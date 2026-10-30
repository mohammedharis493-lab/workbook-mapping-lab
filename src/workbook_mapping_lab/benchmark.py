"""Compare a generated workbook with a *completed* current-year reference export.

The purpose is to validate field classification and amounts, not to test the
third-party import mechanism. Everything runs offline; never commit reports.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .fs_extract import canonical_caption, numeric
from .mapping import load_csv
from .simulator import WorkbookSnapshot


def _decimal_from_cell(value: str) -> Decimal | None:
    return numeric(value)


def _find_anchor(sheet: dict, reference: WorkbookSnapshot, name: str,
                 anchor_col: str, destination_col: str, label: str):
    """Resolve a reference field by its description; never guess ambiguous rows."""
    candidate = []
    expected = canonical_caption(label)
    for address, data in sheet["cells"].items():
        if not address.startswith(anchor_col):
            continue
        row = address[len(anchor_col):]
        if not row.isdigit():
            continue
        if canonical_caption(data["value"]) != expected:
            continue
        amount = reference.cell(name, destination_col + row)
        candidate.append((destination_col + row, amount))
    return candidate


def compare_reference(
    generated_path: str,
    completed_path: str,
    layout_path: str,
    *,
    tolerance: str = "0",
) -> dict:
    """Compare all configured destination fields by anchor caption, not row number.

    Treat a blank field as different from numeric zero, and do not mistake a
    generated workbook matching a partially filled reference as proof of full
    return coverage. An independently completed reference is required.
    """
    try:
        limit = Decimal(tolerance)
    except InvalidOperation as e:
        raise ValueError("Invalid tolerance") from e
    if not limit.is_finite() or limit < 0:
        raise ValueError("Tolerance must be finite and nonnegative")
    rows = load_csv(layout_path,
        ("field_id","section","sheet","cell","anchor_cell","anchor_text"))
    issues = []
    checked = []
    seen = set()

    def mark(fid: str, code: str, details: str = ""):
        issues.append({"field_id": fid, "code": code, "detail": details})

    with WorkbookSnapshot(generated_path) as gen, WorkbookSnapshot(completed_path) as ref:
        if gen.sha256 == ref.sha256:
            mark("", "IDENTICAL_FILES_NOT_INDEPENDENT_REFERENCE",
                 "The two files have the same SHA256; independent completion was not verified.")
        mapped_reference_cells = set()
        mapped_sheets = set()
        for item in rows:
            fid = item["field_id"].strip()
            name = item["sheet"]
            cell = item["cell"].upper()
            anchor = item["anchor_cell"].upper()
            key = (name, cell)
            if not fid or fid in seen:
                mark(fid, "DUPLICATE_OR_EMPTY_FIELD_ID")
                continue
            seen.add(fid)
            if key in ((x["sheet"],x["cell"].upper()) for x in rows if x is not item):
                mark(fid, "REUSED_TARGET_CELL")
                continue
            mapped_sheets.add(name)
            if name not in gen.sheets or name not in ref.sheets:
                mark(fid, "SHEET_MISSING_IN_ONE_WORKBOOK", name)
                continue
            gen_label = gen.cell(name, anchor)["value"]
            if canonical_caption(gen_label) != canonical_caption(item["anchor_text"]):
                mark(fid, "GENERATED_LABEL_CHANGED", anchor)
                continue
            gen_content = gen.cell(name, cell)["value"]
            gen_amount = _decimal_from_cell(gen_content)
            if gen_amount is None:
                mark(fid, "GENERATED_AMOUNT_BLANK_OR_NOT_NUMERIC", cell)
                continue
            anchor_col = anchor.rstrip("0123456789")
            destination_col = cell.rstrip("0123456789")
            found = _find_anchor(ref.sheets[name], ref, name,
                                 anchor_col, destination_col, item["anchor_text"])
            if len(found) != 1:
                mark(fid, "REFERENCE_LABEL_NOT_UNIQUE_OR_MISSING",
                     f"{len(found)} label matches in {name}")
                continue
            ref_cell, ref_data = found[0]
            mapped_reference_cells.add((name, ref_cell))
            ref_amount = _decimal_from_cell(ref_data["value"])
            if ref_amount is None:
                mark(fid, "REFERENCE_FIELD_BLANK_OR_NON_NUMERIC", ref_cell)
                continue
            diff = gen_amount - ref_amount
            good = abs(diff) <= limit
            checked.append({
                "field_id": fid, "section": item["section"],
                "generated_cell": f"{name}!{cell}",
                "reference_cell": f"{name}!{ref_cell}",
                "generated": format(gen_amount,"f"),
                "reference": format(ref_amount,"f"),
                "difference": format(diff,"f"),
                "status": "MATCH" if good else "DIFFERENT",
            })
            if not good:
                mark(fid, "AMOUNT_OR_CLASSIFICATION_MISMATCH",
                     f"{name}: generated {gen_amount}, completed {ref_amount}")

        # Enumerate populated same-column reference fields not included in
        # the mapping layout. Totals/subtotals are included as coverage
        # candidates, not classified automatically or claimed as errors.
        unreviewed = []
        field_columns = {}
        for item in rows:
            name = item["sheet"]
            a = item["anchor_cell"].rstrip("0123456789").upper()
            b = item["cell"].rstrip("0123456789").upper()
            field_columns.setdefault(name, set()).add((a,b))
        for name in mapped_sheets:
            if name not in ref.sheets:
                continue
            for addr, data in ref.sheets[name]["cells"].items():
                for label_col, val_col in field_columns.get(name, ()):
                    if not addr.startswith(label_col):
                        continue
                    r = addr[len(label_col):]
                    if not r.isdigit():
                        continue
                    target = val_col + r
                    if (name, target) in mapped_reference_cells:
                        continue
                    value = ref.cell(name, target)["value"]
                    parsed = _decimal_from_cell(value)
                    if parsed is None or not data["value"].strip():
                        continue
                    unreviewed.append({
                        "sheet": name, "label_cell": addr, "value_cell": target,
                        "caption": data["value"][:120],
                        "reference_amount": format(parsed,"f")
                    })
        unreviewed.sort(key=lambda x:(x["sheet"],x["label_cell"]))
        summary = {
            "status": "MATCHED_SELECTED_FIELDS" if not issues else "DIFFERENCES_OR_BLOCKERS",
            "generated_sha256": gen.sha256,
            "completed_reference_sha256": ref.sha256,
            "target_fields_configured": len(rows),
            "fields_compared": len(checked),
            "matching_fields": sum(x["status"]=="MATCH" for x in checked),
            "differing_fields": sum(x["status"]=="DIFFERENT" for x in checked),
            "additional_populated_reference_candidates": len(unreviewed),
            "comparison_tolerance": format(limit,"f"),
            "details": checked,
            "exceptions": issues,
            "coverage_candidates": unreviewed,
            "warning": ("A matching result applies only to configured fields. "
                        "The reference must be the independently completed "
                        "current-year return; coverage and legal treatments "
                        "require accountant review. This does not test imports."),
        }
    return summary


def main():
    p = argparse.ArgumentParser(description="Current-year field-by-field benchmark")
    p.add_argument("--generated", required=True)
    p.add_argument("--completed-reference", required=True)
    p.add_argument("--layout", required=True)
    p.add_argument("--tolerance", default="0")
    p.add_argument("--report", required=True)
    a = p.parse_args()
    result = compare_reference(a.generated, a.completed_reference, a.layout,
                               tolerance=a.tolerance)
    dst = Path(a.report).expanduser().resolve()
    repo = Path(__file__).resolve().parents[2]
    if dst == repo or repo in dst.parents:
        raise ValueError("Reports with financial data may not be saved in the public repository")
    if dst.exists():
        raise FileExistsError("Refusing to overwrite previous benchmark report")
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({key: value for key,value in result.items()
                      if key not in ("details","coverage_candidates","exceptions")},indent=2))
    if result["status"] != "MATCHED_SELECTED_FIELDS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
