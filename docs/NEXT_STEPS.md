# Roadmap

- v0.1 complete: deterministic mapping with reviewable exceptions.
- v0.2 complete: offline spreadsheet import simulator and independent workbook structure tests.
- v0.3 initial implementation complete: approved-cell, copy-only XLSX writer; strict pre/post checks; round-trip comparison.
- Next: generalise mapping to more financial-statement fields, aggregation, units and sign handling while keeping exceptions explicit.
- Next acceptance gate: supervised **test** import into the real target application; re-export and compare every entered value plus unaffected fields.
- Later: a Windows desktop exception-review interface and reusable mapping library for additional entities and template revisions.

The offline simulator can replace repeated manual engineering checks, but **cannot** establish real importer compatibility. Actual client data stays on the authorised local machine.
