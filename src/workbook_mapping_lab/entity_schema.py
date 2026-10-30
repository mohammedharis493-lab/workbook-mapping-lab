"""Entity-and-assessment-year-specific ITR workbook schema contract.

A statutory ITR form can contain different applicable schedules, sections
and subcomponents for different entities. The native exported workbook,
not a previous client's profile, is the source of field locations.

A schema profile is PRIVATE. This module reads, validates and compares it
against the exact target workbook; it never modifies the original file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .layout_resolver import resolve_layout
from .simulator import WorkbookSnapshot

APPLICABILITY = frozenset(("required", "optional", "not_applicable", "review"))
ROUTE_KEYS = ("field_id", "section", "sheet", "caption")


def load_entity_profile(path: str) -> dict:
    item = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(item, dict) or item.get("version") != 1:
        raise ValueError("Invalid private entity ITR schema profile version")
    for key in ("entity_key", "assessment_year", "itr_form", "template_sha256"):
        if not isinstance(item.get(key), str) or not item[key].strip():
            raise ValueError("Entity profile missing " + key)
    if not isinstance(item.get("fields"), list) or not item["fields"]:
        raise ValueError("Entity profile must declare reviewed field definitions")
    if len(item["fields"]) > 3000:
        raise ValueError("Entity profile has too many fields")
    seen = set()
    for field in item["fields"]:
        if not isinstance(field, dict) or any(
            not isinstance(field.get(key), str) or not field[key].strip()
            for key in ROUTE_KEYS
        ):
            raise ValueError("Profile contains a field without a label, section or destination")
        field_id = field["field_id"].strip()
        if field_id in seen:
            raise ValueError("Duplicate field in entity profile: " + field_id)
        seen.add(field_id)
        if field.get("applicability") not in APPLICABILITY:
            raise ValueError("Unreviewed or unsupported applicability for " + field_id)
    return item


def inspect_entity_profile(
    template: str,
    profile: dict,
    *,
    expected_entity_key: str,
    expected_assessment_year: str,
    expected_itr_form: str,
) -> dict:
    """Validate identity, year, native template and each configured field.

    Different entities or assessment years are never silently interchangeable.
    A prior-year profile is NOT approved for the current year even if labels
    happen to coincide. The current-year exact original export is immutable.
    """
    for key, actual in (
        ("entity_key", expected_entity_key),
        ("assessment_year", expected_assessment_year),
        ("itr_form", expected_itr_form),
    ):
        if not actual or profile.get(key) != actual:
            raise ValueError("ENTITY_SCHEMA_IDENTITY_OR_YEAR_MISMATCH: " + key)
    with WorkbookSnapshot(template) as book:
        template_hash = book.sha256
    if profile.get("template_sha256") != template_hash:
        raise ValueError(
            "ENTITY_TEMPLATE_CHANGED: re-discover the current export and re-review mappings"
        )

    # Each route is matched to the native template independently. Optional
    # absence should not make a different entity appear to have an error.
    matches = []
    blocking = []
    notices = []
    applicability_pending = []
    for field in profile["fields"]:
        applicability = field["applicability"]
        fid = field["field_id"]
        if applicability == "not_applicable":
            continue
        if applicability == "review":
            applicability_pending.append({
                "field_id": fid, "code": "APPLICABILITY_NEEDS_REVIEW",
                "description": "Decide whether this subcomponent applies to this entity.",
            })
            continue
        result = resolve_layout(template, [field])
        if result["status"] == "READY":
            matches.extend(result["layout"])
        else:
            for issue in result["exceptions"]:
                record = {
                    "field_id": fid, "code": issue["code"],
                    "sheet": field["sheet"], "applicability": applicability,
                }
                if applicability == "required":
                    blocking.append(record)
                else:
                    notices.append(record)
    target_addresses = [(record["sheet"], record["cell"]) for record in matches]
    if len(target_addresses) != len(set(target_addresses)):
        blocking.append({"code": "DUPLICATED_ENTITY_DESTINATION_CELL"})
    status = (
        "BLOCKED_REQUIRED_FIELD" if blocking
        else "NEEDS_APPLICABILITY_REVIEW" if applicability_pending
        else "READY_FOR_MAPPING_REVIEW"
    )
    return {
        "status": status,
        "entity_key": profile["entity_key"],
        "assessment_year": profile["assessment_year"],
        "itr_form": profile["itr_form"],
        "template_sha256": template_hash,
        "configured_fields": len(profile["fields"]),
        "resolved_fields": len(matches),
        "candidate_layout": matches,
        "blocking_exceptions": blocking,
        "optional_field_notices": notices,
        "applicability_review": applicability_pending,
        "source_workbooks_modified": False,
        "warning": (
            "A ready schema is not a tax compliance approval. Each approved mapping "
            "still requires accounting evidence, control totals and source review. "
            "Do not assume another entity's assets, liabilities or subcomponents."
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser(
        description="Read-only per-entity Winman workbook schema validation"
    )
    p.add_argument("--template", required=True)
    p.add_argument("--profile", required=True)
    p.add_argument("--entity-key", required=True)
    p.add_argument("--assessment-year", required=True)
    p.add_argument("--itr-form", required=True)
    args = p.parse_args()
    profile = load_entity_profile(args.profile)
    result = inspect_entity_profile(
        args.template, profile,
        expected_entity_key=args.entity_key,
        expected_assessment_year=args.assessment_year,
        expected_itr_form=args.itr_form,
    )
    # Never print client row values to the public repository.
    print(json.dumps({k: v for k, v in result.items() if k != "candidate_layout"},
                     indent=2))
    if result["status"] != "READY_FOR_MAPPING_REVIEW":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
