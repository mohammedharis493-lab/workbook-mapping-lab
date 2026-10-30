"""Independent completed-return benchmark for two DIFFERENT native workbook layouts.

A generated vendor-import workbook and a manually completed return may have
different worksheets/row coordinates. The approved PRIVATE comparison contract
declares the exact visible labels and columns in each. We never infer that an
equal overall BS or P&L means classifications are correct.

No workbook is modified; no files are saved by the function.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from .mapping import load_csv
from .simulator import WorkbookSnapshot

COLUMN = re.compile(r"^[A-Z]{1,3}$")
FIELDS = ("field_id", "expected_amount", "generated_sheet", "generated_label",
          "generated_value_col", "manual_sheet", "manual_label", "manual_value_col")


def amount(raw: str) -> Decimal | None:
    try:
        if raw is None or not str(raw).strip():
            return None
        value = Decimal(str(raw).strip().replace(",", ""))
        return value if value.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def normal(label: str) -> str:
    return " ".join(str(label).casefold().split())


def find_field(book: WorkbookSnapshot, sheet: str, caption: str, value_column: str,
               *, label_column: str = "A") -> dict:
    """Match one specific label and one numeric slot; never guess a row."""
    if sheet not in book.sheets:
        return {"state": "MISSING_SHEET", "sheet": sheet}
    if book.sheets[sheet]["state"] != "visible":
        return {"state": "HIDDEN_SHEET", "sheet": sheet}
    target = normal(caption)
    matches = []
    for position, item in book.sheets[sheet]["cells"].items():
        if not position.startswith(label_column):
            continue
        row = position[len(label_column):]
        if not row.isdigit() or normal(item["value"]) != target:
            continue
        matches.append(row)
    if len(matches) != 1:
        return {"state": "LABEL_MISSING" if not matches else "LABEL_AMBIGUOUS",
                "sheet": sheet, "matches": len(matches)}
    address = value_column + matches[0]
    slot = book.cell(sheet, address)
    value = amount(slot["value"])
    if slot["formula"]:
        return {"state": "FORMULA_VALUE_REQUIRES_REVIEW", "sheet": sheet, "cell": address}
    if value is None:
        return {"state": "BLANK_OR_NONNUMERIC", "sheet": sheet, "cell": address}
    return {"state": "FOUND", "sheet": sheet, "cell": address,
            "label": caption, "amount": format(value, "f")}


def compare_completed_return(
    generated_workbook: str,
    manual_return: str,
    private_contract: str,
    *,
    tolerance: str = "0",
) -> dict:
    try:
        limit = Decimal(tolerance)
    except InvalidOperation as e:
        raise ValueError("Invalid tolerance") from e
    if not limit.is_finite() or limit < 0:
        raise ValueError("Tolerance must be nonnegative and finite")
    if Path(generated_workbook).resolve() == Path(manual_return).resolve():
        raise ValueError("Completed reference must be independent of generated file")
    rules = load_csv(private_contract, FIELDS)
    if not rules:
        raise ValueError("Benchmark contract contains no approved field rules")
    seen = set()
    details = []
    with WorkbookSnapshot(generated_workbook) as gen, WorkbookSnapshot(manual_return) as manual:
        same_bytes = gen.sha256 == manual.sha256
        if same_bytes:
            raise ValueError("Generated and completed workbooks have identical content")
        for rule in rules:
            field = rule["field_id"].strip()
            if not field or field in seen:
                raise ValueError("Duplicate or blank benchmark field ID")
            seen.add(field)
            g_col = rule["generated_value_col"].strip().upper()
            m_col = rule["manual_value_col"].strip().upper()
            if not COLUMN.fullmatch(g_col) or not COLUMN.fullmatch(m_col):
                raise ValueError("Invalid amount column for field " + field)
            expected = amount(rule["expected_amount"])
            if expected is None:
                raise ValueError("Missing independently verified FS value for " + field)
            gen_info = find_field(gen, rule["generated_sheet"], rule["generated_label"], g_col)
            man_info = find_field(manual, rule["manual_sheet"], rule["manual_label"], m_col)
            statuses = []
            if gen_info["state"] != "FOUND":
                statuses.append("GENERATED_FIELD_" + gen_info["state"])
            elif abs(amount(gen_info["amount"]) - expected) > limit:
                statuses.append("GENERATED_AMOUNT_DIFFERS_FROM_FS")
            if man_info["state"] != "FOUND":
                statuses.append("MANUAL_FIELD_" + man_info["state"])
            elif abs(amount(man_info["amount"]) - expected) > limit:
                statuses.append("MANUAL_RETURN_DIFFERS_FROM_FS")
            if gen_info["state"] == "FOUND" and man_info["state"] == "FOUND":
                if abs(amount(gen_info["amount"]) - amount(man_info["amount"])) > limit:
                    statuses.append("GENERATED_DIFFERS_FROM_MANUAL")
            details.append({
                "field_id": field,
                "status": "MATCH" if not statuses else "REVIEW_REQUIRED",
                "checks": statuses,
                "fs_expected": format(expected, "f"),
                "generated": gen_info,
                "manual": man_info,
            })
    matched = sum(item["status"] == "MATCH" for item in details)
    blockers = sum(any(code.startswith("GENERATED_FIELD_") for code in item["checks"])
                   for item in details)
    return {
        "status": "ALL_CONFIGURED_FIELDS_MATCH" if matched == len(details)
                  else "DIFFERENCES_OR_MISSING_FIELDS",
        "contract_fields": len(details),
        "fully_matched": matched,
        "require_review": len(details) - matched,
        "generated_target_unavailable": blockers,
        "tolerance": format(limit, "f"),
        "generated_sha256": gen.sha256,
        "independent_completed_sha256": manual.sha256,
        "details": details,
        "warning": (
            "Only fields explicitly included in the privately approved comparison "
            "contract have been checked. A matching amount is not proof that "
            "the source financial statements or return are legally correct. "
            "Never fill absent vendor worksheets automatically."
        ),
    }


def main():
    import argparse
    import json
    p = argparse.ArgumentParser(description="Read-only manual return vs generated import workbook benchmark")
    p.add_argument("--generated", required=True)
    p.add_argument("--manual-return", required=True)
    p.add_argument("--private-contract", required=True)
    p.add_argument("--tolerance", default="0")
    p.add_argument("--report", required=True)
    args = p.parse_args()
    result = compare_completed_return(
        args.generated,args.manual_return,args.private_contract,tolerance=args.tolerance)
    destination = Path(args.report).expanduser().resolve()
    checkout = Path(__file__).resolve().parents[2]
    if destination == checkout or checkout in destination.parents:
        raise ValueError("Client comparison reports cannot be saved in public source")
    if destination.exists():
        raise FileExistsError("Never overwrite an earlier report")
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="details"},indent=2))
    if result["status"]!="ALL_CONFIGURED_FIELDS_MATCH":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
