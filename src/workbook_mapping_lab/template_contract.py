"""Check whether an ORIGINAL exported destination workbook has required detail tabs.

Never invent or add absent vendor worksheets. Historical populated sub-schedules
are used as a *coverage signal*, not as an automatic current-year classification.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from .simulator import WorkbookSnapshot


def _amount(value: str) -> Decimal | None:
    try:
        v = Decimal(str(value).replace(",", "").strip())
        return v if v.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _historical_detail_rows(book: WorkbookSnapshot, sheet: str) -> list[dict[str, str]]:
    """Nonzero amounts in detail rows only; exclude header and subtotal rows."""
    records=[]
    for addr, cell in book.sheets[sheet]["cells"].items():
        if not addr.startswith("A") or not addr[1:].isdigit():
            continue
        r=addr[1:]
        label=cell["value"].strip()
        if not label or label.casefold().startswith(("total", "back to", "amount")):
            continue
        if label.casefold() in ("-", "others -", "other expenses"):
            continue
        v=_amount(book.cell(sheet,"B"+r)["value"])
        if v is None or v == 0:
            continue
        records.append({"row":r,"caption":label,"amount":format(v,"f")})
    return records


def detail_coverage(previous_export: str, current_template: str) -> dict:
    """Fail closed when active PY supplemental schedules are missing in CY.

    Both inputs must be user/vendor-produced XLSX exports. This test does not
    infer that PY classification is automatically right for CY, nor whether
    previously unused schedules have become necessary this year.
    """
    if Path(previous_export).resolve() == Path(current_template).resolve():
        raise ValueError("Prior export and current template must be different files")
    findings=[]
    with WorkbookSnapshot(previous_export) as prior, WorkbookSnapshot(current_template) as current:
        for name in prior.sheets:
            if name in current.sheets:
                continue
            relevant=_historical_detail_rows(prior,name)
            if not relevant:
                continue
            # Only offer sheet name and item captions. Never copy client amounts
            # into public logs; output report stays private.
            findings.append({
                "issue":"ACTIVE_PREVIOUS_DETAIL_SHEET_ABSENT",
                "sheet":name,
                "prior_item_count":len(relevant),
                "prior_item_captions":[r["caption"] for r in relevant],
                "remedy":"Export the current-year workbook again with this detailed schedule available in the source application.",
            })
        return {
            "status":"READY_FOR_REVIEW" if not findings else "BLOCKED_INCOMPLETE_VENDOR_TEMPLATE",
            "prior_sheet_count":len(prior.sheets),
            "current_sheet_count":len(current.sheets),
            "missing_active_detail_sheets":findings,
            "prior_export_sha256":prior.sha256,
            "current_template_sha256":current.sha256,
            "warning":(
                "This checks only historical used-sheet coverage. "
                "New CY schedules must also be examined. "
                "Never fabricate absent vendor worksheets or silently populate parent totals."
            ),
        }


def require_coverage(previous_export: str, current_template: str) -> None:
    """Guard for applications about to write a checked copy."""
    state=detail_coverage(previous_export,current_template)
    if state["status"]!="READY_FOR_REVIEW":
        missing=", ".join(r["sheet"] for r in state["missing_active_detail_sheets"])
        raise ValueError("Required vendor detail schedules absent: "+missing)


def main() -> None:
    import argparse
    import json
    parser=argparse.ArgumentParser(description="Read-only vendor template coverage check")
    parser.add_argument("--previous-export",required=True)
    parser.add_argument("--current-template",required=True)
    args=parser.parse_args()
    result=detail_coverage(args.previous_export,args.current_template)
    print(json.dumps(result,indent=2))
    if result["status"]!="READY_FOR_REVIEW":
        raise SystemExit(2)


if __name__=="__main__":
    main()
