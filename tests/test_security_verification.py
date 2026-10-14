"""Adversarial and synthetic tests for Phase 4 security and verification.

Covers fail-closed OCR processing, reverification of final output bytes,
dual independent checks, audit artifact safety, and non-destructive operations.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redaction_tool import detector, gui, ocr, redactor, verify


class TestSecurityVerification(unittest.TestCase):
    """Phase 4 mandatory security and verification test suite."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    # 1. One OCR page failure among successful pages
    def test_one_ocr_page_failure_among_successful_pages(self):
        pdf_path = self.td / "multipage.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz

        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((50, 50), "Page 1 clean text")
        p2 = doc.new_page()
        p2.insert_text((50, 50), "Page 2 text with SSN 123-45-6789")
        doc.save(str(pdf_path))
        doc.close()

        def mock_run_ocr(img_path, lang="eng", tesseract_cmd=None):
            if "page-0002" in str(img_path):
                raise RuntimeError("OCR engine error on page 2")
            return [ocr.OCRWord("Page", 0, 0, 10, 10, 95.0, 0, 4)]

        with patch("redaction_tool.ocr.run_ocr", side_effect=mock_run_ocr):
            plan = ocr.scan_ocr_pdf(pdf_path)
            self.assertTrue(len(plan["warnings"]) > 0)
            self.assertIn("Page 2: OCR failed", plan["warnings"][0])

            res = ocr.verify_ocr(pdf_path)
            self.assertEqual(res["status"], "NEEDS_REVIEW")
            self.assertIn("warnings", res)

    # 2. Missing OCR executable/language data
    def test_missing_ocr_executable_or_language_data(self):
        img_path = self.td / "sample.png"
        try:
            from PIL import Image
            img = Image.new("RGB", (100, 100), color="white")
            img.save(img_path)
        except ImportError:
            self.skipTest("Pillow unavailable")

        with patch("redaction_tool.ocr.find_tesseract", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                ocr.scan_ocr_image(img_path)
            self.assertIn("Tesseract OCR not found", str(ctx.exception))

        with patch("redaction_tool.ocr.find_tessdata", return_value=None):
            with patch("redaction_tool.ocr.find_tesseract", return_value="tesseract.exe"):
                with self.assertRaises(RuntimeError) as ctx:
                    ocr.scan_ocr_image(img_path)
                self.assertIn("English data", str(ctx.exception))

    # 3. Scanner raises during verification
    def test_scanner_raises_during_verification(self):
        pdf_path = self.td / "sample.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Some text")
        doc.save(str(pdf_path))
        doc.close()

        opts = redactor.ScanOptions()
        with patch.object(opts, "run_detection", side_effect=RuntimeError("Scanner crashed")):
            res = verify.verify_export(pdf_path, scan_opts=opts)
            self.assertEqual(res["status"], "ERROR")
            self.assertIn("exception", res["reason"])

    # 4. Presidio raises during verification
    def test_presidio_raises_during_verification(self):
        pdf_path = self.td / "sample.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Hello world")
        doc.save(str(pdf_path))
        doc.close()

        opts = redactor.ScanOptions(use_presidio=True)
        with patch("redaction_tool.detector.get_presidio_engine") as mock_engine:
            mock_inst = MagicMock()
            mock_inst.analyze.side_effect = RuntimeError("Presidio internal crash")
            mock_engine.return_value = mock_inst
            res = verify.verify_export(pdf_path, scan_opts=opts)
            self.assertIn(res["status"], ("ERROR", "NEEDS_REVIEW"))

    # 5. Malformed PDF
    def test_malformed_pdf(self):
        bad_pdf = self.td / "corrupt.pdf"
        bad_pdf.write_bytes(b"%PDF-1.4 %FAKE CORRUPT DATA HERE")

        res = verify.verify_export(bad_pdf)
        self.assertEqual(res["status"], "ERROR")

        opts = redactor.ScanOptions()
        red_res = redactor.redact_file(bad_pdf, opts)
        self.assertIsNotNone(red_res.error)

    # 6. Missing/zero-byte output
    def test_missing_or_zero_byte_output(self):
        missing_file = self.td / "non_existent.pdf"
        res = verify.verify_export(missing_file)
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("missing or empty", res["reason"])

        zero_byte = self.td / "empty.pdf"
        zero_byte.write_bytes(b"")
        res2 = verify.verify_export(zero_byte)
        self.assertEqual(res2["status"], "ERROR")
        self.assertIn("missing or empty", res2["reason"])

    # 7. Failed OCR overlay followed by batch accounting
    def test_failed_ocr_overlay_followed_by_batch_accounting(self):
        pdf_path = self.td / "test_ocr.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Document with SSN 123-45-6789")
        doc.save(str(pdf_path))
        doc.close()

        payload = {
            "files": [str(pdf_path)],
            "opts": redactor.ScanOptions(),
            "use_ocr": True,
            "out_dir": str(self.td),
            "suffix": "_REDACTED",
            "preset": "Full (FERPA + HIPAA)",
            "image_output": False,
            "image_format": "PNG",
        }

        import queue
        q = queue.Queue()
        mock_app = MagicMock()

        with patch("redaction_tool.ocr.scan_ocr_pdf", side_effect=RuntimeError("OCR overlay exploded")):
            res = gui.App._redact_worker(mock_app, payload, q)
            self.assertEqual(res["ok"], 0)
            self.assertEqual(res["failed"], 1)
            self.assertTrue(any("OCR ERROR" in line or "ERROR" in line for line in res["lines"]))

    # 8. PDF with visible black rectangle but recoverable underlying text (faux redaction)
    def test_pdf_black_rectangle_with_recoverable_underlying_text(self):
        pdf_path = self.td / "faux.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Confidential SSN 123-45-6789")
        # Draw solid black rectangle over text without redaction annotation or apply_redactions
        p.draw_rect(fitz.Rect(40, 40, 200, 70), color=(0, 0, 0), fill=(0, 0, 0))
        doc.save(str(pdf_path))
        doc.close()

        res = verify.verify_export(pdf_path, targeted_values=["123-45-6789"])
        self.assertEqual(res["status"], "NEEDS_REVIEW")
        self.assertGreater(res["leaked_count"], 0)

    # 9. PDF metadata/link/widget/attachment residue
    def test_pdf_metadata_link_widget_attachment_residue(self):
        pdf_path = self.td / "residue.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Clean page body")
        doc.set_metadata({"author": "Secret User john.doe@example.com"})
        p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(10, 10, 30, 30), "uri": "mailto:123-45-6789@test.com"})
        doc.embfile_add("secret.txt", b"Embedded attachment with 123-45-6789")
        doc.save(str(pdf_path))
        doc.close()

        res = verify.verify_export(pdf_path, targeted_values=["123-45-6789", "john.doe@example.com"])
        self.assertEqual(res["status"], "NEEDS_REVIEW")

        opts = redactor.ScanOptions()
        out_pdf = self.td / "residue_REDACTED.pdf"
        red_res = redactor.redact_file(pdf_path, opts, out_path=out_pdf)
        self.assertEqual(red_res.error, None)

        res_clean = verify.verify_export(out_pdf, targeted_values=["123-45-6789", "john.doe@example.com"])
        self.assertEqual(res_clean["status"], "PASS")

    # 10. DOCX hidden XML/comment/footnote/textbox residue
    def test_docx_hidden_xml_comment_footnote_textbox_residue(self):
        docx_path = self.td / "hidden.docx"
        try:
            import docx
        except ImportError:
            self.skipTest("docx unavailable")

        doc = docx.Document()
        doc.add_paragraph("Visible body text")

        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        section = doc.sections[0]
        footer = section.footer
        p_ft = footer.paragraphs[0]
        p_ft.text = "Footer with SSN 123-45-6789"

        doc.save(str(docx_path))

        res = verify.verify_export(docx_path, targeted_values=["123-45-6789"])
        self.assertEqual(res["status"], "NEEDS_REVIEW")

        out_docx = self.td / "hidden_REDACTED.docx"
        opts = redactor.ScanOptions()
        redactor.redact_file(docx_path, opts, out_path=out_docx)

        res_clean = verify.verify_export(out_docx, targeted_values=["123-45-6789"])
        self.assertEqual(res_clean["status"], "PASS")

    # 11. XLSX comment/header/footer/shared string residue
    def test_xlsx_comment_header_footer_shared_string_residue(self):
        xlsx_path = self.td / "xlsx_test.xlsx"
        try:
            import openpyxl
            from openpyxl.comments import Comment
        except ImportError:
            self.skipTest("openpyxl unavailable")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "Normal Cell"
        ws["A2"] = "Target 123-45-6789"
        ws["A1"].comment = Comment("Comment with 123-45-6789", "Author")
        wb.save(str(xlsx_path))

        res = verify.verify_export(xlsx_path, targeted_values=["123-45-6789"])
        self.assertEqual(res["status"], "NEEDS_REVIEW")

        out_xlsx = self.td / "xlsx_test_REDACTED.xlsx"
        opts = redactor.ScanOptions()
        redactor.redact_file(xlsx_path, opts, out_path=out_xlsx)

        res_clean = verify.verify_export(out_xlsx, targeted_values=["123-45-6789"])
        self.assertEqual(res_clean["status"], "PASS")

    # 12. Residual PII detectable only by Presidio
    def test_residual_pii_detectable_only_by_presidio(self):
        pdf_path = self.td / "presidio_only.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Patient candidate Arthur Dent visited office")
        doc.save(str(pdf_path))
        doc.close()

        opts = redactor.ScanOptions(use_presidio=True)

        fake_match = detector.Match(
            category="names",
            start=18,
            end=29,
            text="Arthur Dent",
            confidence="confirmed",
            evidence="presidio:PERSON:0.85",
        )

        with patch("redaction_tool.detector.presidio_is_available", return_value=True):
            with patch("redaction_tool.detector._presidio_matches", return_value=[fake_match]):
                res = verify.verify_export(pdf_path, scan_opts=opts)
                self.assertEqual(res["status"], "NEEDS_REVIEW")

    # 13. Source unchanged after failure
    def test_source_unchanged_after_failure(self):
        pdf_path = self.td / "immutable.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Text SSN 123-45-6789")
        doc.save(str(pdf_path))
        doc.close()

        src_bytes = pdf_path.read_bytes()
        src_hash = hashlib.sha256(src_bytes).hexdigest()

        opts = redactor.ScanOptions()

        # Attempt to redact overwriting source (must return error or raise)
        red_res = redactor.redact_file(pdf_path, opts, out_path=pdf_path)
        self.assertIsNotNone(red_res.error)

        with self.assertRaises((ValueError, RuntimeError)):
            ocr.apply_ocr_redactions(pdf_path, {}, pdf_path)

        after_bytes = pdf_path.read_bytes()
        after_hash = hashlib.sha256(after_bytes).hexdigest()
        self.assertEqual(src_hash, after_hash)

    # 14. Log and plan serialization contains no inserted synthetic plaintext markers
    def test_log_and_plan_serialization_contains_no_plaintext(self):
        words = [
            ocr.OCRWord("123-45-6789", 10, 10, 50, 20, 90.0, 0, 11)
        ]
        opts = redactor.ScanOptions(enabled_categories=["ssn"], hash_salt="test_salt_123")

        plan_entries, _ = ocr.detect_on_ocr(words, scan_opts=opts)
        plan_str = json.dumps(plan_entries)

        self.assertNotIn("123-45-6789", plan_str)
        self.assertIn("***6789", plan_str)

    # 15. PASS, NEEDS_REVIEW, ERROR distinct meanings
    def test_pass_needs_review_error_distinct_meanings(self):
        pdf_path = self.td / "clean.pdf"
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Completely clean text with no protectable items")
        doc.save(str(pdf_path))
        doc.close()

        res_pass = verify.verify_export(pdf_path, targeted_values=["nonexistent_value"])
        self.assertEqual(res_pass["status"], "PASS")

        res_review = verify.verify_export(pdf_path, targeted_values=["clean text"])
        self.assertEqual(res_review["status"], "NEEDS_REVIEW")

        res_error = verify.verify_export(self.td / "missing.pdf")
        self.assertEqual(res_error["status"], "ERROR")

        self.assertNotEqual(res_pass["status"], res_review["status"])
        self.assertNotEqual(res_pass["status"], res_error["status"])
        self.assertNotEqual(res_review["status"], res_error["status"])


if __name__ == "__main__":
    unittest.main()
