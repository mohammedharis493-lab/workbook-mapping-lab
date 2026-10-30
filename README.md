# Workbook Mapping Lab

Local-first research prototype for mapping previous-year spreadsheet classifications into a new-year template. It suggests mappings, applies **reviewer-approved rules only**, and raises exceptions for unmapped or ambiguous items.

## Implemented

- Previous-year mapping discovery and accountant-approved mapping application
- Exception reports for missing, conflicting and new source items
- Read-only workbook structure simulator and virtual import/re-export
- **Strict copy-only XLSX writer** that updates only approved numeric cells
- Preflight and post-write validation of target cells, values and package contents
- Workbook sheet/formula/style/metadata preservation checks
- Public-data screening and synthetic-only automated tests

No proprietary target-application integration or compatibility is claimed. Final acceptance requires a supervised import and re-export in a disposable target record.

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

See [offline simulator](docs/OFFLINE_SIMULATOR.md), [workflow](docs/WORKFLOW.md), and [privacy policy](PRIVACY.md).

Only invented test data is suitable for this repository.
