# Offline workbook import simulator

The simulator reads a real exported spreadsheet template **without changing it**.
It emulates a field-level import and re-export in memory, and independently
compares a spreadsheet already filled by a separate process.

This is a **compatibility test harness**, not a copy of a proprietary importer.
Its PASS status cannot prove the target program will accept the workbook.

## Capabilities

- Inventory all worksheet names, visibility, cell counts, formulas and merges.
- Compare prior-year and current-year worksheet structures, flag missing tabs.
- Validate explicit field coordinates against the expected label.
- Refuse to target missing/hidden sheets, non-leading merged cells, formulas,
  nonempty cells, duplicated fields, or unexpected workbook sections.
- Validate mapped amounts and section-level reconciliation totals.
- Emulate a round-trip import/re-export entirely in memory.
- Compare values in an externally filled workbook and block loss of workbook
  metadata, styles, original labels, formulas or static cells.
- Emit a private machine-readable JSON report with error codes and fingerprints.
- Never connect to or modify the target accounting program.

## Run

On Windows, from the repository directory:

\`\`\`powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest discover -s tests -v
python -m workbook_mapping_lab.simulator inspect --template "C:\private\blank.xlsx" --previous "C:\private\previous.xlsx"
python -m workbook_mapping_lab.simulator simulate --template "C:\private\blank.xlsx" --layout "C:\private\layout.csv" --values "C:\private\mapped.csv" --controls "C:\private\controls.csv" --report "C:\private\simulation.json"
python -m workbook_mapping_lab.simulator compare --template "C:\private\blank.xlsx" --filled "C:\private\filled-copy.xlsx" --layout "C:\private\layout.csv" --values "C:\private\mapped.csv" --controls "C:\private\controls.csv" --report "C:\private\comparison.json"
\`\`\`

The CSV files are **private local files**. Do not copy them to this repository.

\`layout.csv\` columns:
\`field_id,section,sheet,cell,anchor_cell,anchor_text\`.

\`mapped.csv\` columns:
\`field_id,section,amount\`.

\`controls.csv\` columns:
\`section,total\`. Controls should represent the **same subset of mapped fields**,
not an unrelated full Balance Sheet total.

## Interpretation

- \`PASS / mock-import\`: the mapped values could be applied to a virtual copy
  at the declared coordinates with no detected structural issue.
- \`PASS / filled-workbook-compare\`: values and conservative workbook invariants
  matched after another process populated a separate copy.
- \`BLOCKED\`: do not attempt a production import; inspect error codes.
- Metadata/style changes may be blocked conservatively even if Excel can open
  the copy. That is intentional until an actual importer test proves otherwise.

## Final acceptance still needed

A supervised test import into a backed-up, disposable record of the real
application, followed by re-export, is required **at least once per new export
template version**. We can automate nearly all development regression tests
without that repeated manual step, but cannot claim genuine importer
compatibility without observing the target software.

No actual customer data should be published, including screenshots or Excel
templates from real engagements.
