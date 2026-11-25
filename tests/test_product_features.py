"""Product-feature tests: detection precision, pseudonyms, audit trail.

Synthetic fixtures only.  Run with ``python -m unittest tests/test_product_features.py``.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import docx
import openpyxl
import pymupdf

from redaction_tool import redactor, verify
from redaction_tool.audit import RedactionAudit, render_markdown, write_batch_artifacts
from redaction_tool.detector import presidio_is_available
from redaction_tool.detector import detect
from redaction_tool.pseudonyms import Pseudonymizer


def _texts(matches, category):
    return [m.text for m in matches if m.category == category]


class DetectionPrecisionTests(unittest.TestCase):
    def test_possessive_name_fragments_merge_into_one_span(self):
        matches = detect("Called regarding Saanvi Reddy's suspension.")
        self.assertEqual(_texts(matches, "names"), ["Saanvi Reddy's"])

    def test_last_first_and_following_initial_merge(self):
        matches = detect("Patient ID sticker: QUINN, HARPER J")
        self.assertEqual(_texts(matches, "names"), ["QUINN, HARPER J"])

    def test_nested_duplicate_categories_are_not_reported_twice(self):
        fax = detect("Fax: 303-555-0188")
        self.assertEqual({m.category for m in fax}, {"fax"})

        account = detect("Account Number 99887766")
        self.assertEqual({m.category for m in account}, {"accounts"})

        box = detect("P.O. Box 44551")
        self.assertEqual({m.category for m in box}, {"addresses"})

    def test_conjunction_is_not_a_ledger_name(self):
        matches = detect("Patient: Alexandria Montoya. Later, Ms. Montoya and "
                         "Alexandria and A. Montoya returned.")
        self.assertNotIn("and", [m.text.lower() for m in matches])
        self.assertIn("Ms. Montoya", _texts(matches, "names"))

    def test_identifier_label_bigrams_are_not_names(self):
        passport = detect("US Passport No. 987654321 issued to traveler.")
        self.assertEqual(_texts(passport, "names"), [])
        self.assertIn("987654321", _texts(passport, "unique_ids"))

        itin = detect("Taxpayer ITIN 912-34-5678 submitted.")
        self.assertEqual(_texts(itin, "names"), [])
        self.assertIn("912-34-5678", _texts(itin, "ssn"))

    def test_payment_card_needs_luhn_checksum(self):
        valid = detect("Visa card 4532 0151 1283 0366 charged.")
        self.assertIn("4532 0151 1283 0366", _texts(valid, "financial"))

        invalid = detect("Reference 4532 0151 1283 0367 not a card.")
        self.assertEqual(_texts(invalid, "financial"), [])

    def test_bare_zip_is_redacted_in_every_position(self):
        # Recall-first: a standalone 5-digit token is redacted even when no
        # "ZIP"/"postal" label or "City, ST" precedes it.  Over-redacting a
        # catalog number is acceptable; leaking a ZIP is not.
        roster = detect("Varga, Per | 00732836 | 06/07/1995 | 720-625-5156 | 69364")
        self.assertIn("69364", _texts(roster, "addresses"))
        self.assertIn("Varga, Per", _texts(roster, "names"))

        full_state = detect(
            "mailed to 4629 Alameda Way, Wichita, Kansas 11142.")
        self.assertIn("11142", _texts(full_state, "addresses"))

        labeled = detect("Mailing ZIP 80203 is on the form.")
        self.assertIn("80203", _texts(labeled, "addresses"))
        city_state = detect("Denver, CO 80203")
        self.assertIn("80203", _texts(city_state, "addresses"))
        self.assertIn("55432",
                      _texts(detect("Item catalog # 55432 is currently in stock."),
                             "addresses"))

    def test_given_names_that_look_like_identifier_words(self):
        # Words added to the name stop list for identifier labels are real
        # given names in a name position and must still be redacted.
        for text, expected in (
            ("Name: Per Varga", "Per Varga"),
            ("Per Varga attended the hearing.", "Per Varga"),
            ("Employee: Card Michael", "Card Michael"),
            ("Name: Visa Anan", "Visa Anan"),
        ):
            self.assertIn(expected, _texts(detect(text), "names"), text)

        roster = detect("Varga, Per | 00732836 | 720-625-5156 | 69364")
        self.assertIn("Varga, Per", _texts(roster, "names"))

    def test_street_address_zip_with_unit_and_full_state(self):
        matches = detect(
            "I live at 7471 Kestrel Avenue, Ste. 4, Denver, Colorado 93514.")
        self.assertIn("7471 Kestrel Avenue, Ste. 4", _texts(matches, "addresses"))
        self.assertIn("93514", _texts(matches, "addresses"))

    def test_quoted_alias_surname_detected(self):
        matches = detect("Alias: \u201cFrankie\u201d DiMartino.")
        self.assertIn("DiMartino", _texts(matches, "names"))

    def test_street_address_includes_unit(self):
        matches = detect("Lives at 1234 Pine Street, Apt 8, Denver, CO 80203")
        self.assertIn("1234 Pine Street, Apt 8", _texts(matches, "addresses"))

    @unittest.skipUnless(presidio_is_available(), "Presidio not installed")
    def test_presidio_gate_rejects_label_and_ratio_noise(self):
        for text, bogus in (
            ("Email jane.doe@examp1e.edu", "Email"),
            ("Ratio 5/97 was observed in the sample.", "Ratio 5/97"),
            ("Jordan almonds were served at the reception (candy, not a person).", "Jordan"),
            ("Sibling name: Ana-Sofia Ruiz-Gutierrez", "Sibling"),
        ):
            names = _texts(detect(text, use_presidio=True), "names")
            self.assertNotIn(bogus, names, text)

        locations = _texts(detect("US Passport No. 987654321 issued.", use_presidio=True),
                           "addresses")
        self.assertNotIn("US", locations)


class PseudonymTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_docx_labels_are_consistent_across_paragraphs_and_files(self):
        pseudonyms = Pseudonymizer()
        opts = redactor.ScanOptions(pseudonyms=pseudonyms, use_presidio=False)

        first = docx.Document()
        first.add_paragraph("Case note: Alexandria Montoya (SSN 123-45-6789) "
                            "called 303-555-0142.")
        first.add_paragraph("Follow-up with Alexandria Montoya scheduled.")
        first.save(self.td / "note.docx")

        second = docx.Document()
        second.add_paragraph("Alexandria Montoya emailed again.")
        second.save(self.td / "second.docx")

        r1 = redactor.redact_file(self.td / "note.docx", opts,
                                  out_path=self.td / "note_REDACTED.docx")
        r2 = redactor.redact_file(self.td / "second.docx", opts,
                                  out_path=self.td / "second_REDACTED.docx")
        self.assertEqual(r1.recoverability, "PASS")
        self.assertEqual(r2.recoverability, "PASS")

        out1 = docx.Document(self.td / "note_REDACTED.docx")
        out2 = docx.Document(self.td / "second_REDACTED.docx")
        body = "\n".join(p.text for p in out1.paragraphs)
        self.assertIn("[NAME_1]", body)
        self.assertIn("[SSN_1]", body)
        self.assertIn("[PHONE_1]", body)
        self.assertNotIn("Alexandria", body)
        self.assertNotIn("123-45-6789", body)
        # Same person, same label, different document.
        self.assertIn("[NAME_1]", out2.paragraphs[0].text)
        self.assertNotIn("[NAME_2]", out2.paragraphs[0].text)
        # The value -> label map is in memory only; nothing persisted.
        self.assertFalse(hasattr(pseudonyms, "save"))
        self.assertNotIn("Alexandria", json.dumps(r1.audit))

    def test_xlsx_header_column_labels_are_stable_per_value(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Roster"
        ws.append(["Student Name", "Student ID"])
        ws.append(["Alexandria Montoya", "00991234"])
        ws.append(["Alexandria Montoya", "00991234"])
        wb.save(self.td / "roster.xlsx")

        opts = redactor.ScanOptions(pseudonyms=Pseudonymizer(), use_presidio=False)
        result = redactor.redact_file(self.td / "roster.xlsx", opts,
                                      out_path=self.td / "roster_REDACTED.xlsx")
        self.assertEqual(result.recoverability, "PASS")

        out = openpyxl.load_workbook(self.td / "roster_REDACTED.xlsx").active
        self.assertEqual([c.value for c in out[1]], ["Student Name", "Student ID"])
        self.assertEqual([c.value for c in out[2]][0], "[NAME_1]")
        self.assertEqual([c.value for c in out[3]][0], "[NAME_1]")
        self.assertEqual([c.value for c in out[2]][1], "[ID_1]")

    def test_pdf_label_is_written_and_source_value_is_gone(self):
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Patient: Alexandria Montoya")
        page.insert_text((72, 90), "SSN 123-45-6789")
        doc.save(self.td / "case.pdf")
        doc.close()

        opts = redactor.ScanOptions(pseudonyms=Pseudonymizer(), use_presidio=False)
        result = redactor.redact_file(self.td / "case.pdf", opts,
                                      out_path=self.td / "case_REDACTED.pdf")
        self.assertEqual(result.recoverability, "PASS")

        out = pymupdf.open(self.td / "case_REDACTED.pdf")
        text = out[0].get_text()
        out.close()
        self.assertIn("[NAME_1]", text)
        self.assertIn("[SSN_1]", text)
        self.assertNotIn("Alexandria", text)
        self.assertNotIn("123-45-6789", text)

        check = verify.verify_export(self.td / "case_REDACTED.pdf",
                                     targeted_values=["Alexandria Montoya",
                                                      "123-45-6789"],
                                     scan_opts=opts)
        self.assertEqual(check["status"], "PASS")

    def test_verification_does_not_advance_label_counters(self):
        pseudonyms = Pseudonymizer()
        opts = redactor.ScanOptions(pseudonyms=pseudonyms, use_presidio=False)

        document = docx.Document()
        document.add_paragraph("Patient: Alexandria Montoya")
        document.save(self.td / "verify.docx")
        redactor.redact_file(self.td / "verify.docx", opts,
                             out_path=self.td / "verify_REDACTED.docx")
        counters_after_redaction = dict(pseudonyms.counters)

        verify.verify_export(self.td / "verify_REDACTED.docx",
                             targeted_values=["Alexandria Montoya"],
                             scan_opts=opts)
        self.assertEqual(pseudonyms.counters, counters_after_redaction)

        # The next document still gets the next label, not one burned by verify.
        second = docx.Document()
        second.add_paragraph("Unrelated note.")
        second.add_paragraph("Alexandria Montoya")
        second.save(self.td / "verify2.docx")
        redactor.redact_file(self.td / "verify2.docx", opts,
                             out_path=self.td / "verify2_REDACTED.docx")
        self.assertEqual(pseudonyms.counters["NAME"], counters_after_redaction["NAME"])

    def test_constant_replacement_is_unchanged_without_pseudonyms(self):
        document = docx.Document()
        document.add_paragraph("Patient: Alexandria Montoya")
        document.save(self.td / "plain.docx")
        result = redactor.redact_file(self.td / "plain.docx",
                                      redactor.ScanOptions(use_presidio=False),
                                      out_path=self.td / "plain_REDACTED.docx")
        self.assertEqual(result.recoverability, "PASS")
        text = docx.Document(self.td / "plain_REDACTED.docx").paragraphs[0].text
        self.assertEqual(text, "Patient: [REDACTED]")


class AuditTrailTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_locations_recorded_per_format(self):
        opts = redactor.ScanOptions(use_presidio=False)

        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Patient: Brianna Ynostroza SSN 123-45-6789")
        pdf.save(self.td / "doc.pdf")
        pdf.close()
        r_pdf = redactor.redact_file(self.td / "doc.pdf", opts,
                                     out_path=self.td / "doc_REDACTED.pdf")
        self.assertEqual(r_pdf.audit[0]["where"], "page 1")
        self.assertEqual(r_pdf.audit[0]["categories"], {"names": 1, "ssn": 1})

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Roster"
        ws.append(["Name", "Email"])
        ws.append(["Brianna Ynostroza", "brianna@example.edu"])
        wb.save(self.td / "roster.xlsx")
        r_xlsx = redactor.redact_file(self.td / "roster.xlsx", opts,
                                      out_path=self.td / "roster_REDACTED.xlsx")
        where = {u["where"]: u["categories"] for u in r_xlsx.audit}
        self.assertIn("Roster!A2", where)
        self.assertIn("Roster!B2", where)

        document = docx.Document()
        document.add_paragraph("Nothing sensitive here.")
        document.add_paragraph("SSN 123-45-6789")
        document.save(self.td / "memo.docx")
        r_docx = redactor.redact_file(self.td / "memo.docx", opts,
                                      out_path=self.td / "memo_REDACTED.docx")
        where = {u["where"]: u["categories"] for u in r_docx.audit}
        self.assertIn("body ¶2", where)
        self.assertNotIn("body ¶1", where)

    def test_log_and_report_contain_no_plaintext(self):
        document = docx.Document()
        document.add_paragraph("Patient: Brianna Ynostroza SSN 123-45-6789")
        document.save(self.td / "case.docx")
        opts = redactor.ScanOptions(use_presidio=False, hash_salt="test-salt")
        result = redactor.redact_file(self.td / "case.docx", opts,
                                      out_path=self.td / "case_REDACTED.docx")

        batch = {
            "tool_version": "test",
            "generated_at": "2026-01-01T00:00:00",
            "preset": "Full (FERPA + HIPAA)",
            "hash_salt": opts.hash_salt,
            "replacement": opts.replacement,
            "pseudonymize": False,
            "use_presidio": False,
            "entries": [{
                "source": "case.docx",
                "redaction_count": result.redaction_count,
                "per_category": result.per_category,
                "audit": result.audit,
                "verify": {"status": "PASS", "residual": 0},
                "recoverability": result.recoverability,
                "errors": [],
            }],
        }
        log_path, report_path = write_batch_artifacts(self.td, batch)
        serialized = log_path.read_text(encoding="utf-8") + report_path.read_text(encoding="utf-8")
        for secret in ("Brianna", "Ynostroza", "123-45-6789"):
            self.assertNotIn(secret, serialized)
        self.assertIn("names", serialized)
        self.assertIn("body ¶1", serialized)

        # A second batch in the same second must not clobber the first.
        log_path2, report_path2 = write_batch_artifacts(self.td, batch)
        self.assertNotEqual(log_path, log_path2)
        self.assertNotEqual(report_path, report_path2)

    def test_report_flags_failed_verification(self):
        batch = {
            "tool_version": "test",
            "generated_at": "2026-01-01T00:00:00",
            "preset": "Full (FERPA + HIPAA)",
            "replacement": "[REDACTED]",
            "entries": [{
                "source": "bad.pdf",
                "redaction_count": 0,
                "errors": ["Verification status: NEEDS_REVIEW"],
                "verify": {"status": "NEEDS_REVIEW"},
            }],
        }
        rendered = render_markdown(batch)
        self.assertIn("Follow-up required", rendered)
        self.assertIn("NEEDS_REVIEW", rendered)

    def test_audit_accumulates_counts_without_values(self):
        audit = RedactionAudit()
        audit.add("page 2", "names")
        audit.add("page 2", "names")
        audit.add("page 3", "emails")
        self.assertEqual(audit.category_totals(), {"emails": 1, "names": 2})
        self.assertEqual(audit.as_list()[0],
                         {"where": "page 2", "categories": {"names": 2}})


if __name__ == "__main__":
    unittest.main()
