# Workbook mapping workflow

1. Read previous-year source spreadsheet and its completed destination template locally.
2. Suggest mappings using captions, hierarchy, amounts, signs and historical treatment.
3. Require human approval for ambiguous or changed mappings.
4. Apply only approved rules to the current-year source.
5. Compare against the destination workbook shape and report missing fields.
6. For spreadsheet compatibility tests, validate anchor labels, empty target cells, formulas, merged cells and sheet visibility.
7. Later, populate a COPY of the real blank workbook with a dedicated adapter.
8. Reconcile/re-export and have the operator test the actual application.

**No public repo input should include real client data.**
Passing local simulation does NOT establish compatibility with a proprietary application's importer.
