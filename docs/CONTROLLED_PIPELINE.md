# Controlled spreadsheet mapping pipeline

The local application builds reviewed copies of structured destination workbooks. It is not a tax application and does not perform a live import.

## Completed features

1. Read source detail rows and explicitly approved mappings.
2. Perform decimal-precise unit conversion (rupees, thousands, lakhs, crores).
3. Aggregate several source accounts into one target field.
4. Split a source using portions which must sum to 100%.
5. Apply sign reversals only where approved.
6. Block new/unmapped/duplicate/cross-section/conflicting items.
7. Verify source controls and destination totals.
8. Verify assets equal liabilities when sections BS-A and BS-L are supplied.
9. Optionally round aggregated target amounts to whole rupees using half-up rounding and record differences.
10. Refuse output if any exception remains unresolved.
11. Write an unused COPY of a blank XLSX using only explicitly approved numeric cells.
12. Re-read the output and verify workbook content and unmodified package parts.

## Private CSV inputs

- Detailed source: source_id,section,caption,amount,unit
- Reviewed rules: source_id,field_id,approved,portion,sign
- Destination layout: field_id,section,sheet,cell,anchor_cell,anchor_text
- Source control totals: section,amount
- Expected output totals: section,total

Rules may have sign keep/reverse and portion 1 (default). A split requires its approved portions to sum exactly to 1. A new source without an approved destination remains an exception.

Keep authorised capital in a separate memorandum section if it is disclosed but should not be added to balance sheet paid-up share capital.

## Local execution

From the working directory, set PYTHONPATH to src and run:

python -m workbook_mapping_lab.pipeline --source PRIVATE_SOURCE.csv --rules PRIVATE_RULES.csv --layout PRIVATE_LAYOUT.csv --template PRIVATE_BLANK.xlsx --source-controls PRIVATE_SOURCE_CONTROLS.csv --output-controls PRIVATE_OUTPUT_CONTROLS.csv --rounding whole_rupees --output PRIVATE_OUTPUT.xlsx --exception-report PRIVATE_REPORT.json

Only private local paths should replace these placeholder names. On error, the detailed report is generated and no final workbook is released.

## Acceptance boundary

Offline PASS checks mappings, reconciliations and XLSX integrity, not compatibility with an external importer. Opening the output in Excel is an additional independent check. A controlled test import into a disposable record followed by re-export comparison remains necessary before using an external application in production.

No actual financial statements, identifying records, client amounts, template files, approvals or exception reports may be added to the public repository.
