"""Conservative XLSX writer: change approved numeric cells in a COPY only.

This does not recreate workbooks. Other OPC package parts remain byte-identical
after decompression; only approved existing numeric-cell XML is patched.
No proprietary application import is attempted or claimed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

from .simulator import WorkbookSnapshot, _load_rows, _money, review

DISALLOWED_PARTS = ("/vbaproject", "_xmlsignatures/", "/externallink")
CELL_TAG = re.compile(rb'<c\b(?=[^>]*\br="(?P<address>[A-Z]+[0-9]+)")[^>]*?/>')


def _safe_numeric(v: Decimal) -> str:
    if not v.is_finite():
        raise ValueError("Non-finite Excel number")
    if v.adjusted() > 14:
        raise ValueError("More than 15 significant integer digits; Excel precision unsafe")
    text = format(v, "f")
    if len(text.replace("-", "").replace(".", "").lstrip("0")) > 15:
        raise ValueError("More than 15 significant digits; use source rounding")
    return text


def _patch_existing_cell(raw: bytes, address: str, amount: str) -> bytes:
    """Replace only a self-closing <c> element, preserving other XML bytes."""
    addr = address.strip().upper().encode("ascii")
    target = []
    for match in CELL_TAG.finditer(raw):
        if match.group("address") == addr:
            target.append(match)
    if len(target) != 1:
        raise ValueError("Expected exactly one existing self-closing target cell")
    found = target[0]
    tag = found.group(0)
    # A blank cell should have only r, s, or explicit numeric t="n".
    if re.search(rb'\s+t="(?!n")[^"]+"', tag):
        raise ValueError("Cell has a non-numeric type; refuse to replace")
    # XML entity/namespace transforms are intentionally avoided.
    rendered = _safe_numeric(_money(amount)).encode("ascii")
    replacement = tag[:-2] + b"><v>" + rendered + b"</v></c>"
    return raw[:found.start()] + replacement + raw[found.end():]


def populate(template: str, layout: str, values: str, output: str,
             *, controls: str | None = None) -> dict:
    """Fill a separate copy and reject missing/malformed/unapproved positions."""
    in_path = Path(template).resolve()
    dest = Path(output).resolve()
    if in_path == dest:
        raise ValueError("Refusing to overwrite the source template")
    if dest.exists():
        raise FileExistsError("Output exists; never overwrite without review")
    if in_path.suffix.lower() != ".xlsx" or dest.suffix.lower() != ".xlsx":
        raise ValueError("Only .xlsx files are supported")
    if not in_path.is_file():
        raise FileNotFoundError("Template does not exist")

    before = review(template, layout, values, controls=controls)
    if before["status"] != "PASS":
        raise ValueError("Preflight BLOCKED: " + json.dumps(before["errors"]))

    field_rows = _load_rows(layout, ("field_id", "section", "sheet", "cell", "anchor_cell", "anchor_text"))
    val_rows = _load_rows(values, ("field_id", "section", "amount"))
    lookup = {x["field_id"]: x for x in field_rows}
    targets = defaultdict(list)
    with WorkbookSnapshot(in_path) as snapshot:
        parts = snapshot.archive.namelist()
        if any(any(block in p.lower() for block in DISALLOWED_PARTS) for p in parts):
            raise ValueError("Macros, digital signatures, or external links are unsupported")
        if len(set(parts)) != len(parts):
            raise ValueError("Duplicate package entries are unsupported")
        for val in val_rows:
            field = lookup[val["field_id"]]
            if field["sheet"] not in snapshot.sheets:
                raise ValueError("Unknown worksheet")
            part = snapshot.sheets[field["sheet"]]["part_name"]
            targets[part].append((field["cell"].upper(), val["amount"]))
        staged = {}
        for part, pairs in targets.items():
            raw = snapshot.archive.read(part)
            for address, amount in pairs:
                raw = _patch_existing_cell(raw, address, amount)
            staged[part] = raw

    dest.parent.mkdir(parents=True, exist_ok=True)
    handle, staged_path = tempfile.mkstemp(prefix="workbook_checked_", suffix=".xlsx", dir=dest.parent)
    os.close(handle)
    try:
        # Preserve ZipInfo metadata and unmodified package member bytes.
        with ZipFile(in_path) as z_in, ZipFile(staged_path, mode="w") as z_out:
            for member in z_in.infolist():
                z_out.writestr(member, staged.get(member.filename, z_in.read(member.filename)))
            z_out.comment = z_in.comment
        with ZipFile(in_path) as source, ZipFile(staged_path) as result:
            if source.namelist() != result.namelist():
                raise ValueError("Package file list changed")
            for part in source.namelist():
                if part not in staged and source.read(part) != result.read(part):
                    raise ValueError("Unapproved package part was modified")
            for part, expected in staged.items():
                if result.read(part) != expected:
                    raise ValueError("Destination worksheet patch mismatch")
            if result.testzip() is not None:
                raise ValueError("XLSX ZIP archive failed CRC verification")
        after = review(template, layout, values, filled=staged_path, controls=controls)
        if after["status"] != "PASS":
            raise ValueError("Post-write verification BLOCKED: " + json.dumps(after["errors"]))
        if dest.exists():
            raise FileExistsError("Output became occupied during validation")
        os.replace(staged_path, dest)
        return {
            "status": "PASS", "mode": "checked-copy-write",
            "field_count": len(val_rows),
            "modified_sheet_count": len(staged),
            "unchanged_package_parts_verified": len(parts) - len(staged),
            "output_path": str(dest),
            "source_sha256": before["template_sha256"],
            "result_sha256": after["filled_sha256"],
            "application_import_verified": False,
        }
    finally:
        if os.path.exists(staged_path):
            os.unlink(staged_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely populate a COPY of an .xlsx template")
    parser.add_argument("--template", required=True)
    parser.add_argument("--layout", required=True)
    parser.add_argument("--values", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--controls")
    parser.add_argument("--report", help="Optional private local report")
    args = parser.parse_args()
    result = populate(args.template, args.layout, args.values, args.output,
                      controls=args.controls)
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
