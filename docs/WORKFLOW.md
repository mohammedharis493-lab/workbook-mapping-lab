# Workbook mapping workflow

1. Read previous-year source data and its completed destination spreadsheet **privately**.
2. Propose mappings using captions, hierarchy, signs, amounts and historical treatment.
3. Require the reviewer to approve ambiguous or changed mappings.
4. Apply only approved rules to the current-year source.
   The Chrome review pins SHA-256 fingerprints of the selected financial
   statements, extraction profile, approved layout, prior rules and historical
   reference when extraction begins. It rechecks file contents when saving
   the reviewed mappings and immediately before building the copy; individual
   approval clicks do not repeatedly hash large workbooks. Any changed or missing
   input requires a fresh extraction and approval, even when its path is the
   same; changing the selected previous-year reference also resets the review.
5. Check target cell coordinates and anchor labels in the original blank template.
6. Validate formulas, existing values, merged cells, worksheet states and section totals.
7. Write an **unused separate copy** by replacing approved empty numeric cell XML only.
8. Verify all unmodified workbook package parts are byte-identical after extraction.
9. Reopen the produced file and recheck populated fields; do not edit the original workbook.
10. Perform the application's real import in a backed-up **test** record; re-export and compare the affected and unaffected fields.

No automatically generated file is deemed production-ready based solely on an offline simulator pass.

**Privacy:** Client templates, returns, mapping tables, values and reports are private and never belong in the public repository.
