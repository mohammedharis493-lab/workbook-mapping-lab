# Workbook Mapping Lab

Local-first research prototype for mapping previous-year spreadsheet classifications into a new-year template. It suggests mappings, applies **reviewer-approved rules only**, and raises exceptions for unmapped or ambiguous items.

## Implemented

- Read-only financial-statement extraction using reviewed XLSX profiles
- Detection of newly inserted numeric detail lines in configured watch ranges
- Historical mapping suggestions even when the target workbook row positions move
- **Entity-specific ITR schema profiles:** never assume identical assets, liabilities, schedules or subcomponents across different entities; validate entity, AY, return type and native template before reusing a mapping
- Explicit required/optional/not-applicable/needs-review field states, with no invented zero values for absent optional subcomponents
- Local Windows exception-review desk with explicit approval and private exports
- Separate **non-blocking Warnings** tab comparing historical classifications with supporting FS evidence
- Optional private, reusable cross-workbook advisory checks with review notes
- **Exact vendor-export preservation**: only approved existing numeric cell values change
- Detect previously active detailed sheets missing from the current-year vendor export
- Resolve reviewed detailed fields from captions even when cell rows move
- Compare a generated import workbook with an independently completed current-year ITR workbook, including approved hidden reference worksheets
- Reconcile parent totals against independently populated detail schedules without double-counting
- Previous-year mapping discovery and accountant-approved mapping application
- Exception reports for missing, conflicting and new source items
- Read-only workbook structure simulator and virtual import/re-export
- **Strict copy-only XLSX writer** that updates only approved numeric cells
- Preflight and post-write validation of target cells, values and package contents
- Workbook sheet/formula/style/metadata preservation checks
- Public-data screening and synthetic-only automated tests

No proprietary target-application integration or compatibility is claimed. The primary acceptance test is accurate field-by-field reproduction of an independently completed current-year reference workbook. A separate application import check may be useful for one-time compatibility verification but is not required to iterate on the mapping engine.

## Run synthetic tests

```bash
python tools/check_public_repo.py
python -m unittest discover -s tests -v
```

## Populate an approved local template copy

Keep every actual template, field-layout CSV, source value CSV and output **outside the public repository**.

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m workbook_mapping_lab.writer --template "C:\private\blank.xlsx" --layout "C:\private\layout.csv" --values "C:\private\approved_values.csv" --controls "C:\private\controls.csv" --output "C:\private\checked-copy.xlsx"
```

The output location must be unused. The writer refuses source overwrites, nonempty or formula destination cells, changed anchor labels, invalid/missing fields and modified package contents. It does **not** submit any data to external software.

See [completed-return verification](docs/COMPLETED_RETURN_BENCHMARK.md), [advisory warnings](docs/WARNINGS.md), [exact vendor export](docs/EXACT_VENDOR_EXPORT.md), [reference benchmark](docs/REFERENCE_BENCHMARK.md), [local review desk](docs/LOCAL_REVIEW.md), [offline simulator](docs/OFFLINE_SIMULATOR.md), and [privacy policy](PRIVACY.md).

Only invented test data is suitable for this repository.
