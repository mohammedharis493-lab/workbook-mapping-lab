"""Review-first discovery of potential ITR fields in each native vendor export.

This module discovers *where* labels and safe blank amount destinations exist.
It cannot determine whether a field is tax-applicable; that is a human decision.
Only an explicit reviewed selection may be saved as an entity-specific profile.
No input workbook is modified and no client data is sent off localhost.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .entity_schema import APPLICABILITY, inspect_entity_profile
from .mapping import load_csv
from .review import require_private_directory
from .simulator import WorkbookSnapshot, CELL_REF, _cell_key

# Self-closing native target cells already required by the strict XLSX writer.
BLANK_TARGET = re.compile(
    rb'<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?c\b[^>]*\br="([A-Z]+[1-9][0-9]*)"[^>]*/>'
)
CANDIDATE_LIMIT = 2500
LABEL_COLUMN_LIMIT = 4   # A-D only; do not scan arbitrary value regions as labels.
LABEL_LENGTH = 160


def _to_column(n: int) -> str:
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _key(sheet: str, anchor: str, target: str) -> str:
    raw = "\x00".join((sheet, anchor, target)).encode("utf-8")
    return "CAND_" + hashlib.sha256(raw).hexdigest()[:15].upper()


def discover_entity_fields(template: str, layout_path: str = "",
                           *, limit: int = CANDIDATE_LIMIT) -> dict:
    """Enumerate safe label/blank-value pairs in an unmodified native XLSX.

    The returned list is *not* an applicability assessment or approved schema.
    An optional approved CSV can match existing field identities to rows but
    never copies previous entity's applicability choices.
    """
    if not isinstance(limit, int) or limit < 1 or limit > CANDIDATE_LIMIT:
        raise ValueError("Unsupported discovery candidate limit")
    native = Path(template)
    if native.suffix.lower() != ".xlsx":
        raise ValueError("Only native XLSX import exports can be scanned")
    prior = []
    if layout_path:
        prior = load_csv(layout_path, (
            "field_id", "section", "sheet", "cell", "anchor_cell", "anchor_text"
        ))
    matched = {}
    for item in prior:
        key = item["sheet"], item["anchor_cell"].upper()
        if key in matched:
            raise ValueError("Duplicate known label anchor in approved layout")
        matched[key] = item
    rows = []
    sheet_summary = []
    candidates_count = 0
    matched_count = 0
    with WorkbookSnapshot(native) as wb:
        for sheet, data in wb.sheets.items():
            if data["state"] != "visible":
                sheet_summary.append({
                    "sheet": sheet, "visibility": data["state"], "candidates": 0
                })
                continue
            xml = wb.archive.read(data["part_name"])
            native_empty = set(match.group(1).decode("ascii") for match in
                               BLANK_TARGET.finditer(xml))
            per_sheet = 0
            # Addresses have stable sheet/row ordering even when XML order
            # or vendor workbook sheet ordering differs.
            for anchor in sorted(data["cells"], key=_cell_key):
                label = data["cells"][anchor]
                if label["formula"] or not label["value"]:
                    continue
                column, row = CELL_REF.fullmatch(anchor).groups()
                column_id = _cell_key(anchor)[1]
                if column_id > LABEL_COLUMN_LIMIT or len(label["value"].strip()) > LABEL_LENGTH:
                    continue
                caption = " ".join(label["value"].split())
                if not caption or caption.replace(",", "").replace(".", "").replace("-", "").isnumeric():
                    continue
                # If existing known route uses a different target column,
                # prefer its independently approved coordinate.
                known = matched.get((sheet, anchor))
                options = ([known["cell"].upper()] if known else
                           [_to_column(column_id + offset) + row for offset in (1, 2)])
                for cell in options:
                    if cell not in native_empty or wb.merged_non_anchor(sheet, cell):
                        continue
                    candidates_count += 1
                    per_sheet += 1
                    if len(rows) >= limit:
                        break
                    unchanged_label = known and (
                        " ".join(known["anchor_text"].split()).casefold() ==
                        caption.casefold()
                    )
                    if unchanged_label:
                        matched_count += 1
                    rows.append({
                        "candidate_id": _key(sheet, anchor, cell),
                        "sheet": sheet, "caption": caption,
                        "anchor_cell": anchor, "amount_cell": cell,
                        "field_id": known["field_id"] if unchanged_label else _key(sheet, anchor, cell),
                        "section": known["section"] if unchanged_label else "",
                        "applicability": "review",
                        "selected": bool(unchanged_label),
                        "previous_layout_match": bool(unchanged_label),
                        "reviewed": False,
                        "anchor_column": column,
                        "amount_column": CELL_REF.fullmatch(cell).group(1),
                    })
                    break
                # If we reached the maximum number, continue counting
                # but never include silently omitted candidates in a saved
                # profile without an explicit manual review route.
            sheet_summary.append({
                "sheet": sheet, "visibility": "visible", "candidates": per_sheet
            })
        sha = wb.sha256
    return {
        "template_sha256": sha,
        "candidate_count": candidates_count,
        "returned_count": len(rows),
        "truncated": candidates_count > limit,
        "matched_existing_layout": matched_count,
        "sheets": sheet_summary,
        "candidates": rows,
        "warning": (
            "Fields are unapproved candidates, not automatically applicable. "
            "A missing optional sheet does not establish non-applicability. "
            "Review each chosen source mapping independently."
        ),
    }


def set_candidate_decision(
    discovery: dict,
    *,
    candidate_id: str,
    selected: bool,
    field_id: str = "",
    section: str = "",
    applicability: str = "review",
) -> dict:
    if not isinstance(selected, bool):
        raise ValueError("Selected must be explicitly true or false")
    if applicability not in APPLICABILITY:
        raise ValueError("Invalid applicability decision")
    field = next((f for f in discovery["candidates"]
                  if f["candidate_id"] == candidate_id), None)
    if field is None:
        raise ValueError("Unknown candidate; run discovery again")
    if selected:
        fid = field_id.strip()
        sect = section.strip()
        if not fid or not sect or len(fid) > 90 or len(sect) > 90:
            raise ValueError("Review the field ID and statement section first")
        if any(c in fid for c in "\r\n\t,") or any(c in sect for c in "\r\n\t"):
            raise ValueError("Invalid field/section characters")
        if applicability == "review":
            raise ValueError("Applicability must be decided before a field can be approved")
        field.update({
            "selected": True, "field_id": fid,
            "section": sect, "applicability": applicability, "reviewed": True,
        })
    else:
        field.update({
            "selected": False, "reviewed": False, "applicability": "review"
        })
    return field


def reviewed_profile(
    discovery: dict, *,
    entity_key: str,
    assessment_year: str,
    itr_form: str,
    native_template: str,
    layout_path: str = "",
) -> dict:
    for value in (entity_key, assessment_year, itr_form):
        if not isinstance(value, str) or not value.strip() or len(value) > 128:
            raise ValueError("Entity, assessment year and ITR form are required")
    if discovery["truncated"]:
        raise ValueError("Discovery exceeded safe candidate limit; review the extra fields manually")
    with WorkbookSnapshot(native_template) as wb:
        if wb.sha256 != discovery["template_sha256"]:
            raise ValueError("Template changed after discovery; start again")
    approved = [x for x in discovery["candidates"] if x["selected"]]
    if not approved:
        raise ValueError("Select and review at least one field")
    if any(not x["reviewed"] or x["applicability"] == "review" for x in approved):
        raise ValueError("All selected fields require explicit applicability review")
    ids = [x["field_id"] for x in approved]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate field IDs in reviewed selections")
    addresses = [(x["sheet"], x["amount_cell"]) for x in approved]
    if len(addresses) != len(set(addresses)):
        raise ValueError("Duplicate target amount address")

    if layout_path:
        layout = load_csv(layout_path, (
            "field_id", "section", "sheet", "cell", "anchor_cell", "anchor_text"
        ))
        chosen = {x["field_id"]: x for x in approved if x["applicability"] in ("required", "optional")}
        for row in layout:
            key = row["field_id"]
            found = chosen.get(key)
            if not found:
                raise ValueError("Approved mapping not represented by reviewed profile: " + key)
            if ((row["section"], row["sheet"], row["cell"], row["anchor_cell"]) !=
                (found["section"], found["sheet"], found["amount_cell"], found["anchor_cell"]) or
                " ".join(row["anchor_text"].split()).casefold() != found["caption"].casefold()):
                raise ValueError("Approved mapping and discovered source differ: " + key)

    fields = [{
        "field_id": x["field_id"], "section": x["section"],
        "sheet": x["sheet"], "caption": x["caption"],
        "anchor_column": x["anchor_column"],
        "amount_column": x["amount_column"],
        "applicability": x["applicability"],
    } for x in approved]
    profile = {
        "version": 1,
        "entity_key": entity_key.strip(),
        "assessment_year": assessment_year.strip(),
        "itr_form": itr_form.strip(),
        "template_sha256": discovery["template_sha256"],
        "fields": fields,
        "review_method": "individual_explicit_local_approval",
        "candidate_coverage": {
            "discovered": discovery["candidate_count"],
            "reviewed_selected": len(fields),
            "omitted": discovery["candidate_count"] - len(fields),
        },
        "warning": (
            "Only approved selections are included. Omitted candidates are "
            "not automatically not-applicable; verify FS, ledgers and statutory "
            "return requirements separately before relying on the profile."
        ),
    }
    result = inspect_entity_profile(
        native_template, profile,
        expected_entity_key=entity_key.strip(),
        expected_assessment_year=assessment_year.strip(),
        expected_itr_form=itr_form.strip()
    )
    if result["status"] != "READY_FOR_MAPPING_REVIEW":
        raise ValueError("Reviewed profile is not ready: " + result["status"])
    return profile


def save_private_profile(profile: dict, destination: str) -> str:
    path = Path(destination).expanduser().resolve()
    project = Path(__file__).resolve().parents[2]
    if path == project or project in path.parents:
        raise ValueError("Entity profile must never be saved inside a public repository")
    if path.suffix.lower() != ".json":
        raise ValueError("Private entity profile must be JSON")
    directory = require_private_directory(str(path.parent))
    target = directory / path.name
    with target.open("x", encoding="utf-8") as out:
        import json
        json.dump(profile, out, indent=2, ensure_ascii=False)
    return str(target)
