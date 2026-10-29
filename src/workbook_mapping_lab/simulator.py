"""Offline, read-only simulation of a structured spreadsheet import.

Checks target cells and anchor labels in an actual .xlsx template, performs a
virtual field import and re-export, and can compare a subsequently filled file.
It DOES NOT write to Excel or connect to any accounting/tax application.
All actual client workbooks and local mapping tables must remain private.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import posixpath
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CELL_REF = re.compile(r"^([A-Z]+)([1-9][0-9]*)$")


def _cell_key(address: str) -> tuple[int, int]:
    match = CELL_REF.fullmatch(address.upper().strip())
    if not match:
        raise ValueError("Invalid A1 cell address")
    col = 0
    for character in match.group(1):
        col = col * 26 + ord(character) - 64
    return int(match.group(2)), col


def _money(raw: str) -> Decimal:
    try:
        val = Decimal(str(raw).replace(",", "").strip())
        if not val.is_finite():
            raise ValueError("Non-finite amount")
        return val
    except (InvalidOperation, ValueError) as e:
        raise ValueError("Invalid monetary amount") from e


def _load_rows(path: str | Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = set(fields) - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
        return [dict(row) for row in reader]


class WorkbookSnapshot:
    """Read a workbook's structure and selected cells without modifying it."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()
        try:
            self.archive = ZipFile(self.path)
            main = ET.fromstring(self.archive.read("xl/workbook.xml"))
        except (BadZipFile, KeyError, ET.ParseError) as e:
            raise ValueError("Not a supported .xlsx package") from e

        rel_xml = ET.fromstring(self.archive.read("xl/_rels/workbook.xml.rels"))
        relations = {}
        for el in rel_xml.findall(PKG + "Relationship"):
            target = el.get("Target", "")
            if target.startswith("/"):
                target = target.lstrip("/")
            elif not target.startswith("xl/"):
                target = posixpath.normpath("xl/" + target)
            if not target.startswith("xl/") or ".." in target.split("/"):
                continue
            relations[el.get("Id")] = target

        self.strings = []
        if "xl/sharedStrings.xml" in self.archive.namelist():
            root = ET.fromstring(self.archive.read("xl/sharedStrings.xml"))
            self.strings = [
                "".join((el.text or "") for el in si.iter(M + "t"))
                for si in root.findall(M + "si")
            ]

        self.sheets: dict[str, dict] = {}
        for el in main.find(M + "sheets") or []:
            name = el.get("name", "")
            location = relations.get(el.get(R + "id"))
            if not location or location not in self.archive.namelist():
                raise ValueError("Unresolvable worksheet reference")
            root = ET.fromstring(self.archive.read(location))
            cells = {}
            for cell in root.findall(".//" + M + "sheetData/" + M + "row/" + M + "c"):
                address = cell.get("r", "").upper()
                if not CELL_REF.fullmatch(address):
                    continue
                formula = cell.find(M + "f") is not None
                text_val = ""
                v = cell.find(M + "v")
                if v is not None and v.text is not None:
                    text_val = v.text
                    if cell.get("t") == "s":
                        index = int(v.text)
                        text_val = self.strings[index] if index < len(self.strings) else ""
                elif cell.get("t") == "inlineStr":
                    text_val = "".join(
                        n.text or "" for n in cell.iter(M + "t")
                    )
                cells[address] = {"value": text_val, "formula": formula}
            merges = [
                t.get("ref", "")
                for t in root.findall(".//" + M + "mergeCells/" + M + "mergeCell")
            ]
            self.sheets[name] = {
                "state": el.get("state", "visible"),
                "cells": cells,
                "merges": merges,
            }

    def close(self) -> None:
        self.archive.close()

    def __enter__(self) -> "WorkbookSnapshot":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def cell(self, sheet: str, address: str) -> dict:
        return self.sheets[sheet]["cells"].get(
            address.upper(), {"value": "", "formula": False}
        )

    def merged_non_anchor(self, sheet: str, address: str) -> bool:
        point = _cell_key(address)
        for group in self.sheets[sheet]["merges"]:
            parts = group.upper().split(":")
            if len(parts) != 2:
                continue
            lo, hi = sorted((_cell_key(parts[0]), _cell_key(parts[1])))
            if lo[0] <= point[0] <= hi[0] and lo[1] <= point[1] <= hi[1]:
                if point != _cell_key(parts[0]):
                    return True
        return False

    def inventory(self) -> dict:
        return {
            "sheet_count": len(self.sheets),
            "sheets": [{
                "name": name,
                "visibility": data["state"],
                "formula_count": sum(x["formula"] for x in data["cells"].values()),
                "cell_count": len(data["cells"]),
                "merged_ranges": len(data["merges"]),
            } for name, data in self.sheets.items()],
        }


def review(template: str, layout: str, values: str, *, filled: str | None = None,
           controls: str | None = None) -> dict:
    """Produce a mock-import report; no workbook bytes are changed.

    A layout is intentionally explicit rather than guessed from cell captions.
    Field IDs, destination coordinates and anchor labels require prior approval.
    """
    fields = _load_rows(layout, ("field_id", "section", "sheet", "cell", "anchor_cell", "anchor_text"))
    amounts = _load_rows(values, ("field_id", "section", "amount"))
    errors: list[dict] = []
    virtual = {}
    seen_fields, seen_cells = set(), set()
    layout_by_id = {}
    totals = defaultdict(lambda: Decimal("0"))
    with WorkbookSnapshot(template) as wb:
        with WorkbookSnapshot(filled) if filled else _EmptyContext() as filled_wb:
            for row in fields:
                fid = row["field_id"].strip()
                dest = (row["sheet"], row["cell"].strip().upper())
                if not fid or fid in seen_fields:
                    errors.append({"code": "DUPLICATE_OR_EMPTY_FIELD", "field_id": fid})
                    continue
                seen_fields.add(fid)
                layout_by_id[fid] = row
                if dest in seen_cells:
                    errors.append({"code": "DUPLICATE_TARGET_CELL", "field_id": fid})
                seen_cells.add(dest)
                if row["sheet"] not in wb.sheets:
                    errors.append({"code": "MISSING_TEMPLATE_SHEET", "field_id": fid})
                    continue
                if wb.sheets[row["sheet"]]["state"] != "visible":
                    errors.append({"code": "HIDDEN_TARGET_SHEET", "field_id": fid})
                try:
                    if wb.merged_non_anchor(row["sheet"], row["cell"]):
                        errors.append({"code": "NON_ANCHOR_MERGED_CELL", "field_id": fid})
                    anchor = wb.cell(row["sheet"], row["anchor_cell"])["value"]
                    if anchor.strip().casefold() != row["anchor_text"].strip().casefold():
                        errors.append({"code": "ANCHOR_MISMATCH", "field_id": fid})
                    target = wb.cell(row["sheet"], row["cell"])
                    if target["formula"]:
                        errors.append({"code": "FORMULA_TARGET", "field_id": fid})
                    elif target["value"].strip():
                        errors.append({"code": "NONEMPTY_TARGET", "field_id": fid})
                except ValueError:
                    errors.append({"code": "INVALID_CELL_ADDRESS", "field_id": fid})
                if filled_wb is not None and row["sheet"] not in filled_wb.sheets:
                    errors.append({"code": "FILLED_MISSING_SHEET", "field_id": fid})

            for row in amounts:
                fid = row["field_id"].strip()
                if fid in virtual:
                    errors.append({"code": "DUPLICATE_AMOUNT", "field_id": fid})
                    continue
                if fid not in layout_by_id:
                    errors.append({"code": "UNMAPPED_OUTPUT_FIELD", "field_id": fid})
                    continue
                dest = layout_by_id[fid]
                if row["section"].strip().casefold() != dest["section"].strip().casefold():
                    errors.append({"code": "SECTION_MISMATCH", "field_id": fid})
                    continue
                try:
                    amount = _money(row["amount"])
                except ValueError:
                    errors.append({"code": "INVALID_AMOUNT", "field_id": fid})
                    continue
                virtual[fid] = str(amount)
                totals[row["section"]] += amount
                if filled_wb is not None and dest["sheet"] in filled_wb.sheets:
                    actual = filled_wb.cell(dest["sheet"], dest["cell"])
                    if actual["formula"]:
                        errors.append({"code": "FILLED_HAS_FORMULA", "field_id": fid})
                    else:
                        try:
                            if _money(actual["value"]) != amount:
                                errors.append({"code": "FILLED_VALUE_DIFFERS", "field_id": fid})
                        except ValueError:
                            errors.append({"code": "FILLED_NOT_NUMERIC", "field_id": fid})

            expected = {}
            if controls:
                for row in _load_rows(controls, ("section", "total")):
                    try:
                        expected[row["section"]] = _money(row["total"])
                    except ValueError:
                        errors.append({"code": "INVALID_CONTROL_AMOUNT", "section": row["section"]})
                for section, expected_total in expected.items():
                    if totals[section] != expected_total:
                        errors.append({"code": "CONTROL_TOTAL_MISMATCH", "section": section})
            result = {
                "status": "PASS" if not errors else "BLOCKED",
                "mode": "filled-workbook-compare" if filled else "mock-import",
                "template_sha256": wb.sha256,
                "template_sheet_count": len(wb.sheets),
                "field_count": len(fields),
                "virtual_reexported_field_count": len(virtual),
                "control_total_count": len(expected),
                "errors": errors,
                "note": ("This is an offline structural and value simulation. Passing does NOT "
                         "establish that any third-party software will accept an import."),
            }
            if filled_wb is not None:
                result["filled_sha256"] = filled_wb.sha256
            return result


class _EmptyContext:
    def __enter__(self):
        return None

    def __exit__(self, *_):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline spreadsheet import simulator (no writes)")
    sub = parser.add_subparsers(dest="action", required=True)
    inventory = sub.add_parser("inspect", help="Inspect workbook sheets, formulas and merge counts")
    inventory.add_argument("--template", required=True)
    inventory.add_argument("--previous", help="Optional PY workbook to compare missing sheets")
    for mode in ("simulate", "compare"):
        subp = sub.add_parser(mode, help="Mock import or check an externally filled workbook")
        subp.add_argument("--template", required=True)
        subp.add_argument("--layout", required=True)
        subp.add_argument("--values", required=True)
        subp.add_argument("--controls", help="Optional reconciled section totals CSV")
        subp.add_argument("--filled", required=(mode == "compare"))
        subp.add_argument("--report", help="Write JSON report locally; never commit actual client reports")
    args = parser.parse_args()
    if args.action == "inspect":
        with WorkbookSnapshot(args.template) as wb:
            result = wb.inventory()
        if args.previous:
            with WorkbookSnapshot(args.previous) as py:
                result["previous_sheet_count"] = len(py.sheets)
                result["previous_sheets_absent_now"] = sorted(set(py.sheets) - {
                    item["name"] for item in result["sheets"]
                })
    else:
        result = review(args.template, args.layout, args.values,
                        filled=args.filled, controls=args.controls)
        if args.report:
            Path(args.report).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result.get("status") == "BLOCKED":
        sys.exit(2)


if __name__ == "__main__":
    main()
