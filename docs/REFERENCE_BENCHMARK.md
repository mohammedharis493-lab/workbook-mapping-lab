# Current-year reference benchmark (the primary acceptance test)

## Goal

Prove that the application correctly carries reviewed previous-year financial
statement classifications into the current-year destination spreadsheet.

### Data used

1. Previous-year FS and its completed prior-year destination workbook
   establish historical classification relationships and exceptions.
2. Current-year FS provides the amounts to map.
3. The current-year blank destination template provides field coordinates.
4. An independently **completed current-year** destination workbook is the
   benchmark for *classification and amount correctness*.

There is no reason to repeat manual third-party application imports for
every mapping iteration. The native template is the interface contract.
A one-time compatibility check can be deferred until mapping accuracy is proven.

### Core comparison

The tool compares configured fields using the caption in the destination
worksheet rather than relying solely on row numbers. It reports:
- exact matches,
- amount or classification mismatches,
- missing/ambiguous destination labels,
- missing generated or reference values,
- additional populated reference fields not covered by the layout.

This is an accounting mapping benchmark, **not** a tax return filing action.

Run with only PRIVATE local files, outside this repository:

    python -m workbook_mapping_lab.benchmark \
      --generated C:\private\generated_current.xlsx \
      --completed-reference C:\private\completed_current.xlsx \
      --layout C:\private\reviewed_layout.csv \
      --tolerance 0 \
      --report C:\private\benchmark_report.json

Only an independent, already-completed current-year export qualifies as
the reference. A blank template or copy of the generated workbook cannot
establish mapping correctness.

## Limitations

- A PASS applies only to the fields listed in the reviewed layout.
- Other populated fields in the reference are enumerated as coverage
  candidates but are not automatically declared correct or incorrect.
- A PY treatment is a suggestion, not a permanent accounting/tax rule.
- Extra schedules, changed disclosure requirements and zero-vs-blank
  distinctions still require professional review.
- The software does not modify the completed current-year return.
- Never publish real exports, company labels, values or detailed reports.

The full requirement is correctly classified **and** fully covered, not merely
equal Balance Sheet totals.
