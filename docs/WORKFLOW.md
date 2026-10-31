# Workbook mapping workflow

1. Read previous-year source data and its completed destination spreadsheet **privately**.
2. Propose mappings using captions, hierarchy, signs, amounts and historical treatment.
3. Require the reviewer to approve ambiguous or changed mappings.
4. Apply only approved rules to the current-year source.
   Before any Chrome, Classic desktop or CLI checked-copy build, verify this
   entity's privately reviewed schema against its actual current native
   export and approved destination layout. Do not reuse another entity's
   profile, and do not guess optional or conditional schedules.
   The Chrome review pins SHA-256 fingerprints of the selected financial
   statements, extraction profile, approved layout, prior rules and historical
   reference when extraction begins. It rechecks file contents when saving
   the reviewed mappings and immediately before building the copy; individual
   approval clicks do not repeatedly hash large workbooks. Any changed or missing
   input requires a fresh extraction and approval, even when its path is the
   same; changing the selected previous-year reference also resets the review.
   The Classic desktop review likewise binds the six selected review-input
   paths and their contents at extraction, then checks them before private
   approval export, before building and immediately before checked-copy release.
   In-place file changes or selected-path substitutions invalidate prior approvals.
   If evidence changes during a Classic export, that attempt's newly generated
   private review files are discarded so a stale PASS approval report does not
   remain available to other build entry points.
   During a checked-copy build, the Chrome, Classic and CLI entry points pin
   their selected file contents and revalidate them just before publishing;
   the writer also independently pins its immediate template, layout, values
   and controls. Any detected in-flight change blocks release. The verified
   completed file is published with an atomic no-overwrite hard link, so a
   concurrently occupied output filename cannot be silently replaced.
5. Check target cell coordinates and anchor labels in the original blank template.
6. Validate formulas, existing values, merged cells, worksheet states and section totals.
7. Write an **unused separate copy** by replacing approved empty numeric cell XML only.
8. Verify all unmodified workbook package parts are byte-identical after extraction.
9. Reopen the produced file and recheck populated fields; do not edit the original workbook.
10. Perform the application's real import in a backed-up **test** record; re-export and compare the affected and unaffected fields.

No automatically generated file is deemed production-ready based solely on an offline simulator pass.
The content checks are not a cross-process filesystem lock: highly adversarial
changes within the final micro-window are not excluded. Where hard links are
unsupported, publication fails closed; choose a compatible private filesystem.
The private build report is not marked PASS until the verified copy has been
released successfully. A writer failure records BLOCKED, without logging raw
paths or private error details.

**Privacy:** Client templates, returns, mapping tables, values and reports are private and never belong in the public repository.
