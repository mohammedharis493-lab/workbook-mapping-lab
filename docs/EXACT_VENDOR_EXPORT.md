# Exact exported-template handling

## Non-negotiable rule

Use the exact XLSX workbook exported by the destination application for
the **intended year**. Never rebuild its worksheet structure, names,
styles, formulas, relationships, or supplementary tables.

The writer:
- accepts only a separate, unused output filename;
- patches previously existing, blank, approved numeric cell elements;
- requires exact approved label anchors;
- preserves untouched package XML and metadata;
- refuses modification of formulas, merged non-anchor cells, occupied targets,
  macro-enabled workbooks, external links or digitally signed packages;
- verifies every new amount and all unchanged ZIP package parts.

An exact format is **not** the same as an exact byte-for-byte copy: the approved
numeric values must change. Other package members remain byte-identical
when decompressed, and the only changed worksheet XML is the designated
blank-cell value elements.

## Conditional detailed sub-schedules

A vendor may export a short workbook when sub-schedules are not activated.

Check the historical used sub-schedules against the current template:

    python -m workbook_mapping_lab.template_contract \
      --previous-export PRIVATE_PREVIOUS_EXPORT.xlsx \
      --current-template PRIVATE_CURRENT_EXPORT.xlsx

The program reports missing previously used detail sheets and stops. Do not
copy prior-year sheets into the current template or replace detailed
classification with a broad parent field merely to pass the test.

## Exact semantic route resolution

Private, approved route CSV fields:

    field_id,section,sheet,caption,anchor_column,amount_column

For detailed BS rows, use section BS-L-DETAIL; parent Balance Sheet rows use
BS-L. The route resolver finds caption locations in the actual current-year
export; it follows row movements and refuses missing, ambiguous, occupied or
unexpected targets.

    python -m workbook_mapping_lab.layout_resolver \
      --template PRIVATE_CURRENT_EXPORT.xlsx \
      --routes PRIVATE_APPROVED_ROUTES.csv \
      --output-layout PRIVATE_EXACT_LAYOUT.csv

The desktop GUI's Resolve detailed fields action can merge the resolved
detail rows into a previously reviewed full mapping layout. It never modifies
the vendor source workbook.

## Parent totals and detail values

Some vendor exports contain a main parent figure as well as one or more
sub-schedule entries that explain that same balance.

Use a separate PRIVATE CSV with columns:

    parent_field_id,detail_field_id,amount

The full pipeline checks that all children for a parent sum exactly to the
mapped parent amount, after the approved rounding policy. The child values are
emitted into the original vendor workbook but do not inflate the total in
section controls.

    python -m workbook_mapping_lab.pipeline \
      --source PRIVATE_SOURCE.csv \
      --rules PRIVATE_APPROVED_RULES.csv \
      --layout PRIVATE_EXACT_LAYOUT.csv \
      --template PRIVATE_CURRENT_EXPORT.xlsx \
      --source-controls PRIVATE_FS_CONTROLS.csv \
      --output-controls PRIVATE_RETURN_CONTROLS.csv \
      --previous-export PRIVATE_PREVIOUS_EXPORT.xlsx \
      --companion-details PRIVATE_CHILD_AMOUNTS.csv \
      --rounding whole_rupees \
      --output PRIVATE_CHECKED_COPY.xlsx \
      --exception-report PRIVATE_REPORT.json

This covers the *technical* mapping and preservation requirement. It does not
establish that a historical accounting classification is correct in the new
year. An independent completed return, current FS and reviewer-approved
exceptions remain the acceptance benchmark.

## Failure cases

The program must block rather than claim a complete import copy when:
- a historically used detail sheet is absent;
- a newly required field has not been configured;
- a caption occurs in more than one location;
- an existing target is occupied or is a formula;
- the current and prior exports are identical files;
- a child amount does not reconcile to its parent;
- FS totals, return totals or rounding controls differ;
- a source item requires accounting approval.

No real client workbook or report may be committed to this repository.
