# Warnings tab: independent, non-blocking accounting review

## Purpose

The application must **not** assume that a previous-year return is always
right. Earlier year input provides a useful mapping suggestion, but its
classification may have been wrong.

Historical discrepancies and unusual patterns belong in a separate
**Warnings (advisory)** tab. They are NOT changes to financial statements,
approved mapping rules, or filed returns.

The Warnings tab is intentionally separate from strict structural controls:
- **Advisory:** historical age classification differs from supporting FS;
  user may review, add a note, mark reviewed, or continue anyway.
- **Strict exception:** absent required worksheet, duplicate destinations,
  unapproved source row, broken balance-sheet tie-out. These errors still
  block a checked import copy because the output would not be technically
  complete or verifiable.

Warning acknowledgement has no effect on approval or output values.

## Default automatic ageing warning

When both prior-year FS and prior-year completed return are available and
their expected row captions are recognised:

1. Read four prior-year trade payable ageing buckets.
2. Calculate prior-year **over 1 year** = (1–2) + (2–3) + (>3).
3. Compare this with the value appearing under the historical return's
   *trade creditors outstanding for more than 1 year* heading.
4. If different, show the actual difference, source worksheet/cell
   references and a proposed review action.
5. Independently check prior-year note totals, heading units, and current
   year roll-forward evidence (where available).

For example, synthetic figures:
- PY FS less-than-one: 30
- PY FS over-one: 20 + 15 + 5 = 40
- PY ITR recorded under over-one: 70
- Advisory: over-one classification appears higher by 30.

The overall creditors balance can still be entirely correct.

The user should normally check original invoice ageing before accepting a
classification. This is **not** a legal determination.

## Desktop use

Open Workbook Mapping Lab, select the previous-year FS and populated
previous-year return, then click **Extract profile rows** or open the
**Warnings (advisory)** tab and select **Re-check evidence**.

In that tab:
- Select a warning to inspect sources, amounts and suggested action.
- Optional: type an explanation.
- Use **Mark reviewed (no changes)** to acknowledge an item.
- Use **Reopen warning** if further checking is necessary.
- Use **Export warnings privately** to keep a JSON record in the
  explicitly chosen private working folder.

Unacknowledged warnings do **not** disable the Build button, change
mapping approvals or edit any workbook.

## Extending the detection to other classifications

Optional JSON evidence rules, saved **privately**, enable other
cross-file comparisons without changing Python. For example:

    {
      "version": 1,
      "checks": [
        {
          "code": "SYNTHETIC_HISTORY_CHECK",
          "title": "Historical loan classification difference",
          "period": "Previous year",
          "severity": "Review",
          "source_kind": "previous_fs",
          "source_sheet": "Schedule",
          "source_cells": ["C9", "C10"],
          "target_kind": "previous_return",
          "target_sheet": "Borrowing details",
          "target_cell": "B7",
          "tolerance": "1",
          "explanation": "Supporting classification may differ from recorded value.",
          "suggested_action": "Inspect both schedules and prior-year treatment."
        }
      ]
    }

These sheet and cell references are invented, for illustration only.

The additional-rules file is selected under
**Sources -> Additional advisory checks (optional, .json)**.

The engine checks numeric values and emits an advisory if the difference
exceeds the configured tolerance. Missing evidence is reported as **Info**
rather than silently treated as a match. A check must be configured and
approved for the actual form/assessment year.

## Privacy and limitations

- All source workbooks and reports remain on the user's computer.
- No client names, amounts, screenshots or supporting files should be
  committed to the public project.
- The rule is evidence-based, not a guarantee of tax compliance.
- A previous-year classification difference must not be automatically
  carried forward to a new year.
- A checked import copy still requires accounting review and completeness
  checks independent of these advisory warnings.
