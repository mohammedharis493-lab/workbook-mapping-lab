"""Read-only export readiness: no workbook is patched or created.

This is a diagnostic aid. Existing strict write-time checks remain authoritative.
A passing preflight is NOT an accounting or import approval.
"""
from __future__ import annotations

from pathlib import Path

from .layout_resolver import resolve_layout
from .mapping import load_csv
from .simulator import WorkbookSnapshot
from .template_contract import detail_coverage


def preflight_export(template: str, previous_export: str = "",
                     routes_file: str = "") -> dict:
    current_path = Path(template).expanduser()
    if current_path.suffix.lower() != ".xlsx":
        raise ValueError("The import template must be an original .xlsx export")
    if not current_path.is_file():
        raise FileNotFoundError("Current-year exported template not found")

    with WorkbookSnapshot(current_path) as current:
        current_count = len(current.sheets)
        current_sheets = set(current.sheets)
        sha = current.sha256

    prior_count = None
    absent_history = []
    historical_checked = bool(previous_export)
    if historical_checked:
        previous = detail_coverage(previous_export, template)
        prior_count = previous["prior_sheet_count"]
        absent_history = [
            {"sheet": item["sheet"], "prior_item_count": item["prior_item_count"]}
            for item in previous["missing_active_detail_sheets"]
        ]

    routes = []
    missing_required = []
    field_issues = []
    resolved = 0
    if routes_file:
        routes = load_csv(routes_file, ("field_id", "section", "sheet", "caption"))
        for sheet in sorted({r["sheet"] for r in routes} - current_sheets):
            missing_required.append(sheet)
        if routes:
            result = resolve_layout(template, routes)
            resolved = result["count_resolved"]
            field_issues = result["exceptions"]

    missing = sorted({x["sheet"] for x in absent_history} | set(missing_required))
    if missing:
        status = "INCOMPLETE_OFFICIAL_EXPORT"
        next_step = ("Re-export the current-year workbook with the required native "
                     "detail schedules available. Do not create missing sheets.")
    elif field_issues or not routes or not historical_checked:
        status = "NEEDS_REVIEW"
        next_step = ("Review the required field definitions and previous-year "
                     "schedule coverage. A complete export cannot yet be confirmed.")
    else:
        status = "READY_FOR_REVIEW"
        next_step = ("The configured fields were located. Continue with "
                     "independent financial and mapping approvals.")

    return {
        "status": status,
        "current_sheet_count": current_count,
        "previous_sheet_count": prior_count,
        "historical_coverage_checked": historical_checked,
        "detail_fields_requested": len(routes),
        "detail_fields_resolved": resolved,
        "missing_sheets": missing,
        "missing_previously_used": absent_history,
        "missing_configured_sheets": missing_required,
        "field_issues": field_issues,
        "current_template_sha256": sha,
        "next_step": next_step,
        "warning": ("This is a read-only, configured-field preflight, not a "
                    "complete ITR schedule audit. Never fabricate vendor sheets."),
    }
