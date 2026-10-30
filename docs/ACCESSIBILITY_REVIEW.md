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
