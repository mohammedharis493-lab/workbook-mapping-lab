"""Fill vendor child schedules without duplicating parent values in BS totals."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from .allocations import number


def add_companion_fields(
    values: list[dict],
    layout: list[dict],
    companion_rows: list[dict],
    rounding: str,
) -> tuple[list[dict], list[dict]]:
    """Return (augmented values, blocking exceptions).

    Each companion row must identify an approved parent field, child field and
    amount. All child amounts for each parent must sum to the parent amount.
    Children use a distinct section with suffix '-DETAIL' and are intentionally
    excluded from financial statement control totals.
    """
    errors = []
    base = {row["field_id"]: row for row in values}
    fields = {row["field_id"]: row for row in layout}
    if len(base) != len(values) or len(fields) != len(layout):
        return values, [{"issue": "DUPLICATED_FIELD_ID_IN_VALUES_OR_LAYOUT"}]
    grouped = defaultdict(list)
    used = set()
    for row in companion_rows:
        parent = row["parent_field_id"].strip()
        child = row["detail_field_id"].strip()
        if parent not in base:
            errors.append({"issue": "COMPANION_PARENT_NOT_MAPPED", "field_id": parent})
            continue
        if child not in fields or child in base or child in used:
            errors.append({"issue": "COMPANION_CHILD_MISSING_OR_DUPLICATE", "field_id": child})
            continue
        used.add(child)
        section = fields[child]["section"]
        if section != base[parent]["section"] + "-DETAIL":
            errors.append({"issue": "COMPANION_CHILD_SECTION_INCORRECT", "field_id": child})
            continue
        try:
            amount = number(row["amount"], name="companion amount")
        except ValueError:
            errors.append({"issue": "COMPANION_AMOUNT_INVALID", "field_id": child})
            continue
        if rounding == "whole_rupees":
            amount = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        grouped[parent].append((child, section, amount))
    augmented = list(values)
    for parent, parts in grouped.items():
        expected = number(base[parent]["amount"], name="parent value")
        calculated = sum((part[2] for part in parts), Decimal("0"))
        if calculated != expected:
            errors.append({
                "issue": "COMPANION_CHILDREN_DO_NOT_SUM_TO_PARENT",
                "field_id": parent,
                "detail": f"expected={expected}, calculated={calculated}",
            })
        for child, section, value in parts:
            augmented.append({
                "field_id": child, "section": section,
                "caption": fields[child].get("anchor_text", ""),
                "amount": format(value, "f"),
            })
    return augmented, errors
