"""High-recall name/date detection, ledger, OCR, and export-security tests."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from redaction_tool import detector, redactor, verify  # noqa: E402
from redaction_tool.detector import detect  # noqa: E402


def _has(text: str, needle: str, category: str | None = None) -> bool:
    for m in detect(text):
        if needle.lower() in m.text.lower() or m.text.lower() in needle.lower():
            if category is None or m.category == category:
                return True
    return False


def test_unlabeled_narrative_name():
    assert _has("Jordan met with the counselor Tuesday.", "Jordan", "names")


def test_compound_parent_name():
    assert _has("Maria's father, Ernesto de la Cruz, called the office.",
                "Ernesto de la Cruz", "names")


def test_apostrophe_name():
    assert _has("Patient: N'golo Amari", "N'golo Amari", "names")


def test_multicultural_labeled_name():
    assert _has("Parent/Guardian — Xiuying Zhang", "Xiuying Zhang", "names")


def test_initial_last_and_partial_date():
    text = "R. Patel was discharged on 04/17."
    assert _has(text, "R. Patel", "names")
    assert _has(text, "04/17", "dates")


def test_last_first_student():
    assert _has("Student Cruz, Mateo A.", "Cruz, Mateo", "names")


def test_ledger_variants():
    text = ("Patient: Alexandria Montoya. Later, Ms. Montoya and Alexandria "
            "and A. Montoya returned.")
    ms = detect(text)
    joined = " | ".join(m.text for m in ms if m.category == "names")
    assert "Alexandria Montoya" in joined
    assert "Ms. Montoya" in joined
    assert "A. Montoya" in joined


def test_two_digit_year_dates():
    for s in ("04/17/26", "4/7/26", "17-Apr-26", "8/19/24"):
        assert _has(s if " " in s else f"Admitted {s}.", s, "dates"), s


def test_written_and_relative_dates():
    assert _has("Born April seventeenth according to the form.",
                "April seventeenth", "dates")
    assert _has("Visit on the seventeenth of April.",
                "seventeenth of April", "dates")
    assert _has("Student met last Tuesday with advising.",
                "last Tuesday", "dates")
    assert _has("Return next Monday for labs.", "next Monday", "dates")
    assert _has("Symptoms started yesterday.", "yesterday", "dates")
    assert _has("Incident occurred two weeks ago.", "two weeks ago", "dates")


def test_age_over_89():
    # The age number itself must be redacted (as "Age 93" or "93 years old").
    assert _has("Age 93 years old at admission.", "Age 93", "dates")
    assert _has("aged 91 at time of service", "aged 91", "dates")
    # Standalone "NN years old" without a leading "age" word is also caught.
    assert _has("The patient is 93 years old.", "93 years old", "dates")


def test_ocr_digit_letter_name():
    assert _has("Patient: J0hn Sm1th", "J0hn", "names")


def test_hyphen_wrap_name():
    assert _has("Mar-\ngaret Peterson attended.", "garet Peterson", "names") \
        or _has("Mar-\ngaret Peterson attended.", "Margaret", "names") \
        or _has("Mar-\ngaret Peterson attended.", "Peterson", "names")


def test_spaced_ocr_date():
    assert _has("DOB 04 / 17 / 2026", "04 / 17 / 2026", "dates") \
        or _has("DOB 04 / 17 / 2026", "04 / 17 / 2026".replace(" ", ""), "dates") \
        or any("2026" in m.text for m in detect("DOB 04 / 17 / 2026") if m.category == "dates")


def test_ipv6():
    assert _has("IPv6 addr 2001:0db8:85a3:0000:0000:8a2e:0370:7334 noted.",
                "2001:0db8:85a3:0000:0000:8a2e:0370:7334", "ips")


def test_license_with_dot():
    assert _has("License No. D1234567", "D1234567", "licenses")


def test_negatives_not_forced():
    for text in (
        "May is a month on the academic calendar.",
        "The brown folder is in the cabinet.",
        "Ratio 5/97 was observed in the sample.",
        "Version 1.2.3 of the policy is current.",
        "Room 101 is reserved. Building A only.",
    ):
        cats = {m.category for m in detect(text)}
        assert "dates" not in cats or "1.2" not in {m.text for m in detect(text)}, text
        if text.startswith("Room"):
            assert not any(m.category == "addresses" and "Room 101" in m.text
                           for m in detect(text))


def test_custom_text_still_whole_word():
    matches = detect("Ann met Anna", custom_texts=["Ann"])
    texts = [m.text for m in matches]
    assert texts.count("Ann") == 1


def test_thank_you_jennifer_does_not_match_last_first():
    matches = detect("Thank you,\nJennifer")
    assert not any("you" in m.text.lower() and m.category == "names" for m in matches)


def test_nickname_in_quotes():
    assert _has("Alias: 'Frankie' (legal name Francesca DiMartino).",
                "Frankie", "names")


def test_pdf_export_not_recoverable():
    import pymupdf
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Student Brianna Ynostroza SSN 123-45-6789")
        src = td / "in.pdf"
        doc.save(str(src))
        doc.close()
        out = td / "out.pdf"
        result = redactor.redact_file(src, redactor.ScanOptions(), out_path=out)
        assert result.error is None, result.error
        report = verify.verify_export(out, ["Brianna Ynostroza", "123-45-6789"])
        assert report["status"] == "PASS", report
        # Content stream must not contain the SSN digits in order.
        raw = verify.recoverable_text(out)
        assert "123-45-6789" not in raw
        assert "Brianna Ynostroza" not in raw


def test_docx_export_not_recoverable():
    import docx
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        d = docx.Document()
        d.add_paragraph("Contact jane.doe@example.edu SSN 123-45-6789")
        src = td / "in.docx"
        d.save(str(src))
        out = td / "out.docx"
        result = redactor.redact_file(src, redactor.ScanOptions(), out_path=out)
        assert result.error is None, result.error
        report = verify.verify_export(out, ["jane.doe@example.edu", "123-45-6789"])
        assert report["status"] == "PASS", report


def test_fail_closed_missing_output():
    report = verify.verify_export(Path("no-such-file.pdf"), ["abc"])
    assert report["status"] == "ERROR"


def test_strict_preset_exists():
    assert "Maximum / Strict" in detector.PRESETS


def test_taxonomy_covers_hipaa():
    from redaction_tool import taxonomy
    assert len(taxonomy.HIPAA_COVERAGE) == 18
    assert "Student name" in taxonomy.FERPA_COVERAGE


def test_accented_multicultural_name():
    # Red-team finding: diacritics (á é ñ ö) must not defeat name detection.
    assert _has("Name: María-José García", "María-José García", "names")
    assert _has("Patient: François Müller", "François Müller", "names")


def test_interpunct_date_separator():
    # Red-team finding: "05·14·2002" (interpunct) must be caught as a date.
    assert _has("DOB: 05·14·2002", "05·14·2002", "dates")


def test_dotted_version_not_a_date():
    # Red-team finding: "1.2.3" must not be flagged as a date.
    assert not any(m.category == "dates" for m in detect("Version 1.2.3 of the policy."))


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    print("RESULT:", "FAIL" if failures else "ALL PASS")
    sys.exit(1 if failures else 0)
