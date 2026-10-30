"""Static M5.1 UI contracts only; a browser visual audit is still required."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src" / "workbook_mapping_lab"


class BrowserAccessibilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "review_browser.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "review_browser.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "review_browser.js").read_text(encoding="utf-8")

    def test_keyboard_mapping_row_has_visible_focus_contract(self):
        self.assertIn("tr.tabIndex=0", self.js)
        self.assertIn("tbody tr[data-id]:focus-visible{outline:3px solid var(--focus)", self.css)

    def test_warning_selection_communicates_state_to_assistive_technology(self):
        self.assertIn("b.setAttribute('aria-pressed',String(selectedWarning===index))", self.js)
        self.assertIn("b.type='button'", self.js)

    def test_warning_evidence_has_narrow_layout_fallback(self):
        self.assertIn(".evidence-line>*{min-width:0;overflow-wrap:anywhere}", self.css)
        self.assertIn(".evidence-line{grid-template-columns:minmax(0,1fr);gap:.35rem}", self.css)
        self.assertIn("@media(max-width:680px)", self.css)

    def test_existing_skip_and_reduced_motion_controls_preserved(self):
        self.assertIn('class="skip" href="#main"', self.html)
        self.assertIn('@media(prefers-reduced-motion:reduce)', self.css)
        self.assertIn('aria-label="Workflow"', self.html)


if __name__ == "__main__":
    unittest.main()
