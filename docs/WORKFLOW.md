# Controlled pilot and Winman import strategy

## Input contract
- Previous/current FS extracts: `source_id,section,caption,amount`
- Previous Winman export: `field_id,section,caption,amount`
- Current target fields: `field_id,section,caption,amount` (amount optional)
- Approved mappings: `source_id,field_id,approved`

**Only deliberately synthetic examples belong on GitHub.** Actual documents and per-entity mapping rules stay outside the public checkout.

## Acceptance gates
1. Every populated field has an explicitly approved mapping; suggestions never auto-approve.
2. Flag new rows, disappearing rows, duplicate IDs and invalid destination fields.
3. Check aggregation, signs and unit conversions; reconcile Balance Sheet and P&L against reviewed FS.
4. Fill a COPY of an actual blank Winman workbook, preserving worksheets, formulas and hidden content.
5. Import into a test client only and re-export every populated field.
6. Confirm there are no unexpected changes to any other ITR schedule or personal/partner information.
7. Block production use whenever there are unexplained differences.

## Integration options
- Winman's native Tally-to-Balance-Sheet/P&L transfer is an available alternative, subject to ledger validation.
- The proposed adapter for Winman's blank Excel export requires a supervised round-trip test.
- Windows UI automation should only run after explicit approval and should never silently submit a return.
- No unattended public API or database write interface has been verified.

The current code is a mapping prototype, not a Winman Excel importer.
