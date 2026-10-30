# Chrome browser review and trackpad zoom

The normal desktop shortcut opens the **local Chrome interface**. The old desktop
interface is retained as a Classic shortcut.

## Native trackpad zoom

Use Chrome's ordinary two-finger **pinch-to-zoom** gesture on a supported
Windows touchpad:

- Move two fingers apart to zoom **in**.
- Move them together to zoom **out**.
- Zoom applies to the Chrome page at the pointer's focal area as supported by
  the browser and touchpad hardware.

The application intentionally does **not** intercept Ctrl + mouse wheel,
touchpad gestures, browser zoom keyboard shortcuts, or normal browser scrolling.
There are no mandatory custom gestures or browser extensions.

Fallback: Ctrl and + / Ctrl and -; Ctrl and 0 returns to default Chrome zoom.
If pinch gestures are disabled in Windows touchpad settings, turn on
*Pinch to zoom* under Bluetooth & devices > Touchpad > Scroll & zoom.
The setting exists only on devices with compatible hardware/driver support.

## Optional additional reading aids

- Text size slider: 75–250%, independent of native browser zoom.
- Reading lens: press Alt + M, hover over text or a number, then click to pin;
  press Escape to unpin. Lens text magnification: 150–500%.
- Clear keyboard focus indicators, responsive layout, high-contrast support,
  and horizontally scrollable financial tables.

The normal Chrome zoom gesture requires no special software and is controlled
by Chrome itself.

## Local-only processing

Run using the private desktop launcher, or from the repository root:

    python -m workbook_mapping_lab.review_browser --session PRIVATE_SESSION.json

Use PYTHONPATH pointing at src for a direct local checkout.

The HTTP server binds to 127.0.0.1 only, uses a random available port, and
requires a per-run token for all data and edit endpoints. All actual accounting
processing is delegated to the existing reviewed Python engine. The browser
interface does not upload workbooks or contact Winman. The original template
is not overwritten.

A local browser page is not a remote website. Do not expose this service on a
public interface or configure a browser extension to share its tab content.
