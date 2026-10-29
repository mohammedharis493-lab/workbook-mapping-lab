# Winman FS Mapper — public code only

An early-stage **local-first** tool to learn previous-year financial-statement (FS) → Winman Balance Sheet / P&L classifications, reuse **accountant-approved** mappings in a new year, and produce an exception report before any import.

**Status:** working command-line mapping prototype. **Not** an importer into Winman, **not** an ITR/JSON generator, and **not** a replacement for professional review. No real client material is included.

## Privacy boundary

- Keep originals, Winman exports, scans, PAN/GSTIN, bank details, tax returns, and client-specific mapping rules **outside the public Git checkout**.
- Use only synthetic fixtures in GitHub. Anonymising names alone does **not** make client financial statements safe to publish; amounts, addresses, account numbers, transaction descriptions, dates and hidden workbook content can identify an entity.
- Never commit real, pseudonymised or partially redacted client workbooks. A pre-commit / CI gate restricts public data files and scans for obvious identifiers. This is a second defence, **not a guarantee of anonymity**.
- Work on copies; never modify an original client file automatically.

## Local prototype

Python 3.10+; no third-party packages required for the current CLI.

```sh
python -m pip install -e .
python -m winman_mapper discover --previous-fs fixtures/synthetic/previous_fs.csv --previous-winman fixtures/synthetic/previous_winman.csv --output /tmp/winman_discovery.csv
python -m winman_mapper apply --current-fs fixtures/synthetic/current_fs.csv --approved-rules fixtures/synthetic/approved_rules.csv --target-fields fixtures/synthetic/target_fields.csv --output /tmp/winman_preview.csv --exceptions /tmp/winman_exceptions.csv
python tools/check_public_repo.py
python -m unittest discover -s tests -v
```

On Windows PowerShell, use output paths outside the repository, for example `C:\PrivateWinmanTests\...`.

## Actual Winman workflow (not yet validated by a round-trip)

1. Back up the Winman client file and export a **blank Excel import template** for BS/P&L in the installed Winman version.
2. Privately compare previous-year FS with previously populated Winman BS/P&L export; approve classifications.
3. Apply approved rules to the current-year FS; review new, renamed, duplicate or disappeared items.
4. Produce a **copy** of the actual blank Winman template with accountant-approved values; compare totals, formulas and schedules.
5. Import the copy into a **test** Winman client file, then re-export and compare field by field. Do not automatically file or overwrite original client data.

Step 4 (true `.xlsx` template preservation) and step 5 are **planned**, not implemented in this prototype. A workbook structure mismatch or unmatched row blocks release.

## Project layout

- `src/winman_mapper/mapping.py` — deterministic mapping and exception engine.
- `fixtures/synthetic` — invented values and generic labels only.
- `tools/check_public_repo.py` — intentionally conservative public-repo gate.
- `docs/WORKFLOW.md` — pilot contract and import options.

## Collaboration

Create a fresh public GitHub repo and publish **only** this reviewed starter. Client work remains in a local, access-controlled workspace. No public issues or logs should contain client names, paths, screenshots or screenshots with hidden metadata.