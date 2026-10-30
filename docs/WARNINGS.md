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

### Evidence-bound review decisions (M4.1)

The browser and legacy desktop review screen now bind each acknowledgement to
the exact source workbook/rule-file bytes and the warning's actual evidence,
period, amounts and explanation. Refreshing unchanged evidence preserves a
reviewer's note in the active session. Choosing another entity or evidence file,
changing a source file (even an unrelated cell), or changing a warning clears
the affected acknowledgement. A warning that disappears also loses its prior
decision. This prevents old reviews from silently applying to revised accounts.

Private JSON exports include an opaque evidence digest for audit traceability.
The ordinary **Export warnings privately** option is a report snapshot, not an
automatic approval source.

### Private cross-session review journal (M4.2)

In the Chrome Warnings tab, expand **Private review journal** after selecting
the entity, assessment year and ITR form under Build copy:

1. Refresh the original evidence and review the warnings.
2. Choose **Save review decisions** to create a new immutable-name JSON file
   in the configured private working folder. No source workbook is changed.
3. In a later session with the **same** entity, AY, ITR form and source files,
   paste the private journal path and choose **Load matching decisions**.
4. The app rechecks source bytes and warning fingerprints. A changed workbook,
   rule file, identity or warning list **rejects the entire restore**. Nothing
   is partially marked reviewed. The file must be inside the private folder.

The journal contains the exact-evidence SHA-256, warning identifiers, review
notes and acknowledged flags. It contains no authorization to approve a mapping,
modify a workbook, submit an ITR or suppress a blocking exception. Locally
editable JSON is a convenience for review continuity, not authenticated audit
sign-off. The older Tkinter review interface still offers report export but not
journal import; its decisions remain session-only.

## Default automatic ageing warning

When both prior-year FS and prior-year completed return are available and
their expected row captions are recognised:

1. Read four prior-year creditor ageing buckets from the FS.
2. Calculate over one year = (1-2 years) + (2-3 years) + (>3 years).
3. Confirm both separately labelled native export rows:
   - Creditors!A4/B4: Trade Creditors outstanding over one year.
   - Creditors!A5/B5: Others.
4. Compare B4 with the FS over-one-year amount and B5 with the
   independently reviewed under-one-year remainder, subject to verifying
   that the 'Others' classification is appropriate for the form version.
5. Show the exact differences and supporting sheet/cell references;
   never treat a value in B5 as if it were entered on B4.

For example, synthetic figures:
- PY FS less than one year: 30.
- PY FS over one year: 20 + 15 + 5 = 40.
- PY Winman export B4 (over one year): blank/0.
- PY Winman export B5 (Others): 70.
- Advisory: over-one-year entry is lower by 40; Others is higher by 40.

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

### Per-cell provenance and period safety (M4.3a)

For an additional reviewer-configured comparison, the warning now lists **each**
numeric source cell separately, its source worksheet and workbook role, the
recorded target cell, the source and target financial periods, and the exact
nonnegative tolerance. `difference` is defined as **target minus sum of source
cells**; a warning is emitted only when `abs(difference) > tolerance`. No unit
conversion, scaling or applicability determination is inferred.

`source_kind` and `target_kind` determine the period label (`Previous year`,
`Current year`, or `Previous year to Current year` / the reverse). The optional
`period` property must match that derived label, to avoid a misleading review
of data from different periods. If a workbook, sheet or amount is missing, the
warning stays **Info / unverified** and retains the expected, *unverified*
source and target sheet/cell coordinates and tolerance—never a presumed zero.

These checks remain opt-in rules maintained privately for the actual entity,
ITR form and AY. Synthetic ITR-3/ITR-6 layouts in regression tests are not
claims about vendor layout or a shared set of applicable fields. Because the
finding's provenance and tolerance are part of its fingerprint, older review
journals may require fresh review after updating the app; no earlier
acknowledgement is silently transferred.

## Privacy and limitations

- All source workbooks and reports remain on the user's computer.
- No client names, amounts, screenshots or supporting files should be
  committed to the public project.
- The rule is evidence-based, not a guarantee of tax compliance.
- A previous-year classification difference must not be automatically
  carried forward to a new year.
- A checked import copy still requires accounting review and completeness
  checks independent of these advisory warnings.
