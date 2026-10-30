# Per-entity native ITR field discovery (milestone M2)

## Purpose
Each entity can have a different set of financial-statement classifications, ITR sections, and conditional Winman schedules—even when the same ITR form and assessment year are used. Never reuse the Builders field hierarchy automatically for a different entity.

This module discovers **candidate label and existing blank destination pairs** from the currently selected, original .xlsx import-format export. Presence alone does not establish that a field is numeric, applicable or suitable for a particular ledger. A completed ITR-6 .xlsm is a reference workbook, not an interchangeable import template.

## Chrome workflow
Open **Build copy → Entity-specific ITR schema → Discover fields in this entity's export**.

1. Select the original native import template and, if available, the already reviewed destination layout.
2. Choose **Discover possible fields**. The app scans only existing visible worksheet label cells and neighbouring native blank cells. Search by caption or sheet and review candidates in small batches; secondary settings stay collapsed.
3. Click a candidate and explicitly decide whether to include it, its field ID, its statement section, and whether it is **required**, **optional**, or **not applicable** for the entity. The initial state is always **review**, never automatically required or not applicable.
4. Select **Record reviewed decision** for each candidate included.
5. Select **Save reviewed profile privately**. It saves a new JSON file in the configured private folder; prior files are never overwritten.
6. Verify the profile with **Verify this entity and year**. The build gate rechecks the entity, AY, form, exact template checksum and approved mapping coordinates immediately before writing.

Known layout matches are **preselected but unreviewed** to reduce repetitive navigation. No previous approval of applicability carries over without a fresh decision.

## Safety properties
- Read-only workbook scanning; no macros, web APIs, import, filing or generated worksheets.
- Native blank-value cells must already exist. Occupied cells, formulas, merged non-anchor targets and hidden worksheets are not automatically proposed.
- No missing field is classified as zero or not applicable. Unlisted candidate fields remain **unassessed** and the accountant must evaluate them against the FS, TB, supporting ledgers and the applicable ITR form.
- A strict maximum of 2,500 candidates prevents accidentally describing a truncated scan as complete.
- Export requires at least one individually reviewed selected field, unique field IDs and target cells, exact unchanged template hash and consistency with every field in the selected approved mapping layout.
- The new profile is saved only outside the public repository, never to GitHub or Dropbox. There is no local server telemetry.
- Browser-only choices do not change the approved mapping CSV. Newly discovered fields require separately approved mapping rows before the checked-copy build can include them.
- A generated profile does not prove tax applicability, completeness or that an uninspected Winman schedule was exported.

## Tested scenarios
- Two different synthetic template layouts and movement of labels between rows.
- Correct candidate discovery with previously approved field IDs while treating applicability as unreviewed.
- Duplicate captions kept distinct by actual cell locations.
- Occupied destinations are not proposed.
- A truncated scan, stale native workbook, incomplete reviewed selection, repeated field ID or unreviewed applicability cannot produce a completed profile.
- Re-export of an existing private profile filename is refused.
- End-to-end browser review: discover → explicitly approve every mapped field → private JSON → existing mapping approval → exact-format checked copy, with originals byte-unchanged.

## Actual Builders read-only scan
The selected 16-sheet AY 2026–27 native import-format XLSX yielded **298 candidate label/blank-target pairs**; **12** aligned with existing reviewed mapping rows. Every discovered field remained unreviewed for entity-specific applicability. No new private profile was automatically authorised or created. The unavailable detailed import sheets remain a separate blocker until an official corresponding import-format template is provided.

## Technical implementation
- Discovery: `src/workbook_mapping_lab/schema_discovery.py`
- Chrome loopback UI: `review_browser.html`, `review_browser.js`, `review_browser.py`
- Profile check: `src/workbook_mapping_lab/entity_schema.py`
- Synthetic checks: `tests/test_schema_discovery.py`, `tests/test_browser_workflow.py`

A future step can improve hierarchy extraction using reviewed source financial statements and statement headings. Automatic statutory applicability determination is deliberately **not** assumed.
