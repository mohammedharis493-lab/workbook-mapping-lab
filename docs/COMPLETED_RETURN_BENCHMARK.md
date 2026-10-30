# Independent completed-return benchmark

## Purpose

The current-year target spreadsheet must be an **original vendor-exported template**.
The app does not recreate missing sheets or infer unseen field locations.

A manually completed ITR-6 may be stored as a different XLSM workbook, often
with Balance Sheet and Profit & Loss Account on hidden worksheets. The
reference benchmark compares two *different* Excel layouts using a
reviewed, private field contract.

This process is **read-only** for both inputs; an approved, private JSON
report is written to the selected private working folder.

## Required private contract (CSV)

Columns:

- `field_id`: unique accounting field identity
- `expected_amount`: independently reviewed current-year FS amount (not
  simply copied from the manual tax return)
- `generated_sheet`: sheet required in the original exported import workbook
- `generated_label`: exact field caption required there
- `generated_value_col`: amount column letter
- `manual_sheet`: independently completed return workbook's sheet
- `manual_label`: exact field caption there
- `manual_value_col`: completed return's amount column letter
- `manual_label_cell`: optional, *strongly recommended* approved coordinate
  for an exact label; **mandatory** when the completed reference sheet is hidden
- `generated_label_cell`: optional approved generated-template coordinate

Example with imaginary labels/amounts:

    field_id,expected_amount,generated_sheet,generated_label,generated_value_col,manual_sheet,manual_label,manual_value_col,manual_label_cell
    CREDITOR,123,Detail liabilities,Over one year,B,Reference BS,Old trade creditors,E,A19

This is an illustration, not a vendor-form definition.

## Checks

For every configured field:

1. Locate the exact caption and its amount in the generated import workbook.
2. Locate the approved reference caption in the manual return. For hidden
   sheets, the approved anchor must match exactly.
3. Independently compare both figures with the reviewed FS amount.
4. Compare the two amounts directly; distinguish missing fields, ambiguous
   captions, changed anchors, nonnumeric cells and numeric discrepancies.
5. Report match/exception counts and the exact evidence used.

Equal BS or P&L totals alone never establish field classification accuracy.

When a generated sheet is missing, the result is a **coverage blocker**.
Do not substitute a broad Balance Sheet parent field merely because its
numeric total matches a detailed field.

## Browser workflow

In Chrome, open **Build copy → Compare with completed ITR**.

Select the generated import-format workbook, completed reference workbook
(XLSM or XLSX), and reviewed private comparison contract.

Run **Compare fields**. Results are shown in a table without altering the
original workbooks, previous-year mappings, import copies or Winman itself.

The report is a versioned file under the private working folder and never
belongs in the public source repository.

## Known limitations

- Completeness is relative to the reviewed contract. Unconfigured fields
  remain outside the benchmark, and require separate coverage review.
- A completed historical or current ITR might itself contain errors.
- The app cannot automatically invent or activate missing native detail
  worksheets; they must be exported from the target application.
- Hidden reference worksheets can be read only with an approved label anchor.
  The actual import writer still blocks writing into hidden target sheets.
- XLSM files are treated strictly as inert ZIP/XML data; macros are not run.
