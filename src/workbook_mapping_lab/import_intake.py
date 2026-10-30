"""Independent native import cell coverage versus a completed return reference.

The original vendor import XLSX is read as an immutable blank template.
The independently completed return (often a 45-sheet ITR-6 XLSM) is evidence,
NOT a substitute for the import template.

Each private contract field has a reviewed FS expected amount and exact labels
in both workbook formats. No automatic mapping, importing, filing or writing.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .layout_resolver import resolve_layout
from .manual_benchmark import FIELDS, amount, find_field
from .mapping import load_csv
from .simulator import WorkbookSnapshot


def inspect_native_import_coverage(
    current_import: str,
    completed_return: str,
    private_contract: str,
    *,
    tolerance: str = "0",
) -> dict:
    """Return a read-only row-by-row target and independent reference report."""
    template = Path(current_import).expanduser().resolve()
    manual = Path(completed_return).expanduser().resolve()
    if template == manual:
        raise ValueError("Current import template and independent ITR cannot be the same file")
    if template.suffix.casefold() != ".xlsx":
        raise ValueError("Current native import requires an original XLSX workbook")
    if manual.suffix.casefold() not in (".xlsx", ".xlsm"):
        raise ValueError("Completed ITR reference requires XLSX or XLSM")
    limit = amount(tolerance)
    if limit is None or limit < 0:
        raise ValueError("Tolerance must be a finite nonnegative amount")
    contract = load_csv(private_contract, FIELDS)
    if not contract:
        raise ValueError("No fields in private comparison contract")
    if len(contract) > 3000:
        raise ValueError("Comparison contract has too many fields")

    routes = []
    expected = {}
    for item in contract:
        field_id = item["field_id"].strip()
        if not field_id or field_id in expected:
            raise ValueError("Duplicate or blank field ID in comparison contract")
        value = amount(item["expected_amount"])
        if value is None:
            raise ValueError("Independent FS amount is invalid for field " + field_id)
        expected[field_id] = value
        routes.append({
            "field_id": field_id,
            "section": (item.get("section") or "BENCHMARK").strip(),
            "sheet": item["generated_sheet"],
            "caption": item["generated_label"],
            "anchor_column": (item.get("generated_label_col") or "A").strip(),
            "amount_column": item["generated_value_col"],
        })
    target = resolve_layout(str(template), routes)
    target_fields = {item["field_id"]: item for item in target["layout"]}
    errors_by_id: dict[str, list[dict]] = {}
    for issue in target["exceptions"]:
        errors_by_id.setdefault(issue["field_id"], []).append(issue)

    rows = []
    with WorkbookSnapshot(template) as source, WorkbookSnapshot(manual) as reference:
        if source.sha256 == reference.sha256:
            raise ValueError("Independent completed return cannot match the import template")
        for item in contract:
            fid = item["field_id"].strip()
            numeric = expected[fid]
            found = target_fields.get(fid)
            target_status = "NATIVE_CELL_READY" if found else "TARGET_UNAVAILABLE"
            reasons = list(errors_by_id.get(fid, []))
            manual_found = find_field(
                reference,
                item["manual_sheet"], item["manual_label"],
                item["manual_value_col"].strip().upper(),
                label_column=(item.get("manual_label_col") or "A").strip().upper(),
                anchor_cell=(item.get("manual_label_cell") or ""),
                allow_hidden_reference=True,
            )
            matching = (
                manual_found["state"] == "FOUND" and
                abs(amount(manual_found["amount"]) - numeric) <= limit
            )
            if manual_found["state"] == "FOUND" and not matching:
                reference_status = "REFERENCE_DIFFERS_FROM_FS"
            elif manual_found["state"] == "FOUND":
                reference_status = "REFERENCE_MATCHES_FS"
            else:
                reference_status = "REFERENCE_" + manual_found["state"]

            if not found:
                verdict = "BLOCKED_NATIVE_IMPORT_DESTINATION"
            elif not matching:
                verdict = "NEEDS_INDEPENDENT_REFERENCE_REVIEW"
            else:
                verdict = "READY_FOR_ACCOUNTANT_MAPPING_REVIEW"

            rows.append({
                "field_id": fid,
                "expected_fs_amount": format(numeric, "f"),
                "native_sheet": item["generated_sheet"],
                "native_label": item["generated_label"],
                "native_target": (
                    {"sheet":found["sheet"], "cell":found["cell"],
                     "anchor_cell":found["anchor_cell"]}
                    if found else None
                ),
                "native_status": target_status,
                "native_exceptions": reasons,
                "completed_reference_status": reference_status,
                "completed_reference": manual_found,
                "verdict": verdict,
                "next_action": (
                    "Obtain a genuine current-year Winman import export with this "
                    "native detail slot, or review direct entry in Winman separately. "
                    "Never reconstruct vendor worksheets."
                    if not found else
                    "Check completed ITR figure, approved cell and FS source evidence."
                    if not matching else
                    "Verify the entity-specific approval and reconciliations before writing."
                ),
            })
        native_sha, reference_sha = source.sha256, reference.sha256

    unavailable = sum(r["native_target"] is None for r in rows)
    reference_problem = sum(r["completed_reference_status"] != "REFERENCE_MATCHES_FS"
                            for r in rows)
    ready = sum(r["verdict"] == "READY_FOR_ACCOUNTANT_MAPPING_REVIEW" for r in rows)
    status = (
        "BLOCKED_NATIVE_IMPORT_TARGETS" if unavailable else
        "NEEDS_REFERENCE_REVIEW" if reference_problem else
        "READY_FOR_ACCOUNTANT_MAPPING_REVIEW"
    )
    return {
        "status": status,
        "field_count": len(rows),
        "import_cells_available": len(rows) - unavailable,
        "import_cells_unavailable": unavailable,
        "reference_mismatches": reference_problem,
        "ready_for_accountant_review": ready,
        "tolerance": format(limit, "f"),
        "native_template_sha256": native_sha,
        "independent_return_sha256": reference_sha,
        "rows": rows,
        "scope": "Only explicitly reviewed fields in the private comparison contract",
        "caution": (
            "A completed ITR-6 may contain fields absent from a separately exported "
            "native import XLSX. This diagnostic never merges, writes, fabricates "
            "or approves fields, nor establishes Winman import support for them."
        ),
    }
