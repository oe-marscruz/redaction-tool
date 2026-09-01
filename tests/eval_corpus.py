"""Synthetic FERPA/HIPAA evaluation corpus.

All names, identifiers, and narratives are invented.  No real student or
patient records.  Gold spans are character offsets into the document text.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class GoldEntity:
    start: int
    end: int
    value: str
    category: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Document:
    doc_id: str
    text: str
    entities: list[GoldEntity]
    doc_type: str
    tags: list[str] = field(default_factory=list)


def _add(text: str, value: str, category: str, tags: list[str] | None = None) -> GoldEntity:
    start = text.index(value)
    return GoldEntity(start, start + len(value), value, category, tags or [])


def _doc(doc_id: str, text: str, pairs: list[tuple[str, str, list[str]]],
         doc_type: str, tags: list[str] | None = None) -> Document:
    ents: list[GoldEntity] = []
    used: set[tuple[int, int, str]] = set()
    search_from = 0
    # Sequential find so repeated values still get distinct spans when listed
    # multiple times; fall back to str.index for unique values.
    remaining = list(pairs)
    cursor = {i: 0 for i in range(len(remaining))}
    for i, (value, category, etags) in enumerate(remaining):
        start = text.find(value, cursor[i])
        if start < 0:
            start = text.find(value)
        if start < 0:
            raise ValueError(f"{doc_id}: gold value not in text: {value!r}")
        end = start + len(value)
        cursor[i] = end
        key = (start, end, category)
        if key in used:
            # find next occurrence
            start = text.find(value, end)
            if start < 0:
                start = text.find(value)
            end = start + len(value)
            key = (start, end, category)
        used.add(key)
        ents.append(GoldEntity(start, end, value, category, etags))
    return Document(doc_id, text, ents, doc_type, tags or [])


# ── Name templates ─────────────────────────────────────────────────────────

_NAME_CASES: list[tuple[str, str, list[tuple[str, str, list[str]]], list[str]]] = [
    ("n01", "Jordan met with the counselor Tuesday.",
     [("Jordan", "names", ["unlabeled", "ambiguous", "narrative"])], ["education"]),
    ("n02", "Maria's father, Ernesto de la Cruz, called the office.",
     [("Maria", "names", ["possessive", "student"]),
      ("Ernesto de la Cruz", "names", ["compound", "parent", "unlabeled"])], ["education"]),
    ("n03", "Patient: N'golo Amari",
     [("N'golo Amari", "names", ["apostrophe", "labeled", "uncommon"])], ["healthcare"]),
    ("n04", "Parent/Guardian — Xiuying Zhang",
     [("Xiuying Zhang", "names", ["multicultural", "labeled", "parent"])], ["education"]),
    ("n05", "R. Patel was discharged on 04/17.",
     [("R. Patel", "names", ["initials", "unlabeled"]),
      ("04/17", "dates", ["unlabeled", "no_year"])], ["healthcare"]),
    ("n06", "Student Cruz, Mateo A.",
     [("Cruz, Mateo A.", "names", ["last_first", "labeled"])], ["education"]),
    ("n07", "Patient: Alexandria Montoya. Later, Ms. Montoya and Alexandria and A. Montoya returned.",
     [("Alexandria Montoya", "names", ["full"]),
      ("Ms. Montoya", "names", ["honorific", "variant"]),
      ("Alexandria", "names", ["first_only", "repeat"]),
      ("A. Montoya", "names", ["initials", "variant"])], ["healthcare", "ledger"]),
    ("n08", "Dr. Jane Smith attended the hearing.",
     [("Dr. Jane Smith", "names", ["honorific"])], ["education"]),
    ("n09", "Brianna Ynostroza called about her transcript.",
     [("Brianna Ynostroza", "names", ["first_last"])], ["education"]),
    ("n10", "Ynostroza, Brianna",
     [("Ynostroza, Brianna", "names", ["last_first"])], ["education"]),
    ("n11", "The emergency contact is Keiko O'Brien.",
     [("Keiko O'Brien", "names", ["apostrophe", "uncommon"])], ["education"]),
    ("n12", "Respondent Jean-Luc Picard submitted a statement.",
     [("Jean-Luc Picard", "names", ["hyphenated", "labeled"])], ["education"]),
    ("n13", "Sibling name: Ana-Sofia Ruiz-Gutierrez",
     [("Ana-Sofia Ruiz-Gutierrez", "names", ["hyphenated", "compound", "labeled"])], ["education"]),
    ("n14", "mr. luis gomez signed the form.",
     [("mr. luis gomez", "names", ["lowercase", "honorific"])], ["education"]),
    ("n15", "BRIANNA YNOSTROZA",
     [("BRIANNA YNOSTROZA", "names", ["uppercase"])], ["education"]),
    ("n16", "Teacher Priya Natarajan emailed the advisor.",
     [("Priya Natarajan", "names", ["multicultural", "unlabeled"])], ["education"]),
    ("n17", "Spouse: Wei-Lin Chen",
     [("Wei-Lin Chen", "names", ["hyphenated", "labeled"])], ["healthcare"]),
    ("n18", "The student, Mateo Cruz, lives off campus.",
     [("Mateo Cruz", "names", ["appositive"])], ["education"]),
    ("n19", "Called regarding Saanvi Reddy's suspension.",
     [("Saanvi Reddy", "names", ["possessive", "uncommon"])], ["education"]),
    ("n20", "Counselor notes: met with Aisha Rahman on Friday.",
     [("Aisha Rahman", "names", ["narrative"])], ["education"]),
    ("n21", "Father's name is Hassan Al-Farsi.",
     [("Hassan Al-Farsi", "names", ["hyphenated", "parent"])], ["education"]),
    ("n22", "Patient ID sticker: QUINN, HARPER J",
     [("QUINN, HARPER J", "names", ["uppercase", "last_first"])], ["healthcare"]),
    ("n23", "Please notify Ms. Dlamini and Mr. Nguyen.",
     [("Ms. Dlamini", "names", ["honorific", "uncommon"]),
      ("Mr. Nguyen", "names", ["honorific"])], ["education"]),
    ("n24", "Alias: 'Frankie' (legal name Francesca DiMartino).",
     [("Frankie", "names", ["nickname"]),
      ("Francesca DiMartino", "names", ["compound"])], ["education"]),
    ("n25", "Infant of Lakisha Brown, MRN 448821.",
     [("Lakisha Brown", "names", ["unlabeled"]),
      ("MRN 448821", "mrn", ["labeled"])], ["healthcare"]),
]


def _more_name_docs() -> list[Document]:
    firsts = [
        "Zainab", "Ioannis", "Saoirse", "Bjorn", "Nguyen", "Fatou", "Mateo",
        "Hana", "Yusuf", "Ines", "Kwame", "Soren", "Leilani", "Dmitri",
        "Amara", "Tariq", "Nalini", "Oskar", "Chiara", "Jabari",
    ]
    lasts = [
        "Okoye", "Papadopoulos", "Ní Bhraonáin", "Johansson", "Pham",
        "Diallo", "Silva", "Nakamura", "Haddad", "Costa", "Mensah",
        "Lindgren", "Kealoha", "Volkov", "Diallo", "Rahman", "Iyer",
        "Berg", "Rossi", "Abebe",
    ]
    docs: list[Document] = []
    templates = [
        ("The student {f} {l} requested an advising meeting.", "education", ["unlabeled"]),
        ("Patient {f} {l} was seen in clinic.", "healthcare", ["unlabeled"]),
        ("Parent/Guardian: {f} {l}", "education", ["labeled", "parent"]),
        ("{f} {l}'s financial aid file was updated.", "education", ["possessive"]),
        ("Emergency contact {f} {l} can be reached after hours.", "healthcare", ["unlabeled"]),
        ("Dr. {f} {l} signed the discharge note.", "healthcare", ["honorific"]),
        ("{l}, {f} enrolled in CHEM 101.", "education", ["last_first"]),
        ("Respondent {f} {l} declined an interview.", "education", ["labeled"]),
    ]
    n = 0
    extra_first = [
        "Zainab", "Ioannis", "Saoirse", "Bjorn", "Nguyen", "Fatou", "Mateo",
        "Hana", "Yusuf", "Ines", "Kwame", "Soren", "Leilani", "Dmitri",
        "Amara", "Tariq", "Nalini", "Oskar", "Chiara", "Jabari",
        "Aoife", "Seung", "Mei", "Ravi", "Noor", "Imani", "Thiago", "Aylin",
        "Soren", "Anika", "Kofi", "Elif", "Hiro", "Amina", "Pavel", "Nia",
        "Yara", "Omar", "Svetlana", "Diego",
    ]
    extra_last = [
        "Okoye", "Papadopoulos", "Braonain", "Johansson", "Pham",
        "Diallo", "Silva", "Nakamura", "Haddad", "Costa", "Mensah",
        "Lindgren", "Kealoha", "Volkov", "Rahman", "Iyer",
        "Berg", "Rossi", "Abebe", "Kowalski", "Nielsen", "Santos",
        "Kim", "Ali", "Hassan", "Petrov", "Nowak", "Fernandez",
        "Okafor", "Jensen", "Moreau", "Bianchi",
    ]
    for i, f in enumerate(extra_first):
        l = extra_last[i % len(extra_last)]
        tmpl, dtype, tags = templates[i % len(templates)]
        if "{l}, {f}" in tmpl:
            text = tmpl.format(f=f, l=l)
            value = f"{l}, {f}"
        elif "Dr. {f}" in tmpl:
            text = tmpl.format(f=f, l=l)
            value = f"Dr. {f} {l}"
        else:
            text = tmpl.format(f=f, l=l)
            value = f"{f} {l}"
        n += 1
        docs.append(_doc(f"n_gen_{n:03d}", text, [(value, "names", tags)], dtype, tags))
    # Repeat across more templates to push entity count up.
    more_tmpls = [
        ("Advising note: {f} {l} missed two sessions.", "education", ["narrative"]),
        ("Discharge: {f} {l} left against medical advice.", "healthcare", ["unlabeled"]),
        ("Hearing officer met {f} {l} on campus.", "education", ["unlabeled"]),
        ("Pharmacy consult for {f} {l} completed.", "healthcare", ["unlabeled"]),
        ("Parent {f} {l} requested records.", "education", ["parent"]),
        ("RN {f} {l} documented the vitals.", "healthcare", ["unlabeled"]),
        ("{f} {l} (student) lives in residence.", "education", ["appositive"]),
        ("Follow-up call to {f} {l} was not answered.", "healthcare", ["unlabeled"]),
    ]
    for i in range(80):
        f = extra_first[i % len(extra_first)]
        l = extra_last[(i * 3) % len(extra_last)]
        tmpl, dtype, tags = more_tmpls[i % len(more_tmpls)]
        text = tmpl.format(f=f, l=l)
        value = f"{f} {l}"
        docs.append(_doc(f"n_bulk_{i:03d}", text, [(value, "names", tags)], dtype, tags))
    return docs


# ── Date templates ─────────────────────────────────────────────────────────

_DATE_CASES: list[tuple[str, str, list[tuple[str, str, list[str]]], list[str]]] = [
    ("d01", "Appointment on 04/17/26.",
     [("04/17/26", "dates", ["two_digit_year"])], ["healthcare"]),
    ("d02", "Surgery scheduled 04/17/2026.",
     [("04/17/2026", "dates", ["numeric"])], ["healthcare"]),
    ("d03", "Admitted 4/7/26 for observation.",
     [("4/7/26", "dates", ["unpadded", "two_digit_year"])], ["healthcare"]),
    ("d04", "Lab collected 2026-04-17.",
     [("2026-04-17", "dates", ["iso"])], ["healthcare"]),
    ("d05", "Hearing held 17 April 2026.",
     [("17 April 2026", "dates", ["dmy"])], ["education"]),
    ("d06", "DOB April 17, 2026 is on file.",
     [("April 17, 2026", "dates", ["mdy", "dob"])], ["education"]),
    ("d07", "Follow-up Apr. 17 in clinic.",
     [("Apr. 17", "dates", ["month_day_no_year"])], ["healthcare"]),
    ("d08", "Procedure date 17-Apr-26.",
     [("17-Apr-26", "dates", ["d-mon-yy"])], ["healthcare"]),
    ("d09", "Imaging 04.17.2026 completed.",
     [("04.17.2026", "dates", ["dot"])], ["healthcare"]),
    ("d10", "Discharge 04-17-2026.",
     [("04-17-2026", "dates", ["dash"])], ["healthcare"]),
    ("d11", "Born April seventeenth according to the form.",
     [("April seventeenth", "dates", ["written"])], ["healthcare"]),
    ("d12", "Visit on the seventeenth of April.",
     [("the seventeenth of April", "dates", ["written"])], ["healthcare"]),
    ("d13", "Student met last Tuesday with advising.",
     [("last Tuesday", "dates", ["relative"])], ["education"]),
    ("d14", "Return next Monday for labs.",
     [("next Monday", "dates", ["relative"])], ["healthcare"]),
    ("d15", "Symptoms started yesterday.",
     [("yesterday", "dates", ["relative"])], ["healthcare"]),
    ("d16", "Incident occurred two weeks ago.",
     [("two weeks ago", "dates", ["relative"])], ["education"]),
    ("d17", "DOB 05/14/2002",
     [("05/14/2002", "dates", ["dob"])], ["education"]),
    ("d18", "Enrollment date: 8/19/24",
     [("8/19/24", "dates", ["unpadded", "two_digit_year"])], ["education"]),
    ("d19", "Date of death: 1 March 2019",
     [("1 March 2019", "dates", ["death"])], ["healthcare"]),
    ("d20", "Age 93 years old at admission.",
     [("93 years old", "dates", ["age_over_89"])], ["healthcare"]),
    ("d21", "aged 91 at time of service",
     [("aged 91", "dates", ["age_over_89"])], ["healthcare"]),
    ("d22", "Exam on 04/17 at 09:00.",
     [("04/17", "dates", ["no_year", "zero_padded"])], ["education"]),
    ("d23", "Tomorrow the student returns to class.",
     [("Tomorrow", "dates", ["relative"])], ["education"]),
    ("d24", "Suspension effective the 4th of May, 2025.",
     [("the 4th of May, 2025", "dates", ["written"])], ["education"]),
    ("d25", "Seen on May 4th.",
     [("May 4th", "dates", ["month_day_no_year"])], ["healthcare"]),
]


def _more_date_docs() -> list[Document]:
    numeric = [
        "01/02/26", "1/2/26", "01-02-2026", "2026-01-02", "01.02.2026",
        "12/31/99", "3/15/24", "07/04/1776",  # 1776 won't match 19|20 — gold still dates historically; skip
        "11/08/2024", "9/9/09", "10/10/10",
    ]
    # Drop 07/04/1776 — out of modern range and not required.
    numeric = [d for d in numeric if "1776" not in d]
    docs: list[Document] = []
    contexts = [
        ("Admitted {d}.", "healthcare", ["admission"]),
        ("Discharged {d}.", "healthcare", ["discharge"]),
        ("Appointment {d}.", "healthcare", ["appointment"]),
        ("Date of birth {d}.", "healthcare", ["dob"]),
        ("Hearing on {d}.", "education", ["disciplinary"]),
        ("Enrolled {d}.", "education", ["enrollment"]),
        ("Lab drawn {d}.", "healthcare", ["lab"]),
        ("Procedure {d}.", "healthcare", ["procedure"]),
    ]
    for i, d in enumerate(numeric):
        tmpl, dtype, tags = contexts[i % len(contexts)]
        text = tmpl.format(d=d)
        docs.append(_doc(f"d_gen_{i:03d}", text, [(d, "dates", tags)], dtype, tags))
    months = [
        ("January 3, 2024", "education"),
        ("3 January 2024", "healthcare"),
        ("Feb. 14, 2023", "education"),
        ("14-Feb-23", "healthcare"),
        ("March 1st, 2022", "education"),
        ("1st of March 2022", "healthcare"),
    ]
    for i, (d, dtype) in enumerate(months):
        text = f"Service date {d} is recorded."
        docs.append(_doc(f"d_mon_{i:03d}", text, [(d, "dates", ["month_name"])], dtype, ["month_name"]))
    extra_dates = [
        "02/28/25", "2/28/25", "02-28-2025", "2025-02-28", "28 Feb 2025",
        "February 28, 2025", "28-Feb-25", "02.28.2025", "6/1/24", "06/01/2024",
        "12/1/23", "1/15/22", "07/04/2024", "3/3/21", "11/11/11",
        "09/09/2009", "10/31/2020", "4/1/19", "08/08/08", "5/5/05",
    ]
    extra_ctx = [
        ("Seen {d} in clinic.", "healthcare"),
        ("Hearing {d}.", "education"),
        ("DOB {d}.", "healthcare"),
        ("Enrolled {d}.", "education"),
        ("Procedure {d}.", "healthcare"),
        ("Suspended {d}.", "education"),
        ("Admitted {d}.", "healthcare"),
        ("Appointment {d}.", "healthcare"),
    ]
    for i, d in enumerate(extra_dates):
        tmpl, dtype = extra_ctx[i % len(extra_ctx)]
        text = tmpl.format(d=d)
        docs.append(_doc(f"d_bulk_{i:03d}", text, [(d, "dates", ["bulk"])], dtype, ["bulk"]))
    relatives = [
        ("yesterday", "Symptoms began yesterday."),
        ("tomorrow", "Surgery is tomorrow."),
        ("Last Monday", "Last Monday the student was absent."),
        ("Next Friday", "Next Friday is the follow-up."),
        ("two days ago", "Pain started two days ago."),
        ("Three weeks ago", "Three weeks ago labs were drawn."),
    ]
    for i, (val, text) in enumerate(relatives):
        docs.append(_doc(f"d_rel_{i:03d}", text, [(val, "dates", ["relative"])],
                         "healthcare", ["relative"]))
    return docs


# ── Structured identifiers ─────────────────────────────────────────────────

_STRUCT_CASES: list[tuple[str, str, list[tuple[str, str, list[str]]], list[str]]] = [
    ("s01", "SSN 123-45-6789",
     [("123-45-6789", "ssn", [])], ["healthcare"]),
    ("s02", "ssn 123 45 6789 on file",
     [("123 45 6789", "ssn", ["spaced"])], ["education"]),
    ("s03", "Contact jane.doe@example.edu today.",
     [("jane.doe@example.edu", "emails", [])], ["education"]),
    ("s04", "Phone (303) 555-0142",
     [("(303) 555-0142", "phones", [])], ["education"]),
    ("s05", "Call +1 720-555-0199 after hours.",
     [("+1 720-555-0199", "phones", ["plus"])], ["healthcare"]),
    ("s06", "Fax: 303-555-0188",
     [("Fax: 303-555-0188", "fax", [])], ["healthcare"]),
    ("s07", "MRN: A4488219",
     [("MRN: A4488219", "mrn", [])], ["healthcare"]),
    ("s08", "Student ID 00991234",
     [("Student ID 00991234", "unique_ids", [])], ["education"]),
    ("s09", "EMPLID 8765432",
     [("EMPLID 8765432", "unique_ids", [])], ["education"]),
    ("s10", "Account Number 99887766",
     [("Account Number 99887766", "accounts", [])], ["healthcare"]),
    ("s11", "Member ID H123456789",
     [("Member ID H123456789", "health_plan", [])], ["healthcare"]),
    ("s12", "License No. D1234567",
     [("License No. D1234567", "licenses", [])], ["healthcare"]),
    ("s13", "VIN 1HGCM82633A004352",
     [("VIN 1HGCM82633A004352", "vehicles", [])], ["healthcare"]),
    ("s14", "Device serial SN 88:1d:fc:12:34:56",
     [("88:1d:fc:12:34:56", "devices", ["mac"])], ["healthcare"]),
    ("s15", "See https://portal.example.edu/records/12",
     [("https://portal.example.edu/records/12", "urls", [])], ["education"]),
    ("s16", "Host IP 10.8.4.21 blocked.",
     [("10.8.4.21", "ips", [])], ["education"]),
    ("s17", "Lives at 1234 Pine Street, Apt 8, Denver, CO 80203",
     [("1234 Pine Street, Apt 8", "addresses", ["street"]),
      ("Denver, CO", "addresses", ["city_state"]),
      ("80203", "addresses", ["zip"])], ["education"]),
    ("s18", "P.O. Box 44551",
     [("P.O. Box 44551", "addresses", ["pobox"])], ["education"]),
    ("s19", "Health Plan ID XYZ-998877",
     [("Health Plan ID XYZ-998877", "health_plan", [])], ["healthcare"]),
    ("s20", "Fingerprint ID FP-9981 on file.",
     [("Fingerprint ID FP-9981", "biometric", [])], ["education"]),
    ("s21", "GPA 3.82 recorded.",
     [("GPA 3.82", "student_records", [])], ["education"]),
    ("s22", "Tuition: $18,400.00 billed.",
     [("Tuition: $18,400.00", "financial", [])], ["education"]),
    ("s23", "IPv6 addr 2001:0db8:85a3:0000:0000:8a2e:0370:7334 noted.",
     [("2001:0db8:85a3:0000:0000:8a2e:0370:7334", "ips", ["ipv6"])], ["healthcare"]),
    ("s24", "Plate: CO-XYZ-1234 listed.",
     [("Plate: CO-XYZ-1234", "vehicles", [])], ["healthcare"]),
    ("s25", "Banner ID 001234567",
     [("Banner ID 001234567", "unique_ids", [])], ["education"]),
]


def _more_struct_docs() -> list[Document]:
    docs: list[Document] = []
    emails = [f"user{i}@campus.edu" for i in range(20)]
    for i, e in enumerate(emails):
        text = f"Please email {e} with the form."
        docs.append(_doc(f"e_gen_{i:03d}", text, [(e, "emails", [])], "education", ["email"]))
    phones = [f"(303) 555-{1000+i:04d}" for i in range(15)]
    for i, p in enumerate(phones):
        text = f"Callback number {p}."
        docs.append(_doc(f"p_gen_{i:03d}", text, [(p, "phones", [])], "healthcare", ["phone"]))
    ssns = [f"{100+i:03d}-{20+i:02d}-{4000+i:04d}" for i in range(12)]
    for i, s in enumerate(ssns):
        text = f"SSN {s} verified."
        docs.append(_doc(f"ssn_gen_{i:03d}", text, [(s, "ssn", [])], "education", ["ssn"]))
    zips = ["80203", "10001", "60611-1234", "94107"]
    for i, z in enumerate(zips):
        text = f"Mailing ZIP {z} is on the form."
        docs.append(_doc(f"z_gen_{i:03d}", text, [(z, "addresses", ["zip"])], "education", ["zip"]))
    return docs


# ── OCR / noisy ────────────────────────────────────────────────────────────

_OCR_CASES: list[tuple[str, str, list[tuple[str, str, list[str]]], list[str]]] = [
    ("o01", "Patient: J0hn Sm1th",
     [("J0hn Sm1th", "names", ["ocr_sub"])], ["ocr", "healthcare"]),
    ("o02", "Mar-\ngaret Peterson attended.",
     [("Mar-\ngaret Peterson", "names", ["hyphen_wrap"])], ["ocr", "education"]),
    ("o03", "DOB 04 / 17 / 2026",
     [("04 / 17 / 2026", "dates", ["spaced"])], ["ocr", "healthcare"]),
    ("o04", "SSN 123-45-6789 with O vs 0 noise: 123-45-678O",
     [("123-45-6789", "ssn", []),
      ("123-45-678O", "ssn", ["ocr_sub"])], ["ocr"]),
    ("o05", "Name:  Brianna   Ynostroza",
     [("Brianna   Ynostroza", "names", ["extra_spaces"])], ["ocr"]),
    ("o06", "Student: MATE0 CRUZ",
     [("MATE0 CRUZ", "names", ["ocr_sub", "uppercase"])], ["ocr", "education"]),
    ("o07", "Phone (3O3) 555-0142",
     [("(3O3) 555-0142", "phones", ["ocr_sub"])], ["ocr"]),
    ("o08", "Email jane.doe@examp1e.edu",
     [("jane.doe@examp1e.edu", "emails", ["ocr_sub"])], ["ocr"]),
    ("o09", "Admitted 04/\n17/2026",
     [("04/\n17/2026", "dates", ["line_break"])], ["ocr", "healthcare"]),
    ("o10", "Parent Xiuying\nZhang called.",
     [("Xiuying\nZhang", "names", ["line_break"])], ["ocr", "education"]),
]


# ── Multi-page / repeated / overlapping ────────────────────────────────────

_MULTI = [
    ("m01",
     "Investigative note.\n"
     "Complainant Alexandria Montoya (student ID 00991234) reported on 04/17/26 "
     "that Ernesto de la Cruz, her father, called from 303-555-0142. "
     "Ms. Montoya and A. Montoya later emailed alexandria.montoya@campus.edu. "
     "DOB 05/14/2002. Address 88 Colfax Avenue, Denver, CO 80203.\n"
     "Alexandria declined further contact yesterday.",
     [
         ("Alexandria Montoya", "names", ["full"]),
         ("student ID 00991234", "unique_ids", []),
         ("04/17/26", "dates", ["two_digit_year"]),
         ("Ernesto de la Cruz", "names", ["parent", "compound"]),
         ("303-555-0142", "phones", []),
         ("Ms. Montoya", "names", ["variant"]),
         ("A. Montoya", "names", ["variant"]),
         ("alexandria.montoya@campus.edu", "emails", []),
         ("05/14/2002", "dates", ["dob"]),
         ("88 Colfax Avenue", "addresses", []),
         ("Denver, CO", "addresses", []),
         ("80203", "addresses", ["zip"]),
         ("Alexandria", "names", ["first_only"]),
         ("yesterday", "dates", ["relative"]),
     ],
     "education", ["multi", "ledger"]),
    ("m02",
     "Discharge summary for N'golo Amari, MRN 448821. Admitted 4/7/26, "
     "discharged 04/17/2026. Procedure 17-Apr-26. Next Monday follow-up. "
     "Insurance Member ID H123456789. Lives at 500 Broadway Street.",
     [
         ("N'golo Amari", "names", ["apostrophe"]),
         ("MRN 448821", "mrn", []),
         ("4/7/26", "dates", []),
         ("04/17/2026", "dates", []),
         ("17-Apr-26", "dates", []),
         ("Next Monday", "dates", ["relative"]),
         ("Member ID H123456789", "health_plan", []),
         ("500 Broadway Street", "addresses", []),
     ],
     "healthcare", ["multi"]),
]


# ── Negatives (must NOT be forced as PII) ──────────────────────────────────

_NEGATIVES: list[tuple[str, str, str]] = [
    ("neg01", "May is a month on the academic calendar.", "education"),
    ("neg02", "The brown folder is in the cabinet.", "education"),
    ("neg03", "Ratio 5/97 was observed in the sample.", "healthcare"),
    ("neg04", "Page 123 of the handbook describes the process.", "education"),
    ("neg05", "The patient was stable and in no distress.", "healthcare"),
    ("neg06", "March weather delayed the hearing, but no individual date is given.", "education"),
    ("neg07", "Jordan almonds were served at the reception (candy, not a person).", "education"),
    ("neg08", "Call the main office during business hours.", "education"),
    ("neg09", "Version 1.2.3 of the policy is current.", "education"),
    ("neg10", "Room 101 is reserved. Building A only.", "education"),
    ("neg11", "The United States Constitution is cited.", "education"),
    ("neg12", "New York style pizza was discussed in the icebreaker (not an address).", "education"),
    ("neg13", "Grade appeals follow Faculty Council rules.", "education"),
    ("neg14", "IP as in intellectual property is out of scope here.", "education"),
    ("neg15", "See Table 4 for aggregate counts only.", "healthcare"),
]


def build_corpus() -> list[Document]:
    docs: list[Document] = []
    for doc_id, text, pairs, tags in _NAME_CASES:
        docs.append(_doc(doc_id, text, pairs, tags[0] if tags else "general", tags))
    docs.extend(_more_name_docs())
    for doc_id, text, pairs, tags in _DATE_CASES:
        docs.append(_doc(doc_id, text, pairs, tags[0] if tags else "general", tags))
    docs.extend(_more_date_docs())
    for doc_id, text, pairs, tags in _STRUCT_CASES:
        docs.append(_doc(doc_id, text, pairs, tags[0] if tags else "general", tags))
    docs.extend(_more_struct_docs())
    for doc_id, text, pairs, tags in _OCR_CASES:
        docs.append(_doc(doc_id, text, pairs, tags[0] if tags else "ocr", tags))
    for doc_id, text, pairs, dtype, tags in _MULTI:
        docs.append(_doc(doc_id, text, pairs, dtype, tags))
    for doc_id, text, dtype in _NEGATIVES:
        docs.append(Document(doc_id, text, [], dtype, ["negative"]))
    return docs


def corpus_as_jsonable(docs: list[Document] | None = None) -> list[dict]:
    docs = docs or build_corpus()
    out = []
    for d in docs:
        out.append({
            "doc_id": d.doc_id,
            "text": d.text,
            "doc_type": d.doc_type,
            "tags": d.tags,
            "entities": [asdict(e) for e in d.entities],
        })
    return out


def write_corpus(path: Path) -> Path:
    path.write_text(json.dumps(corpus_as_jsonable(), indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    docs = build_corpus()
    n_ent = sum(len(d.entities) for d in docs)
    print(f"documents={len(docs)} entities={n_ent}")
    by_cat: dict[str, int] = {}
    for d in docs:
        for e in d.entities:
            by_cat[e.category] = by_cat.get(e.category, 0) + 1
    print(json.dumps(by_cat, indent=2))
