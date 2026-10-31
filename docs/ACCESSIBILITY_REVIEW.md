# M5.1: keyboard and 200% zoom review — controlled scope

This is a local Chrome accounting review tool. Its primary job is to select
evidence, review mappings and advisory warnings, then build a checked copy.
No UI inspection may assume a client's financial statements or Winman export
can be published to a public repository or GitHub runner.

## Code-level safeguards

- Keyboard-reachable mapping table rows use Enter/Space to select a row and
  now have a dedicated `:focus-visible` outline in addition to the selected
  state. This avoids relying solely on selected-row background colour.
- Warning cards are buttons. The chosen card now exposes `aria-pressed` as well
  as its existing visible active state.
- Warning evidence names and amounts can wrap within their grid items; a
  narrow viewport stacks the label and amount rather than forcing a wide row.
- Existing skip link, labelled workflow navigation, reduced-motion rule and
  native browser zoom are retained.

The added automated tests assert **source-level contracts only**. They do not
prove browser accessibility, rendered focus visibility, actual text wrapping,
contrast, absence of horizontal overflow or usability at 200% zoom.

## Required human/browser verification before marking M5.1 complete

1. Use the normal local Chrome build with **synthetic** mapping and warning
   data. Test at browser zoom 100% and 200%, including an approximately
   320-CSS-pixel content viewport (for example, 640 physical pixels at 200%).
2. Keyboard only: use Tab/Shift+Tab, Enter, Space and Escape through workflow
   navigation, expanded source options, mapping rows, warning cards and the
   help dialog. Confirm focus is visible, controls work, and focus returns
   after closing the modal.
3. In Review mappings, confirm row focus and selected status remain distinct,
   and the horizontally scrollable table retains its own scrollbar without
   causing unrelated page-level horizontal overflow.
4. In Warnings, select a warning containing long source filenames, cell
   coordinates and large synthetic amounts; confirm the period, tolerance,
   evidence and review action remain readable with no clipping or overlap.
5. In View options, use keyboard-only text size and zoom controls; verify the
   reading lens remains optional and native Chrome zoom still functions.
6. Verify at wide and narrow viewports with no data, incomplete evidence,
   error statuses and long values; check the actual computed focus outline,
   contrast and target sizes in Chrome.

**Release status:** code-level fixes can pass public GitHub CI independently,
but M5.1 remains **PENDING_RENDERED_BROWSER_VERIFICATION** until these actual
browser checks are recorded. Do not claim a visual test was run on GitHub CI.

## M5.1 keyboard-focus retention — additional source-level fix

A source audit on 2026-10-31 found that selecting a warning rebuilt the entire
warning-button list. The active keyboard-focused button was thereby detached,
interrupting keyboard navigation. The updated selector changes the existing
buttons' selected state and the detail panel **in place**, preserving the
focused DOM node. A fifth synthetic static contract test guards this path.

This is a code-level correction, **not** observed browser acceptance. The
required Chrome keyboard and native 200% zoom review remains open; neither
PR merging nor a passing unit suite marks M5.1 complete.

## M5.1b — GitHub-hosted synthetic browser rendering (planned test)

`tests/browser_review_smoke.js` launches the project's original loopback-only
HTTP server inside a GitHub-hosted Ubuntu runner. Its API state is replaced
with an **invented** warning and mapping row; no actual FS, vendor export,
private profile, credentials or local machine paths enter the runner.

The optional pull-request workflow `.github/workflows/browser-smoke.yml` checks
keyboard warning focus retention, accessible selected state, visible focus,
320-CSS-pixel equivalent warning reflow, document-level overflow, and mapped-row
keyboard selection. It retains only synthetic screenshots for a short review
period. This is a new automated **rendered** evidence gate, distinct from
source-level contract tests.

**Limitations:** A narrow 320-CSS-pixel viewport is a reflow proxy, not a proof
that native branded Chrome zoom was exercised at 200%. Human review of Chrome
native zoom, keyboard traversal, touch/trackpad interaction and real desktop
layout remains required before M5.1 is called complete. The initial CI
outcome is pending; do not claim the browser test passed until GitHub logs are
read.
