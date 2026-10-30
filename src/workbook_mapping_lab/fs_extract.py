"""Read-only, profile-driven financial statement extraction from local XLSX files.

Profiles select *detail rows*, not financial-statement totals. A profile is a
reviewed source layout, not a declaration of tax classification correctness.
Extraction never evaluates formulas, executes macros or modifies a workbook.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .simulator import WorkbookSnapshot

NUMERIC = re.compile(r"^[\s+-]*[0-9][0-9,.]*(?:\.[0-9]+)?\s*$")
SAFE_CELL = re.compile(r"^[A-Z]{1,3}[1-9][0-9]*$")
SUSPICIOUS_LABELS = (
    "total", "subtotal", "grand total", "brought forward", "carried forward",
    "number of shares", "earnings per share", "percentage", "shareholding",
)


def canonical_caption(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")


def numeric(raw: str) -> Decimal | None:
    raw = str(raw).strip()
    if not raw or not NUMERIC.fullmatch(raw):
        return None
    try:
        value = Decimal(raw.replace(",", ""))
        return value if value.is_finite() else None
    except InvalidOperation:
        return None


def _unique_id(section: str, label: str, count: int) -> str:
    root = canonical_caption(section).upper() + "-" + canonical_caption(label).upper()
    return root if count == 1 else f"{root}--{count}"


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("format") != 1:
        raise ValueError("Unsupported extraction profile format")
    ranges = profile.get("ranges")
    if not isinstance(ranges, list) or not ranges:
        raise ValueError("Profile requires at least one selected range")
    for item in ranges:
        if not isinstance(item, dict):
            raise ValueError("Invalid profile range")
        if not item.get("sheet") or not item.get("section"):
            raise ValueError("Each range requires a worksheet and a section")
        cols = [item.get(k, "") for k in ("caption_column", "current_column")]
        if any(not re.fullmatch("[A-Z]{1,3}", str(x).upper()) for x in cols):
            raise ValueError("Invalid label or value column")
        if "previous_column" in item and item["previous_column"]:
            if not re.fullmatch("[A-Z]{1,3}", str(item["previous_column"]).upper()):
                raise ValueError("Invalid PY column")
        rows = item.get("selected_rows")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Each range requires explicit selected_rows")
        if len(set(rows)) != len(rows) or not all(isinstance(r, int) and 1 <= r <= 100000 for r in rows):
            raise ValueError("Duplicate or invalid selected_rows")
        if item.get("unit", "rupees").lower() not in ("rupees", "inr", "thousands", "lakhs", "crores"):
            raise ValueError("Unknown money unit")
        if item.get("period_header_cell") and not SAFE_CELL.fullmatch(
            str(item["period_header_cell"]).upper()
        ):
            raise ValueError("Invalid date header address")
    for watch in profile.get("watch_ranges", []):
        if not isinstance(watch, dict) or not watch.get("sheet"):
            raise ValueError("Each watch range needs a worksheet")
        start, stop = watch.get("start_row"), watch.get("end_row")
        if not isinstance(start, int) or not isinstance(stop, int) or start < 1 or stop < start or stop-start > 30000:
            raise ValueError("Invalid numeric row watch range")
        for name in ("caption_column","current_column"):
            if not re.fullmatch("[A-Z]{1,3}", str(watch.get(name,"")).upper()):
                raise ValueError("Invalid watched column")
        ignored=watch.get("ignore_rows",[])
        if not isinstance(ignored,list) or not all(isinstance(x,int) for x in ignored):
            raise ValueError("Invalid ignored row list")


def scan_sheet(
    wb: WorkbookSnapshot, sheet: str,
    *, caption_column: str = "A", current_column: str = "C",
    previous_column: str = "D", start_row: int = 1, end_row: int = 500,
) -> list[dict[str, str]]:
    """Read candidate figures without deciding which are import-worthy."""
    if sheet not in wb.sheets:
        raise ValueError("Worksheet not present")
    if end_row < start_row or end_row - start_row > 30000:
        raise ValueError("Unsafe row scan range")
    result = []
    for row in range(start_row, end_row + 1):
        label = wb.cell(sheet, f"{caption_column.upper()}{row}")["value"].strip()
        cy = wb.cell(sheet, f"{current_column.upper()}{row}")
        py = wb.cell(sheet, f"{previous_column.upper()}{row}") if previous_column else {"value": ""}
        if not label:
            continue
        value = numeric(cy["value"])
        if value is None:
            continue
        risk = []
        low = label.casefold()
        if any(phrase in low for phrase in SUSPICIOUS_LABELS):
            risk.append("POSSIBLE_TOTAL_OR_DISCLOSURE")
        if cy["formula"]:
            risk.append("FORMULA_CACHED_VALUE")
        if numeric(py["value"]) is None and py["value"].strip():
            risk.append("PREVIOUS_NON_NUMERIC")
        result.append({
            "sheet":sheet, "row":str(row), "caption":label,
            "current_amount":format(value,"f"),
            "previous_amount":("" if numeric(py["value"]) is None else format(numeric(py["value"]),"f")),
            "risk":";".join(risk), "status":"UNREVIEWED",
        })
    return result


def extract_profile(
    workbook_path: str, profile: dict[str, Any],
    *, previous_workbook_path: str | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Extract profile-selected cells; report all changed/missing expected rows."""
    validate_profile(profile)
    found: list[dict[str,str]] = []
    issues: list[dict[str,str]] = []
    identity_counts: Counter[tuple[str,str]] = Counter()
    previous = None
    with WorkbookSnapshot(workbook_path) as wb:
        try:
            if previous_workbook_path:
                previous = WorkbookSnapshot(previous_workbook_path)
            for block in profile["ranges"]:
                sheet, section = block["sheet"], block["section"]
                if sheet not in wb.sheets:
                    issues.append({"issue":"MISSING_WORKSHEET","source_id":"","detail":sheet})
                    continue
                label_col = block["caption_column"].upper()
                current_col = block["current_column"].upper()
                previous_col = (block.get("previous_column") or "").upper()
                unit = block.get("unit", "rupees").lower()
                header_at = str(block.get("period_header_cell") or "").upper()
                header_text = str(block.get("period_header_contains") or "")
                if header_at and header_text:
                    text = wb.cell(sheet, header_at)["value"]
                    if header_text.casefold() not in text.casefold():
                        issues.append({"issue":"PERIOD_HEADER_MISMATCH","source_id":"","detail":f"{sheet}!{header_at}"})
                for row in block["selected_rows"]:
                    label = wb.cell(sheet, f"{label_col}{row}")["value"].strip()
                    raw = wb.cell(sheet, f"{current_col}{row}")
                    curr = numeric(raw["value"])
                    if not label or curr is None:
                        issues.append({"issue":"MISSING_CAPTION_OR_AMOUNT","source_id":"","detail":f"{sheet}!{row}"})
                        continue
                    # Stable ID is based on descriptive caption and section, not row number.
                    key=(section, canonical_caption(label))
                    identity_counts[key]+=1
                    sid=_unique_id(section,label,identity_counts[key])
                    risks=[]
                    if identity_counts[key]>1:
                        risks.append("DUPLICATE_CAPTION")
                    notices = ["FORMULA_CACHED_VALUE"] if raw["formula"] else []
                    if any(phrase in label.casefold() for phrase in SUSPICIOUS_LABELS):
                        risks.append("POSSIBLE_TOTAL_OR_DISCLOSURE")
                    py = None
                    if previous_col:
                        py = numeric(wb.cell(sheet, f"{previous_col}{row}")["value"])
                    old = None
                    if previous and sheet in previous.sheets:
                        # Locate same descriptive caption in previous-year worksheet.
                        matches = [
                            (r, numeric(previous.cell(sheet,f"{current_col}{r}")["value"]))
                            for r in range(max(1,row-8),row+9)
                            if canonical_caption(previous.cell(sheet,f"{label_col}{r}")["value"]) == key[1]
                        ]
                        matches = [(r,amount) for r,amount in matches if amount is not None]
                        if len(matches)==1:
                            old=matches[0][1]
                        elif not matches:
                            risks.append("NOT_FOUND_IN_PRIOR_FS")
                        else:
                            risks.append("AMBIGUOUS_PRIOR_FS_ROW")
                    if py is not None and old is not None and py != old:
                        risks.append("PREVIOUS_COLUMN_DISAGREES_WITH_PRIOR_FS")
                    entry = {
                        "source_id":sid, "section":section, "caption":label,
                        "amount":format(curr, "f"), "unit":unit,
                        "sheet":sheet, "cell":f"{current_col}{row}",
                        "previous_amount":"" if py is None else format(py,"f"),
                        "risk":";".join(risks),
                        "notice":";".join(notices),
                    }
                    found.append(entry)
                    for risk in risks:
                        issues.append({"issue":risk,"source_id":sid,"detail":f"{sheet}!{current_col}{row}"})
            # Watch limited, reviewer-approved source regions for new numeric
            # detail lines. Deliberate summary/duplicate exclusions are explicit.
            # Without watch_ranges, new rows OUTSIDE the selected profile cannot
            # be automatically ruled out.
            selected={(part["sheet"], row)
                      for part in profile["ranges"]
                      for row in part["selected_rows"]}
            reported=set()
            for watch in profile.get("watch_ranges", []):
                sheet=watch["sheet"]
                if sheet not in wb.sheets:
                    issues.append({"issue":"MISSING_WATCH_WORKSHEET","source_id":"","detail":sheet})
                    continue
                ignored=set(watch.get("ignore_rows", []))
                label_col=watch["caption_column"].upper()
                value_col=watch["current_column"].upper()
                for row in range(watch["start_row"],watch["end_row"]+1):
                    if (sheet,row) in selected or row in ignored or (sheet,row) in reported:
                        continue
                    label=wb.cell(sheet,f"{label_col}{row}")["value"].strip()
                    amount=numeric(wb.cell(sheet,f"{value_col}{row}")["value"])
                    if not label or amount is None or amount==0:
                        continue
                    if any(phrase in label.casefold() for phrase in SUSPICIOUS_LABELS):
                        continue
                    reported.add((sheet,row))
                    issues.append({
                        "issue":"NEW_UNREVIEWED_NUMERIC_DETAIL",
                        "source_id":"",
                        "detail":f"{sheet}!{value_col}{row}: {label[:80]}",
                    })
        finally:
            if previous:
                previous.close()
    return found, issues


def load_profile(path: str) -> dict[str, Any]:
    data=json.loads(Path(path).read_text(encoding="utf-8-sig"))
    validate_profile(data)
    return data
