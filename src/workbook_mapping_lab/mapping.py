"""Deterministic, review-first FS → target workbook classification engine.

Operates only on local CSV extracts or synthetic fixtures. It does not connect to
target workbook, and mapping candidates always require an accountant's approval.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path


def load_csv(path: str, required: tuple[str, ...]) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(required) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        return [dict(row) for row in reader]


def save_csv(path: str, columns: tuple[str, ...], rows: list[dict]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def money(value: str | int | Decimal) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "").strip() or "0")
    except InvalidOperation as e:
        raise ValueError("Invalid monetary amount") from e


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def discover(previous_fs: list[dict], previous_target: list[dict]) -> list[dict]:
    """Suggest previous-year mappings; suggestions are never auto-approved."""
    result = []
    for src in previous_fs:
        candidates = []
        for field in previous_target:
            if normalized(src["section"]) != normalized(field["section"]):
                continue
            if money(src["amount"]) != money(field["amount"]):
                continue
            score = SequenceMatcher(
                None, normalized(src["caption"]), normalized(field["caption"])
            ).ratio()
            candidates.append((score, field["field_id"]))
        candidates.sort(reverse=True)
        if len(candidates) == 1:
            suggestion, status = candidates[0][1], "REVIEW_ONLY"
        elif candidates:
            suggestion, status = candidates[0][1], "AMBIGUOUS"
        else:
            suggestion, status = "", "UNMATCHED"
        result.append({
            "source_id": src["source_id"],
            "section": src["section"],
            "source_caption": src["caption"],
            "suggested_field_id": suggestion,
            "candidate_count": len(candidates),
            "status": status,
            "approved": "no",
        })
    return result


def apply(
    current_fs: list[dict], approved_rules: list[dict], target_fields: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Apply approved mappings only and report exceptions without guessing."""
    source_seen = set()
    field_ids = {r["field_id"] for r in target_fields}
    rules = defaultdict(list)
    exceptions = []
    for r in approved_rules:
        if r.get("approved", "").strip().lower() not in ("yes", "true", "1"):
            continue
        if r["field_id"] not in field_ids:
            exceptions.append({"issue": "TARGET_NOT_IN_TEMPLATE", "source_id": r["source_id"], "field_id": r["field_id"]})
            continue
        rules[r["source_id"]].append(r["field_id"])
    totals = defaultdict(lambda: Decimal("0"))
    for src in current_fs:
        sid = src["source_id"]
        if sid in source_seen:
            exceptions.append({"issue": "DUPLICATE_SOURCE_ID", "source_id": sid, "field_id": ""})
            continue
        source_seen.add(sid)
        targets = rules.get(sid, [])
        if len(targets) == 1:
            totals[targets[0]] += money(src["amount"])
        elif not targets:
            exceptions.append({"issue": "UNMAPPED_CURRENT_SOURCE", "source_id": sid, "field_id": ""})
        else:
            exceptions.append({"issue": "CONFLICTING_APPROVED_RULES", "source_id": sid, "field_id": ";".join(targets)})
    for sid in rules:
        if sid not in source_seen:
            exceptions.append({"issue": "PREVIOUS_SOURCE_DISAPPEARED", "source_id": sid, "field_id": ";".join(rules[sid])})
    target_index = {r["field_id"]: r for r in target_fields}
    output = [{
        "field_id": fid, "section": target_index[fid]["section"],
        "caption": target_index[fid]["caption"], "amount": str(val)
    } for fid, val in sorted(totals.items())]
    return output, exceptions


