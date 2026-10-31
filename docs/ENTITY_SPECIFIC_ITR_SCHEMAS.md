# Entity-specific ITR schemas — permanent design rule

## Principle

NEVER assume that two entities have identical ITR assets, liabilities, P&L components, subcomponents or schedules. Two entities using the same statutory ITR form for the same assessment year may still have different applicable schedules and detailed disclosures. Winman exports may also vary by application version and activated schedules.

Every mapping must be tied to the entity, assessment year, ITR form and its **actual current-year native export**. A previous entity's mapping is not authoritative.

## Non-negotiable requirements

1. Discover each current entity's worksheets, actual field labels and locations from its own official export.
2. Review field applicability independently: required, optional, not_applicable, or review.
3. An optional component may be absent. Do not assume it is zero or manufacture a worksheet.
4. An uncertain component is left for accountant review. An absent required field is a blocking issue.
5. Different subcomponents may appear under the same BS/P&L group across different entities. Do not hardcode the Builders structure.
6. Preserve each native workbook exactly except for reviewed, explicitly approved numeric cell changes in a separate copy.
7. Do not reuse an entity-specific profile for a different entity, assessment year, form or native workbook SHA-256.
8. Reconcile parent amounts against details without double-counting.
9. Use prior-year classification solely as a suggestion; never blindly repeat it.
10. A completed-return comparison and FS totals are independent controls. Equal totals do not prove correct field placement.

## Implemented validator

The read-only module is located at src/workbook_mapping_lab/entity_schema.py.

A private JSON profile identifies the entity key, assessment year, ITR form, exact native export SHA-256 and a list of fields with section, sheet, caption, anchor/amount columns and reviewed applicability. The module validates the identity, template and field placements without writing any workbook. It returns required-field blockers, optional notices and unresolved applicability separately.

Example (synthetic): entity-a uses an active Related Details sheet with Deposits from related parties as a required subcomponent. Entity-b, also using ITR-6 for the same AY, has no Related Details sheet and an independently reviewed not-applicable decision. Those profiles must not be mixed.

Run: python -m workbook_mapping_lab.entity_schema --template PRIVATE_CURRENT_EXPORT.xlsx --profile PRIVATE_ENTITY_PROFILE.json --entity-key ENTITY_KEY --assessment-year 2026-27 --itr-form ITR-6

Keep every private profile outside the public repository.

## Build preflight across user-facing entry points

Browser, Classic desktop, controlled-pipeline CLI and direct-writer CLI builds must now pass a shared
`require_approved_entity_schema` preflight before generating a checked copy.
It verifies the private reviewed profile's entity, assessment year, ITR form
and exact original native-export SHA-256. Every approved CSV destination must
match a currently resolved native sheet, anchor, blank amount cell, statement
section and caption. Required profile fields missing from the approved layout
are blocking. Undecided applicability never becomes a zero or an approval.

For either command-line build, add these required options to the existing
`python -m workbook_mapping_lab.pipeline` or
`python -m workbook_mapping_lab.writer` invocation:

    --entity-schema-profile PRIVATE_REVIEWED_ENTITY.json
    --entity-key VERIFIED_ENTITY_KEY
    --assessment-year 2026-27
    --itr-form ITR-6

The Classic desktop Build tab exposes the same four selections. Users may
discover and approve native fields in the Chrome workflow, then use its
privately saved reviewed schema in Classic. No vendor import is performed.

`controlled_build` remains a low-level programmatic engine for synthetic
tests and explicitly supervised internal use; it does not independently
enforce entity profile identity. A new integration must run the shared
preflight or be treated as not release-ready. Historical source-content
fingerprinting in the Chrome review is a separate safeguard.

## Acceptance tests

Tests verify differing native subcomponents for two entities using the same form and year, cross-entity and cross-year rejection, missing optional versus required fields, undecided applicability, native row movements and unchanged originals.
