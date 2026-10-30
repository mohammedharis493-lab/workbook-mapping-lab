"""Review-first full-schedule amount allocation and reconciliation.

Operate on *detail rows only*. Source subtotals are independent control figures,
not data rows to import twice. All mapping rules require explicit approval.
No files are modified by this module.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Mapping

UNIT_FACTORS = {
    "rupees": Decimal("1"),
    "inr": Decimal("1"),
    "thousands": Decimal("1000"),
    "lakhs": Decimal("100000"),
    "crores": Decimal("10000000"),
}
SIGN_MODES = {"keep": Decimal("1"), "reverse": Decimal("-1")}


def number(raw: object, *, name: str, allow_zero: bool = True) -> Decimal:
    try:
        text = str(raw).replace(",", "").strip()
        if not text:
            raise ValueError()
        val = Decimal(text)
        if not val.is_finite() or (not allow_zero and not val):
            raise ValueError()
        return val
    except (ValueError, InvalidOperation):
        raise ValueError(f"{name}: invalid finite decimal") from None


def plan_allocations(
    source_rows: list[dict[str, str]],
    rules: list[dict[str, str]],
    targets: list[dict[str, str]],
    *,
    expected_totals: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Return (output, exceptions, trace) without writing any file.

    Source columns: source_id, section, caption, amount, unit (optional).
    Rule columns: source_id, field_id, approved, portion (optional), sign (optional).
    Target columns: field_id, section, caption.
    Controls (optional): section, amount.
    Each source may fan out via approved fractional portions summing to one.
    Multiple sources can feed a single field. Sign inversion must be explicit.
    """
    problems: list[dict[str, str]] = []
    trace: list[dict[str, str]] = []
    sums: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    target_by_id: dict[str, dict] = {}
    seen_sources: set[str] = set()
    rules_by_source: dict[str, list[dict]] = defaultdict(list)
    mapped_sources: dict[str, dict] = {}

    def flag(kind: str, sid: str = "", fid: str = "", detail: str = ""):
        problems.append({
            "issue": kind, "source_id": sid, "field_id": fid, "detail": detail,
        })

    for dest in targets:
        fid = dest.get("field_id", "").strip()
        if not fid or fid in target_by_id:
            flag("DUPLICATE_OR_BLANK_TARGET_ID", fid=fid)
        else:
            target_by_id[fid] = dest

    for src in source_rows:
        sid = src.get("source_id", "").strip()
        if not sid or sid in seen_sources:
            flag("DUPLICATE_OR_BLANK_SOURCE_ID", sid=sid)
            continue
        seen_sources.add(sid)
        mapped_sources[sid] = src

    for rule in rules:
        sid = rule.get("source_id", "").strip()
        fid = rule.get("field_id", "").strip()
        approval = rule.get("approved", "").strip().lower()
        if approval not in ("yes", "true", "1"):
            # An unapproved rule is *not* silently used.
            continue
        if sid not in mapped_sources:
            flag("APPROVED_SOURCE_NOT_PRESENT", sid=sid, fid=fid)
            continue
        if fid not in target_by_id:
            flag("TARGET_NOT_IN_TEMPLATE", sid=sid, fid=fid)
            continue
        rules_by_source[sid].append(rule)

    seen_sections: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    mapped_sections: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for sid, src in mapped_sources.items():
        group = src.get("section", "").strip()
        if not group:
            flag("BLANK_SOURCE_SECTION", sid=sid)
            continue
        try:
            amt = number(src.get("amount", ""), name="source amount")
            unit = (src.get("unit") or "rupees").strip().lower()
            if unit not in UNIT_FACTORS:
                raise ValueError("Unrecognised unit")
            source_value = amt * UNIT_FACTORS[unit]
        except ValueError:
            flag("INVALID_SOURCE_AMOUNT_OR_UNIT", sid=sid)
            continue
        seen_sections[group] += source_value
        these = rules_by_source.get(sid, [])
        if not these:
            flag("UNMAPPED_OR_NOT_APPROVED", sid=sid, detail=src.get("caption", ""))
            continue
        checked = []
        used_targets = set()
        for rule in these:
            fid = rule["field_id"].strip()
            if fid in used_targets:
                flag("DUPLICATE_RULE_TARGET", sid=sid, fid=fid)
                continue
            used_targets.add(fid)
            target = target_by_id[fid]
            if target.get("section", "").strip() != group:
                flag("CROSS_SECTION_MAPPING", sid=sid, fid=fid)
                continue
            mode = (rule.get("sign") or "keep").strip().lower()
            if mode not in SIGN_MODES:
                flag("UNAPPROVED_SIGN_MODE", sid=sid, fid=fid)
                continue
            try:
                part = number(rule.get("portion") or "1", name="portion", allow_zero=False)
            except ValueError:
                flag("INVALID_PORTION", sid=sid, fid=fid)
                continue
            if part <= 0 or part > 1:
                flag("PORTION_OUT_OF_RANGE", sid=sid, fid=fid)
                continue
            checked.append((fid, part, mode))
        if len(checked) != len(these):
            continue
        if sum((p for _, p, _ in checked), Decimal("0")) != 1:
            flag("SPLIT_NOT_100_PERCENT", sid=sid)
            continue
        for fid, portion, mode in checked:
            value = source_value * portion * SIGN_MODES[mode]
            sums[fid] += value
            trace.append({
                "source_id": sid,
                "field_id": fid,
                "source_amount_in_rupees": str(source_value),
                "portion": str(portion),
                "sign": mode,
                "allocated_amount": str(value),
            })
        mapped_sections[group] += source_value

    # A source must never disappear from the output simply because it was unmapped.
    for group, total in seen_sections.items():
        if mapped_sections[group] != total:
            flag("SOURCE_COVERAGE_DIFFERENCE", detail=f"{group}: {total - mapped_sections[group]}")

    for control in expected_totals or []:
        group = control.get("section", "").strip()
        try:
            expected = number(control.get("amount", ""), name="control amount")
        except ValueError:
            flag("INVALID_CONTROL", detail=group)
            continue
        if seen_sections[group] != expected:
            flag("SOURCE_CONTROL_MISMATCH",
                 detail=f"{group}: actual={seen_sections[group]} expected={expected}")

    output = [{
        "field_id": fid, "section": target_by_id[fid]["section"],
        "caption": target_by_id[fid].get("caption", ""),
        "amount": format(val, "f"),
    } for fid, val in sorted(sums.items())]
    return output, problems, trace


def ready_to_release(issues: list[dict[str, str]]) -> bool:
    """Strict release gate: any unresolved issue blocks the import-ready file."""
    return len(issues) == 0
