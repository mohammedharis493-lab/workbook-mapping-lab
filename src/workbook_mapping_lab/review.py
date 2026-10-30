"""Local-only review state and safe export for a spreadsheet mapping GUI.

This module has no UI dependency so approval logic can be exercised headlessly.
Original workbooks, identifiers, notes and source values remain private.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .allocations import plan_allocations
from .fs_extract import canonical_caption


def require_private_directory(directory: str) -> Path:
    dest = Path(directory).expanduser().resolve()
    checkout = Path(__file__).resolve().parents[2]
    if dest == checkout or checkout in dest.parents:
        raise ValueError("Private working files may NOT be written inside the public repository")
    if dest == Path(dest.anchor):
        raise ValueError("Choose a dedicated private folder, not a filesystem root")
    dest.mkdir(parents=True, exist_ok=True)
    return dest


class ReviewSession:
    """Approval is explicit. Previously approved rules may be safely reused."""

    def __init__(self, rows: list[dict], issues: list[dict],
                 fields: list[dict], existing_rules: list[dict] | None = None,
                 suggestions: list[dict] | None = None):
        self.entries = {row["source_id"]: dict(row) for row in rows}
        if len(self.entries) != len(rows):
            raise ValueError("Duplicate extracted source IDs")
        self.layout = {f["field_id"]: dict(f) for f in fields}
        if len(self.layout) != len(fields):
            raise ValueError("Duplicate target field IDs")
        self.issues = [dict(i) for i in issues]
        self.rules: dict[str,list[dict]] = {}
        proposed = {x["source_id"]:x for x in (suggestions or [])}
        index = {}
        for rule in existing_rules or []:
            if rule.get("approved", "").strip().lower() in ("yes", "true", "1"):
                index.setdefault(rule.get("source_id", ""),[]).append(dict(rule))
        for sid, entry in self.entries.items():
            # If the new/old workbook comparison found a risk, the rule is
            # *suggested* but not approved for the new period.
            if entry.get("risk"):
                entry["review_status"]="NEEDS_REVIEW"
                hints=[x.get("field_id","") for x in index.get(sid,[])]
                if proposed.get(sid,{}).get("suggested_field_id"):
                    hints.append(proposed[sid]["suggested_field_id"])
                entry["target_hint"]=",".join(dict.fromkeys(hints))
                continue
            previous = index.get(sid,[])
            if len(previous)==1 and previous[0].get("field_id") in self.layout:
                rule=previous[0]
                if self.layout[rule["field_id"]].get("section")==entry["section"]:
                    self.rules[sid]=[{
                        "source_id":sid,
                        "field_id":rule["field_id"],
                        "approved":"yes",
                        "portion":rule.get("portion") or "1",
                        "sign":rule.get("sign") or "keep",
                    }]
                    entry["review_status"]="REUSED"
                    entry["target_hint"]=rule["field_id"]
                    continue
            guess=proposed.get(sid,{})
            hint=guess.get("suggested_field_id","")
            if hint and hint in self.layout and self.layout[hint].get("section")==entry["section"]:
                entry["review_status"]="SUGGESTED"
                entry["target_hint"]=hint
            else:
                entry["review_status"]="NEEDS_REVIEW"
                entry["target_hint"]=",".join(x.get("field_id","") for x in previous)

    def approve(self, source_id: str, field_id: str,
                *, portion: str="1", sign: str="keep",
                acknowledge_risks: bool=False) -> None:
        if source_id not in self.entries:
            raise ValueError("Source not present in current workbook")
        row=self.entries[source_id]
        if row.get("risk") and not acknowledge_risks:
            raise ValueError("Review and explicitly acknowledge the source risk flags")
        field=self.layout.get(field_id)
        if not field:
            raise ValueError("Destination field not in the reviewed template layout")
        if field.get("section","").strip()!=row["section"].strip():
            raise ValueError("Cannot map figures between different statement sections")
        from .allocations import number
        portion_number=number(portion,name="portion",allow_zero=False)
        if not (0 < portion_number <= 1):
            raise ValueError("Invalid allocation portion")
        if sign not in ("keep","reverse"):
            raise ValueError("Unapproved sign mode")
        self.rules[source_id]=[{
            "source_id":source_id,"field_id":field_id,"approved":"yes",
            "portion":str(portion_number),"sign":sign,
        }]
        row["review_status"]="APPROVED"
        row["target_hint"]=field_id

    def revoke(self, source_id: str) -> None:
        self.rules.pop(source_id,None)
        if source_id in self.entries:
            self.entries[source_id]["review_status"]="NEEDS_REVIEW"

    def unresolved(self) -> list[str]:
        return [sid for sid in self.entries if sid not in self.rules]

    def compiled(self) -> tuple[list[dict], list[dict], list[dict]]:
        return plan_allocations(
            [
                {k:r.get(k,"") for k in ("source_id","section","caption","amount","unit")}
                for r in self.entries.values()
            ],
            [r for group in self.rules.values() for r in group],
            list(self.layout.values()),
        )

    def save_review(self, directory: str, *, prefix: str="review") -> dict:
        base=require_private_directory(directory)
        if not prefix or not prefix.replace("_","").replace("-","").isalnum():
            raise ValueError("Invalid review prefix")
        src=base/(prefix+"_sources.csv")
        rules=base/(prefix+"_rules.csv")
        report=base/(prefix+"_exceptions.json")
        for f in (src,rules,report):
            if f.exists():
                raise FileExistsError(f"Refusing to overwrite an existing private file: {f.name}")
        outputs,exceptions,trace=self.compiled()
        # Global extraction errors (missing sheets, wrong year headers, etc.)
        # must never disappear from the release decision.
        external=[i for i in self.issues if not i.get("source_id") or i.get("source_id") in self.entries]
        global_errors=[i for i in external if not i.get("source_id")]
        exceptions.extend(global_errors)
        unresolved=self.unresolved()
        for sid in unresolved:
            exceptions.append({"issue":"PENDING_ACCOUNTANT_REVIEW","source_id":sid,"field_id":"","detail":self.entries[sid].get("risk","")})
        if unresolved:
            # Do not treat a successful partial mapping as a release-ready file.
            status="BLOCKED"
        else:
            status="PASS" if not exceptions else "BLOCKED"
        with src.open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=("source_id","section","caption","amount","unit"))
            w.writeheader()
            for row in self.entries.values():
                w.writerow({k:row.get(k,"") for k in w.fieldnames})
        with rules.open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=("source_id","field_id","approved","portion","sign"))
            w.writeheader()
            for group in self.rules.values():
                w.writerows(group)
        report.write_text(json.dumps({
            "status":status,"extracted":len(self.entries),
            "approved_rules":len(self.rules),
            "unresolved":unresolved,
            "exceptions":exceptions,
            "extraction_findings":external,
            "allocation_trace":trace,
            "mapped_field_count":len(outputs),
            "note":"Private review only; no target application import has been performed.",
        },indent=2),encoding="utf-8")
        return {"status":status,"sources":str(src),"rules":str(rules),"report":str(report)}
