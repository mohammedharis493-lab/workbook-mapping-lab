"""Explicit, private, evidence-bound storage for advisory review decisions.

These notes are never accounting approvals and cannot authorize a build.
Journal files are untrusted local JSON: strict identity/evidence validation
precedes any restoration of acknowledgement state.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .advisories import warning_review_key
from .review import require_private_directory

SCHEMA = "workbook-mapping-lab.warning-review-journal/v1"
IDENTITY_KEYS = ("entity_key", "assessment_year", "itr_form")
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 1024 * 1024


def reviewed_identity(config: dict) -> dict[str, str]:
    identity = {key: str(config.get(key, "")).strip() for key in IDENTITY_KEYS}
    if any(not value or len(value) > 180 for value in identity.values()):
        raise ValueError("Choose an entity identifier, assessment year and ITR form before saving or loading warning reviews")
    return identity


def _warning_keys(warnings: list[dict], signature: str) -> list[str]:
    if not HEX_SHA256.fullmatch(signature):
        raise ValueError("Refresh exact evidence before handling a review journal")
    if len(warnings) > 500:
        raise ValueError("Too many warnings for a review journal")
    keys = [warning_review_key(item, signature) for item in warnings]
    if len(keys) != len(set(keys)):
        raise ValueError("Cannot save ambiguous duplicate warning identities")
    return sorted(keys)


def save_journal(private_folder: str, identity: dict, signature: str,
                 warnings: list[dict], decisions: dict[str, dict]) -> dict:
    """Create one new private JSON snapshot; originals remain untouched."""
    identity = reviewed_identity(identity)
    known = _warning_keys(warnings, signature)
    if any(key not in known for key in decisions):
        raise ValueError("Refresh evidence; a reviewer decision refers to an old warning")
    records = []
    for key in sorted(decisions):
        decision = decisions[key]
        note = str(decision.get("reviewer_note", ""))
        if len(note) > 600:
            raise ValueError("Reviewer note exceeds 600 characters")
        records.append({"warning_key": key,
                        "acknowledged": decision.get("acknowledged") is True,
                        "reviewer_note": note})
    document = {
        "schema": SCHEMA,
        "entity": identity,
        "evidence_sha256": signature,
        "warning_keys": known,
        "decisions": records,
        "meaning": "Non-blocking advisory notes; never mapping or filing approval",
    }
    directory = require_private_directory(private_folder)
    destination = directory / ("warning_reviews_PRIVATE_" +
                               datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
    with destination.open("x", encoding="utf-8") as output:
        json.dump(document, output, indent=2, ensure_ascii=False)
    return {"path": str(destination), "decision_count": len(records)}


def load_journal(path: str, private_folder: str, identity: dict,
                 signature: str, warnings: list[dict]) -> dict[str, dict]:
    """Validate everything before returning decisions; no partial restore."""
    identity = reviewed_identity(identity)
    known = _warning_keys(warnings, signature)
    directory = require_private_directory(private_folder)
    target = Path(path).expanduser().resolve(strict=True)
    if directory not in target.parents or target.suffix.casefold() != ".json":
        raise ValueError("Select a JSON review journal inside the configured private folder")
    if target.stat().st_size > MAX_BYTES:
        raise ValueError("Private review journal exceeds the 1 MiB limit")
    document = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError("Unrecognised private review journal version")
    if document.get("entity") != identity:
        raise ValueError("Journal entity, assessment year or ITR form does not match this session")
    if document.get("evidence_sha256") != signature:
        raise ValueError("Journal evidence changed: review the new source files independently")
    if document.get("warning_keys") != known:
        raise ValueError("Journal warning findings have changed since the saved review")
    rows = document.get("decisions")
    if not isinstance(rows, list) or len(rows) > len(known):
        raise ValueError("Invalid journal decisions")
    restored = {}
    for row in rows:
        if (not isinstance(row, dict) or
            set(row) != {"warning_key", "acknowledged", "reviewer_note"}):
            raise ValueError("Invalid journal decision record")
        key = row["warning_key"]
        note = row["reviewer_note"]
        if (not isinstance(key, str) or key not in known or key in restored or
            type(row["acknowledged"]) is not bool or
            not isinstance(note, str) or len(note) > 600):
            raise ValueError("Journal contains stale, duplicate or invalid warning decisions")
        restored[key] = {"acknowledged": row["acknowledged"],
                         "reviewer_note": note}
    return restored
