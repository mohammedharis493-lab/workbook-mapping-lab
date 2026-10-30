"""Historical FS-to-target mapping suggestions; never self-approve.

Tolerates destination row shifts by matching field captions and rounded values
rather than copying previous cell coordinates. All real inputs stay local.
"""
from __future__ import annotations

import re
from decimal import Decimal
from difflib import SequenceMatcher

from .fs_extract import numeric
from .simulator import WorkbookSnapshot


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", value.lower())).strip()


def historic_targets(previous_workbook: str, layout: list[dict]) -> tuple[list[dict],list[dict]]:
    """Resolve new-year layout captions in the previous-year populated export."""
    resolved, issues = [], []
    with WorkbookSnapshot(previous_workbook) as previous:
        for field in layout:
            fid = field["field_id"]
            sheet = field["sheet"]
            if sheet not in previous.sheets:
                issues.append({"issue":"MISSING_PRIOR_TARGET_SHEET","field_id":fid})
                continue
            col_current=field["cell"].rstrip("0123456789").upper()
            label=norm(field["anchor_text"])
            sheet_info=previous.sheets[sheet]
            hits=[]
            for addr,cell in sheet_info["cells"].items():
                col=addr.rstrip("0123456789")
                row=addr[len(col):]
                if not row or col != field["anchor_cell"].rstrip("0123456789").upper():
                    continue
                if norm(cell["value"]) == label:
                    amount=numeric(previous.cell(sheet,col_current+row)["value"])
                    if amount is not None:
                        hits.append((addr,amount))
            if len(hits)==1:
                resolved.append({
                    "field_id":fid,"section":field["section"],
                    "caption":field.get("anchor_text",""),
                    "previous_amount":str(hits[0][1]),
                    "prior_cell":sheet+"!"+hits[0][0],
                })
            else:
                issues.append({
                    "issue":"PRIOR_TARGET_NOT_UNIQUE_OR_NOT_FOUND",
                    "field_id":fid, "count":str(len(hits)),
                })
    return resolved,issues


def propose_mappings(
    current_sources: list[dict], previous_target_workbook: str,
    new_layout: list[dict], *, tolerance: Decimal=Decimal("1"),
) -> tuple[list[dict],list[dict]]:
    """Suggest FS → field mapping with PY comparison, never approve or commit."""
    if tolerance < 0:
        raise ValueError("Tolerance cannot be negative")
    targets,issues=historic_targets(previous_target_workbook,new_layout)
    suggestions=[]
    for row in current_sources:
        sid=row["source_id"]
        py=numeric(row.get("previous_amount",""))
        if py is None:
            suggestions.append({"source_id":sid,"suggested_field_id":"",
                                "status":"NO_PRIOR_AMOUNT","confidence":"none","candidate_count":"0"})
            continue
        if py == 0:
            suggestions.append({"source_id":sid,"suggested_field_id":"",
                                "status":"ZERO_AMOUNT_REQUIRES_REVIEW","confidence":"none","candidate_count":"0"})
            continue
        candidates=[]
        for dest in targets:
            if dest["section"] != row["section"]:
                continue
            prior=Decimal(dest["previous_amount"])
            if abs(py - prior) > tolerance:
                continue
            score=SequenceMatcher(None,norm(row["caption"]),norm(dest["caption"])).ratio()
            candidates.append((score,dest))
        candidates.sort(key=lambda x:(-x[0],x[1]["field_id"]))
        if not candidates:
            status="UNMATCHED"
        elif len(candidates)==1:
            status="SUGGESTED_REVIEW_REQUIRED"
        elif len(candidates)>1 and candidates[0][0]-candidates[1][0] >= 0.20:
            status="AMBIGUOUS_WITH_TOP_CANDIDATE"
        else:
            status="AMBIGUOUS"
        suggestions.append({
            "source_id":sid,
            "suggested_field_id":candidates[0][1]["field_id"] if candidates else "",
            "status":status,
            "confidence":"review_only",
            "candidate_count":str(len(candidates)),
            "matching_prior_amount":(candidates[0][1]["previous_amount"] if candidates else ""),
        })
    return suggestions,issues
