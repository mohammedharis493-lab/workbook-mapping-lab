# Workbook Mapping Lab

Local-first research prototype for mapping prior-year spreadsheet classifications to a new-year workbook.

The project suggests mappings, applies only explicit reviewer-approved rules, and emits exceptions for missing or ambiguous rows. Public fixtures contain invented numbers and identities. Real client workbooks and mappings never belong in this repository.

## Status

- Previous-year classification discovery
- Reviewer-approved mapping application
- Exception reporting
- Synthetic automated tests
- Public-data screening

No integration with external accounting applications is claimed. A spreadsheet compatibility simulator is being developed to catch template and mapping errors offline. That simulation is not a substitute for a supervised test in the actual target application.

## Test

```bash
python tools/check_public_repo.py
python -m unittest discover -s tests -v
```

See docs/WORKFLOW.md for the local data boundaries and verification gates.
