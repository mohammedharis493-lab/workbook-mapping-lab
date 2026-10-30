# Local review desk

The Windows review screen is optional. The mapping engine, controls and writer
can still run entirely from the command line.

## Starting the interface

From the repository directory:

    set PYTHONPATH=src
    python -m workbook_mapping_lab.review_gui

An optional --session PRIVATE_SESSION.json argument preloads local file paths.
Session files and entity-specific extraction profiles must **never** be added
to the public repository.

## Preparation

The screen asks for:
- Current-year financial statement XLSX
- Previous-year financial statement (optional)
- A **reviewed** source extraction profile
- Target blank-template field layout CSV
- Previous-year populated destination XLSX (optional)
- Existing approved mapping rules CSV (optional)
- A private working directory

It then identifies selected FS detail lines, compares historical values, and
displays prior-year mapping suggestions. Previously approved rules can be reused
when the source item is stable and has no unresolved exception. New suggestions
are deliberately never self-approved.

The review screen lets you:
1. Inspect each source caption, amount, historical amount and risk.
2. Confirm or change its target field within the same statement section.
3. Explicitly acknowledge a flagged change before approval.
4. Add newly discovered source rows using the scan dialog.
5. Export private source CSV, approved rules and exceptions.
6. Build a checked XLSX copy only when independent source/output controls
   reconcile and no exception remains.

All file exports and build reports remain local.

## Extraction profile

A version 1 profile contains a list of explicitly chosen data rows, together
with the label, current-year and prior-year columns. For example, using
**invented** worksheet names and locations:

    {
      "format": 1,
      "ranges": [{
        "sheet": "Statement",
        "section": "BS-A",
        "caption_column": "A",
        "current_column": "C",
        "previous_column": "D",
        "selected_rows": [8, 9, 12],
        "period_header_cell": "C3",
        "period_header_contains": "2026",
        "unit": "rupees"
      }],
      "watch_ranges": [{
        "sheet": "Statement",
        "caption_column": "A",
        "current_column": "C",
        "start_row": 7,
        "end_row": 14,
        "ignore_rows": [13, 14]
      }]
    }

Do not include both a subtotal and its component lines.

### New item detection

The optional watch_ranges detect **nonzero numeric lines** not in the
previously approved selected_rows, within declared scan regions. They are
released only after a person reviews them and updates the private profile.
Summaries excluded from the watch must be explicitly recorded using
ignore_rows.

New items **outside** watched ranges, and records that cannot be recognized
from workbook cells, are not guaranteed to be found. A reviewer must always
inspect the FS and ensure watched regions cover the required sections.

Formula-backed FS cells are noted as cached values. The system does not
independently recalculate them; FS and controls must be verified against a
trusted Excel recalculation or reviewed accounting statements.

## Boundaries

- The scanner uses read-only XLSX parsing and never evaluates macros.
- The GUI does not send files to GitHub or any external service.
- Personal information must not be committed as profiles, screenshots or
  exception logs.
- A checked copy is **not** an application-accepted return. Controlled import
  and independent re-export remain an acceptance test.
