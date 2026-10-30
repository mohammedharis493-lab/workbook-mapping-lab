"""Controlled source → reviewed allocations → Excel copy pipeline.

Only explicitly approved mappings are processed; zero unresolved exceptions is
a release precondition. All input/output paths should be private local files.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .allocations import number, plan_allocations, ready_to_release
from .mapping import load_csv
from .writer import populate
from .template_contract import detail_coverage


def _csv(path: str, columns: tuple[str, ...], rows: list[dict]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def controlled_build(
    *, source: str, rules: str, layout: str, template: str,
    source_controls: str, output_controls: str, output: str,
    exception_report: str, rounding: str = "exact",
    previous_export: str | None = None,
    companion_details: str | None = None,
) -> dict:
    """Create the final workbook only after all mapping and control checks pass.

    The exception report is always local and regenerated. Caller chooses a
    previously unused output filename; the original template is untouched.
    """
    if rounding not in ("exact", "whole_rupees"):
        raise ValueError("Invalid rounding policy")
    inputs = load_csv(source, ("source_id", "section", "caption", "amount"))
    mappings = load_csv(rules, ("source_id", "field_id", "approved"))
    fields = load_csv(layout, ("field_id", "section", "sheet", "cell", "anchor_cell", "anchor_text"))
    source_totals = load_csv(source_controls, ("section", "amount"))
    required_output_totals = load_csv(output_controls, ("section", "total"))
    out, issues, trace = plan_allocations(inputs, mappings, fields, expected_totals=source_totals)
    # The exact user/vendor export is immutable. A current blank export can
    # omit detailed worksheets that were active in the prior-year export.
    # Never silently replace those with broad parent fields.
    if previous_export:
        contract=detail_coverage(previous_export,template)
        for item in contract["missing_active_detail_sheets"]:
            issues.append({"issue":"VENDOR_TEMPLATE_DETAIL_MISSING",
                           "source_id":"","field_id":"",
                           "detail":item["sheet"]})

    output_sections = defaultdict(lambda: Decimal(0))
    deviations = []
    safe_out = []
    for item in out:
        exact = number(item["amount"], name="allocated field amount")
        final = exact
        if rounding == "whole_rupees":
            final = exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if final != exact:
            deviations.append({
                "field_id": item["field_id"],
                "unrounded": format(exact, "f"),
                "output": format(final, "f"),
                "difference": format(final - exact, "f"),
            })
        safe_out.append({**item, "amount": format(final, "f")})
        output_sections[item["section"]] += final

    control_seen = set()
    for control in required_output_totals:
        section = control.get("section", "").strip()
        if section in control_seen:
            issues.append({"issue":"DUPLICATE_OUTPUT_CONTROL","source_id":"","field_id":"","detail":section})
            continue
        control_seen.add(section)
        try:
            want = number(control["total"], name="output control")
        except ValueError:
            issues.append({"issue":"INVALID_OUTPUT_CONTROL","source_id":"","field_id":"","detail":section})
            continue
        actual = output_sections[section]
        if want != actual:
            issues.append({"issue":"OUTPUT_CONTROL_MISMATCH","source_id":"","field_id":"",
                           "detail":f"{section}: expected {want}, actual {actual}"})
    if set(output_sections) != control_seen:
        issues.append({"issue":"INCOMPLETE_OUTPUT_CONTROLS","source_id":"","field_id":"",
                       "detail":f"populated={sorted(output_sections)}, controls={sorted(control_seen)}"})
    if "BS-A" in output_sections and "BS-L" in output_sections:
        if output_sections["BS-A"] != output_sections["BS-L"]:
            issues.append({"issue":"BALANCE_SHEET_DOES_NOT_BALANCE","source_id":"","field_id":"",
                           "detail":f"assets={output_sections['BS-A']} liabilities={output_sections['BS-L']}"})

    report = {
        "status":"PASS" if ready_to_release(issues) else "BLOCKED",
        "source_row_count":len(inputs),
        "approved_mapping_count":sum(1 for x in mappings if x.get("approved","").lower().strip() in ("yes","true","1")),
        "mapped_field_count":len(safe_out),
        "rounding_policy":rounding,
        "rounding_differences":deviations,
        "sections":{k:format(v,"f") for k,v in sorted(output_sections.items())},
        "exceptions":issues,
        "trace":trace,
        "note":"Only an offline workbook compatibility check; application import remains unverified."
    }
    report_path=Path(exception_report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if issues:
        return report

    # Stage private CSVs next to report; never publish mapped values or controls.
    # Reuse an unused output path and remove temporary intermediates afterward.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="mapping_private_", dir=report_path.parent) as work:
        values_csv=Path(work)/"approved_values.csv"
        controls_csv=Path(work)/"output_controls.csv"
        _csv(str(values_csv),("field_id","section","amount"),safe_out)
        _csv(str(controls_csv),("section","total"),required_output_totals)
        result=populate(template, layout, str(values_csv), output, controls=str(controls_csv))
    report["writer"]=result
    report["status"]=result["status"]
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    p=argparse.ArgumentParser(description="Local-only approved-mapping workbook build")
    for key in ("source","rules","layout","template","source-controls","output-controls","output","exception-report"):
        p.add_argument("--"+key, required=True)
    p.add_argument("--rounding",choices=("exact","whole_rupees"),default="exact")
    p.add_argument("--previous-export",help="Optional historical populated vendor export used to block missing detail schedules")
    a=p.parse_args()
    report=controlled_build(
        source=a.source, rules=a.rules,layout=a.layout,template=a.template,
        source_controls=a.source_controls,output_controls=a.output_controls,
        output=a.output,exception_report=a.exception_report,rounding=a.rounding,
        previous_export=a.previous_export)
    print(json.dumps({k:v for k,v in report.items() if k not in ("trace","rounding_differences")},indent=2))
    if report["status"]!="PASS":
        raise SystemExit(2)


if __name__=="__main__":
    main()
