# Browser interface redesign — 30 October 2026

## Product context

A local-first accountant review tool for financial statements, previous-year
classification learning and exact preservation of the official destination
spreadsheet. The operator needs Chrome-like touchpad zoom and easy reading of
individual words and amounts. Privacy and deterministic accounting controls
take precedence over visual embellishment.

## Design direction

**Quiet, precise, readable financial workspace.** This is an operating
application rather than a marketing website.

The redesign follows an evidence-based Impeccable-style design review
(operate mode); no external design engine, telemetry or new dependencies
were installed.

### Primary changes

- Top bar contains the identity and local-only status; optional
  magnification controls move inside **View options**.
- Intro is compact rather than a marketing hero or collection of KPI cards.
- **Sources:** three essential workbooks visible; profiles, rule files
  and private folder under **More source options**.
- **Review mappings:** five-column table for scanning, with a separate
  selection panel for decision, risk acknowledgement, allocation and sign.
- **Warnings:** evidence-first two-panel reading layout, with notes and
  acknowledgement secondary and collapsible.
- **Build copy:** source template and output filename visible; validations
  under expandable details. A contextual readiness message explains
  unresolved mappings and missing official detail schedules.
- Native Chrome pinch-to-zoom remains unmodified. Optional text scale and
  reading lens are available but are not needed for normal use.

### Motion

- Tab content enters with a short opacity + translateY effect.
- Collapsible advanced content and the View options panel use restrained
  ease-out deceleration.
- Toast messages appear briefly without bouncing.
- CSS **prefers-reduced-motion** disables transitions and animations.
- No loading spinners that claim work has completed, parallax, autoplay,
  or decorative movement unrelated to user actions.

### Test and governance

- Two manually inspected local Chrome renderings: desktop-sized and narrow.
- Static JavaScript syntax validation.
- Localhost API, token and origin protection retained.
- Synthetic end-to-end check: FS -> explicit approvals -> saved review ->
  checked copy -> original workbook byte equality.
- Read-only current FS extraction remains independent from visual logic.
- Neither a copied vendor workbook nor approved review can bypass the
  required detail-schedule and accounting reconciliation checks.

**Current Builders limit:** the available current-year blank vendor export
lacks three previously used detail worksheets. Generating or copying these
from older versions would not meet exact-template requirements. Export the
needed worksheets from the intended-year application before treating the
Builders mapping as complete.

These checks do not establish acceptance of a real application import or
guarantee that a historical tax classification is correct.
