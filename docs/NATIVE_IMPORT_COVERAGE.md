# Native Winman import destination coverage — milestone M3 evidence check

## Scope and evidence distinction

A completed return exported from Winman (for example an ITR-6 XLSM workbook) can contain detailed Balance Sheet/P&L values on hidden reference worksheets. It **is not** proof that the separate **native import-format XLSX** offers corresponding writable destination cells.

This check independently assesses each field in a *privately approved comparison contract*:

1. Original/current-year **blank Winman import-format XLSX** — verify its actual native worksheet, exact label and pre-existing blank numeric destination. Never create a missing worksheet.
2. **Independently completed ITR workbook** — verify an exact labelled value, including a hidden reference sheet only with an approved label cell.
3. **Reviewed FS amount** in the private comparison contract — independently compare the completed-return value to that amount. Equal totals alone do not establish correct classification.

Only configured fields are assessed. An empty or omitted field is not assumed not applicable.

## Chrome workflow

Open **Build copy → Check native import field coverage**.

Specify the original template in **Build copy**, and the independently completed return plus reviewed contract under **Compare with completed ITR**. To inspect a *new* vendor-exported XLSX without changing the selected official template, provide it in the optional replacement-path field and choose **Check import destinations**.

The app shows each field's native destination availability, completed-return figure status and separate accountant-review verdict. The report is written as a new timestamped JSON file in the private working folder and the original inputs remain byte-for-byte unchanged.

Even when every target exists, this is **READY_FOR_ACCOUNTANT_MAPPING_REVIEW**, not automatic classification, return submission or import verification.

The application does **not** assume that an XLSM completed return can be imported into Winman. If a genuinely required detail is absent from the XLSX, an accountant can verify Winman's native export options and, where appropriate, use **independent direct entry or the vendor's Trial Balance/B/S tool**; this is a separate supervised process. There is no invented worksheet, automatic filing or unverified vendor feature claim.

## Status and blockers

- **READY_FOR_ACCOUNTANT_MAPPING_REVIEW**: every configured native destination exists and all completed-return reference amounts match the reviewed FS figures.
- **BLOCKED_NATIVE_IMPORT_TARGETS**: one or more configured native destinations are missing, duplicated, formula cells, occupied, merged or lack an original blank target.
- **NEEDS_REFERENCE_REVIEW**: all native targets exist but the independently completed reference amount or exact label fails comparison.
- Per-field statuses distinguish exact native cell readiness, native exceptions, reference mismatches, and unavailable import destinations.

A complete original vendor export is still necessary to write every configured field through this precise Excel import pathway. Read-only evidence reports cannot replace it.

## Actual AY 2026–27 Builders observation (private evidence only)

The independently completed return supports all **13** configured reviewed figures. The native 16-sheet import XLSX contains **9** valid configured writable cells; four detail fields cannot be placed because the three corresponding detailed worksheets are absent. Do **not** copy the client-specific monetary amounts or private paths into the public repository.

## Technical components

- Read-only diagnostic: `src/workbook_mapping_lab/import_intake.py`
- Local browser endpoint and private JSON report: `review_browser.py`
- Accessible collapsed table: `review_browser.html` / `review_browser.js`
- Deterministic acceptance: `tests/test_import_intake.py` and `tests/test_browser_workflow.py`

The checker uses the existing strict `resolve_layout`, `WorkbookSnapshot` and `manual_benchmark.find_field`. The original exact-structure Excel writer and accountant-approval gate are unchanged.
