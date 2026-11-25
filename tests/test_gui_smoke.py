"""GUI smoke test: the desktop app starts and redacts a synthetic document.

Linux CI runs this under ``xvfb-run`` (no physical display).  Without a display
the test skips instead of failing, so a developer box without X still gets a
green suite; the Linux CI job is what proves it runs.
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tkinter as tk  # noqa: E402

from redaction_tool import gui  # noqa: E402


def _display_available() -> bool:
    try:
        root = tk.Tk()
    except Exception:
        return False
    root.destroy()
    return True


HAS_DISPLAY = _display_available()
SKIP_REASON = "no display available (headless CI must wrap this in xvfb-run)"


@unittest.skipUnless(HAS_DISPLAY, SKIP_REASON)
class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        self._dnd_ok = gui._DND_OK

    def tearDown(self):
        gui._DND_OK = self._dnd_ok

    def _pump(self, root, app, seconds=120):
        deadline = time.time() + seconds
        while time.time() < deadline:
            root.update()
            if getattr(app, "_batch_queue", None) is None and \
                    getattr(app, "results", None) is not None:
                return
            time.sleep(0.02)
        raise AssertionError("GUI batch did not finish in time")

    def test_startup_falls_back_when_the_tkdnd_extension_cannot_load(self):
        """Tk 9 on Linux rejects tkinterdnd2's Tcl 8 extension."""
        broken = MagicMock()
        broken.Tk.side_effect = RuntimeError("Unable to load tkdnd library.")
        with patch.object(gui, "_DND_OK", True), \
                patch.object(gui, "TkinterDnD", broken):
            root = gui._create_root()
            try:
                self.assertIsInstance(root, tk.Tk)
                self.assertFalse(gui._DND_OK)
            finally:
                root.destroy()

    def test_app_redacts_a_synthetic_docx_end_to_end(self):
        import docx

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "synthetic-case-file.docx"
            document = docx.Document()
            document.add_paragraph(
                "Complainant Brianna Ynostroza, SSN 123-45-6789, "
                "email jane.doe@example.edu."
            )
            document.save(str(src))

            root = gui._create_root()
            app = gui.App(root)
            try:
                box = MagicMock()
                box.askyesno.return_value = True
                with patch.object(gui, "messagebox", box):
                    app._add_paths([str(src)])
                    self.assertEqual(app.files, [str(src)])

                    app.scan_files()
                    self._pump(root, app)
                    scan_text = app.results.get("1.0", "end")
                    self.assertIn("3 item(s) detected", scan_text)

                    app.redact_all()
                    self._pump(root, app)
                    redact_text = app.results.get("1.0", "end")
                    self.assertIn("PASS", redact_text)
            finally:
                root.destroy()

            out = src.with_name(src.stem + "_REDACTED.docx")
            self.assertTrue(out.is_file(), "redacted copy was not written")
            self.assertTrue(app.last_outputs)
            text = "\n".join(p.text for p in docx.Document(str(out)).paragraphs)
            self.assertNotIn("123-45-6789", text)
            self.assertNotIn("jane.doe@example.edu", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
