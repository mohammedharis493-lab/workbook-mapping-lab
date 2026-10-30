"""Reviewed roll-forward of creditor ageing and two-band return disclosure.

This module NEVER updates source FS or tax software. A bucket roll is a
continuity check; payment or adjustment evidence governs whether amounts
remain outstanding. The two return categories use *current* ageing, not a
made-up recomputation of prior-year balances.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping


BUCKETS = ("under_1", "from_1_to_2", "from_2_to_3", "over_3")


def amount(value, description: str) -> Decimal:
    try:
        if value is None or not str(value).strip():
            raise ValueError(description + " is missing")
        result = Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        raise ValueError(description + " is not numeric") from None
    if not result.is_finite() or result < 0:
        raise ValueError(description + " must be finite and nonnegative")
    return result


def parse_ageing(values: Mapping) -> dict[str, Decimal]:
    """Require all 4 current age buckets. Never infer missing values."""
    missing = set(BUCKETS) - set(values)
    if missing:
        raise ValueError("Missing ageing buckets: " + ", ".join(sorted(missing)))
    return {key: amount(values[key], key) for key in BUCKETS}


def itr_ageing(current_ageing: Mapping) -> dict[str, Decimal]:
    """Return the two disclosure bands from the reviewed current-year ageing."""
    c = parse_ageing(current_ageing)
    younger = c["under_1"]
    older = c["from_1_to_2"] + c["from_2_to_3"] + c["over_3"]
    return {"under_1": younger, "over_1": older, "total": younger + older}


def check_rollforward(
    previous_ageing: Mapping,
    current_ageing: Mapping,
    *,
    settlements_of_prior: Mapping | None = None,
    current_year_new: str | Decimal | None = None,
) -> dict:
    """Test whether unpaid PY amounts rolled exactly one age bucket.

    Unknown settlements remain an explicit limitation. If provided, settlements
    are indexed by PREVIOUS-year bucket and must not exceed their balances.
    This function doesn't identify invoice dates or attribute repayments.
    """
    previous = parse_ageing(previous_ageing)
    current = parse_ageing(current_ageing)
    if settlements_of_prior is None:
        paid = {key: Decimal("0") for key in BUCKETS}
        settlements_provided = False
    else:
        if set(settlements_of_prior) != set(BUCKETS):
            raise ValueError("All four prior-ageing settlement buckets required")
        paid = {key: amount(settlements_of_prior[key], key + " settled")
                for key in BUCKETS}
        for key in BUCKETS:
            if paid[key] > previous[key]:
                raise ValueError("Settlements exceed opening balance in " + key)
        settlements_provided = True
    remaining = {key: previous[key] - paid[key] for key in BUCKETS}
    expected = {
        "from_1_to_2": remaining["under_1"],
        "from_2_to_3": remaining["from_1_to_2"],
        "over_3": remaining["from_2_to_3"] + remaining["over_3"],
    }
    current_extra = None if current_year_new is None else amount(current_year_new, "current-year new")
    differences = {key: current[key] - value for key, value in expected.items()}
    all_match = all(x == 0 for x in differences.values())
    under_one_match = None if current_extra is None else current["under_1"] == current_extra
    bands = itr_ageing(current)
    prior_total = sum(previous.values(), Decimal("0"))
    settlement_total = sum(paid.values(), Decimal("0"))
    actual_expected_total = prior_total - settlement_total + (current_extra or Decimal("0"))
    total_matches = (None if current_extra is None else
                     bands["total"] == actual_expected_total)
    return {
        "status": "ROLLFORWARD_MATCH" if all_match and under_one_match is not False
                  and total_matches is not False else "REQUIRES_REVIEW",
        "previous_total": prior_total,
        "current_total": bands["total"],
        "itr_under_1": bands["under_1"],
        "itr_over_1": bands["over_1"],
        "expected_rolled_prior": expected,
        "difference_by_bucket": differences,
        "settlements_of_prior_specified": settlements_provided,
        "new_current_year_specified": current_extra is not None,
        "current_new_matches": under_one_match,
        "total_continuity_matches": total_matches,
        "warning": (
            "A PY balance moves from <1 to 1-2, from 1-2 to 2-3, from 2-3 "
            "to >3, and >3 stays >3 if it remains outstanding. "
            "Payments, adjustments and invoice dates must be verified. "
            "The return's two figures are always derived from the current "
            "verified ageing schedule."
        ),
    }
