"""Locate approved semantic destination fields within a real vendor export.

The export is immutable. This resolver writes only a private CSV which the
existing writer will use to patch existing numeric target cells. Ambiguous,
missing, occupied, hidden, or restructured destinations block output.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from .simulator import WorkbookSnapshot, _cell_key

LAYOUT_COLUMNS=("field_id","section","sheet","cell","anchor_cell","anchor_text")


def strict_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def resolve_layout(template_path: str, routes: list[dict]) -> dict:
    errors=[]
    output=[]
    seen_ids=set()
    seen_locations=set()

    with WorkbookSnapshot(template_path) as vendor:
        for route in routes:
            fid=route.get("field_id","").strip()
            section=route.get("section","").strip()
            sheet=route.get("sheet","").strip()
            caption=route.get("caption","").strip()
            anchor_col=(route.get("anchor_column") or "A").strip().upper()
            amount_col=(route.get("amount_column") or "B").strip().upper()
            if not fid or fid in seen_ids:
                errors.append({"code":"DUPLICATE_OR_BLANK_FIELD_ID","field_id":fid})
                continue
            seen_ids.add(fid)
            if not section or not sheet or not caption:
                errors.append({"code":"MISSING_ROUTE_DETAILS","field_id":fid})
                continue
            if len(anchor_col)>3 or not anchor_col.isalpha() or len(amount_col)>3 or not amount_col.isalpha():
                errors.append({"code":"INVALID_COLUMN","field_id":fid})
                continue
            if sheet not in vendor.sheets:
                errors.append({"code":"REQUIRED_VENDOR_SHEET_ABSENT","field_id":fid,"sheet":sheet})
                continue
            if vendor.sheets[sheet]["state"]!="visible":
                errors.append({"code":"REQUIRED_VENDOR_SHEET_HIDDEN","field_id":fid,"sheet":sheet})
                continue
            matches=[]
            for a,content in vendor.sheets[sheet]["cells"].items():
                if a.rstrip("0123456789")!=anchor_col:
                    continue
                if strict_label(content["value"])==strict_label(caption):
                    matches.append(a)
            if len(matches)!=1:
                errors.append({"code":"CAPTION_NOT_UNIQUE_OR_ABSENT",
                               "field_id":fid,"sheet":sheet,"count":len(matches)})
                continue
            anchor=matches[0]
            row_num=anchor[len(anchor_col):]
            address=amount_col+row_num
            if (sheet,address) in seen_locations:
                errors.append({"code":"DUPLICATED_TARGET_ADDRESS","field_id":fid})
                continue
            seen_locations.add((sheet,address))
            cell=vendor.cell(sheet,address)
            if cell["formula"]:
                errors.append({"code":"VENDOR_DESTINATION_IS_FORMULA","field_id":fid,"cell":address})
                continue
            if cell["value"].strip():
                errors.append({"code":"VENDOR_DESTINATION_OCCUPIED","field_id":fid,"cell":address})
                continue
            if vendor.merged_non_anchor(sheet,address):
                errors.append({"code":"VENDOR_DESTINATION_MERGED","field_id":fid,"cell":address})
                continue
            # The conservative writer requires an already-present, self-closing
            # blank cell element. Checking in advance avoids silent additions.
            import re
            part=vendor.sheets[sheet]["part_name"]
            raw=vendor.archive.read(part)
            addr=address.encode("ascii")
            pattern=re.compile(rb'<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?c\b[^>]*\br="'+re.escape(addr)+rb'"[^>]*/>')
            if len(pattern.findall(raw))!=1:
                errors.append({"code":"NO_EXISTING_BLANK_TARGET_CELL",
                               "field_id":fid,"cell":address})
                continue
            output.append({
                "field_id":fid, "section":section, "sheet":sheet,
                "cell":address, "anchor_cell":anchor,
                "anchor_text":vendor.cell(sheet,anchor)["value"],
            })

        return {
            "status":"READY" if not errors and len(output)==len(routes) else "BLOCKED",
            "count_requested":len(routes),
            "count_resolved":len(output),
            "template_sha256":vendor.sha256,
            "layout":output,
            "exceptions":errors,
            "principle":"Exact vendor-exported workbook; preserve all structural content and write only approved existing blank numeric cells.",
        }


def write_private_layout(report: dict, destination: str) -> None:
    if report["status"]!="READY":
        raise ValueError("Cannot export a partially resolved target layout")
    file=Path(destination).expanduser().resolve()
    project=Path(__file__).resolve().parents[2]
    if file==project or project in file.parents:
        raise ValueError("Never save client mapping data inside public project")
    if file.exists():
        raise FileExistsError("Layout already exists; refusing overwrite")
    file.parent.mkdir(parents=True,exist_ok=True)
    with file.open("w",newline="",encoding="utf-8") as target:
        wr=csv.DictWriter(target,fieldnames=LAYOUT_COLUMNS)
        wr.writeheader()
        wr.writerows(report["layout"])


def main() -> None:
    p=argparse.ArgumentParser(description="Match approved field captions inside ORIGINAL exported vendor workbook")
    p.add_argument("--template",required=True)
    p.add_argument("--routes",required=True)
    p.add_argument("--output-layout",required=True)
    a=p.parse_args()
    with open(a.routes,encoding="utf-8-sig",newline="") as stream:
        routes=list(csv.DictReader(stream))
    result=resolve_layout(a.template,routes)
    print(json.dumps({k:v for k,v in result.items() if k!="layout"},indent=2))
    if result["status"]!="READY":
        raise SystemExit(2)
    write_private_layout(result,a.output_layout)


if __name__=="__main__":
    main()
