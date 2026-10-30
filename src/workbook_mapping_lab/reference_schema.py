"""Read-only recovery of vendor field positions from an earlier native export.

The historical amounts are NOT used as current-year values. A proposed
coordinate remains unusable until the real target-year export contains
the same labelled and approved destination.
"""
from __future__ import annotations

from .mapping import load_csv
from .simulator import WorkbookSnapshot


def recover_native_reference_fields(previous_export: str, routes_file: str) -> list[dict]:
    routes=load_csv(routes_file,("field_id","section","sheet","caption"))
    findings=[]
    with WorkbookSnapshot(previous_export) as book:
        for route in routes:
            name=route["sheet"]
            label=route["caption"].strip().casefold()
            col=(route.get("anchor_column") or "A").strip().upper()
            target_col=(route.get("amount_column") or "B").strip().upper()
            field=route["field_id"]
            if name not in book.sheets:
                findings.append({"field_id":field,"status":"HISTORICAL_SHEET_ABSENT",
                                 "sheet":name})
                continue
            hits=[]
            for addr, item in book.sheets[name]["cells"].items():
                if not addr.startswith(col):
                    continue
                row=addr[len(col):]
                if row.isdigit() and " ".join(item["value"].casefold().split())==" ".join(label.split()):
                    hits.append(row)
            if len(hits)!=1:
                findings.append({"field_id":field,"status":"HISTORICAL_LABEL_MISSING_OR_AMBIGUOUS",
                                 "sheet":name,"match_count":len(hits)})
                continue
            row=hits[0]
            findings.append({
                "field_id":field,"status":"HISTORICAL_LABEL_FOUND",
                "sheet":name,"caption":route["caption"],
                "anchor_cell":col+row,
                "potential_amount_cell":target_col+row,
                "historical_values_reused":False,
                "warning":"Read-only historical layout reference; never substitute for a native current-year worksheet.",
            })
    return findings
