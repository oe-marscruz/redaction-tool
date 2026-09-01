"""Canonical FERPA/HIPAA-oriented detection taxonomy.

Detection (what was found) is separate from redaction policy (whether a
profile removes it).  Software output is not a legal compliance determination.

References:
- FERPA PII: 34 CFR § 99.3
- HIPAA Safe Harbor: 45 CFR § 164.514(b)(2)
"""

from __future__ import annotations

from dataclasses import dataclass

# Internal taxonomy keys.  Detector ``Match.category`` values remain the
# historical GUI keys (names, dates, ssn, ...) so existing presets keep
# working; ``Match.entity_type`` carries the finer type when known.

PERSON_NAME = "PERSON_NAME"
STUDENT_NAME = "STUDENT_NAME"
PATIENT_NAME = "PATIENT_NAME"
PARENT_NAME = "PARENT_NAME"
RELATIVE_NAME = "RELATIVE_NAME"
EMPLOYER_NAME_WHEN_IDENTIFYING = "EMPLOYER_NAME_WHEN_IDENTIFYING"
ADDRESS = "ADDRESS"
CITY = "CITY"
COUNTY = "COUNTY"
ZIP_CODE = "ZIP_CODE"
PHONE = "PHONE"
FAX = "FAX"
EMAIL = "EMAIL"
SSN = "SSN"
STUDENT_ID = "STUDENT_ID"
MEDICAL_RECORD_NUMBER = "MEDICAL_RECORD_NUMBER"
HEALTH_PLAN_NUMBER = "HEALTH_PLAN_NUMBER"
ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
LICENSE_NUMBER = "LICENSE_NUMBER"
VEHICLE_IDENTIFIER = "VEHICLE_IDENTIFIER"
DEVICE_IDENTIFIER = "DEVICE_IDENTIFIER"
URL = "URL"
IP_ADDRESS = "IP_ADDRESS"
BIOMETRIC_IDENTIFIER = "BIOMETRIC_IDENTIFIER"
DATE = "DATE"
DATE_OF_BIRTH = "DATE_OF_BIRTH"
DATE_OF_DEATH = "DATE_OF_DEATH"
ADMISSION_DATE = "ADMISSION_DATE"
DISCHARGE_DATE = "DISCHARGE_DATE"
SERVICE_DATE = "SERVICE_DATE"
APPOINTMENT_DATE = "APPOINTMENT_DATE"
PROCEDURE_DATE = "PROCEDURE_DATE"
LAB_DATE = "LAB_DATE"
AGE_OVER_89 = "AGE_OVER_89"
PLACE_OF_BIRTH = "PLACE_OF_BIRTH"
MOTHERS_MAIDEN_NAME = "MOTHERS_MAIDEN_NAME"
UNIQUE_IDENTIFIER = "UNIQUE_IDENTIFIER"
INDIRECT_IDENTIFIER = "INDIRECT_IDENTIFIER"
OTHER_REIDENTIFICATION_RISK = "OTHER_REIDENTIFICATION_RISK"
RELATIVE_TEMPORAL = "RELATIVE_TEMPORAL"

# Detector category key → default taxonomy type
CATEGORY_TO_ENTITY: dict[str, str] = {
    "names": PERSON_NAME,
    "addresses": ADDRESS,
    "dates": DATE,
    "phones": PHONE,
    "fax": FAX,
    "emails": EMAIL,
    "ssn": SSN,
    "mrn": MEDICAL_RECORD_NUMBER,
    "health_plan": HEALTH_PLAN_NUMBER,
    "accounts": ACCOUNT_NUMBER,
    "licenses": LICENSE_NUMBER,
    "vehicles": VEHICLE_IDENTIFIER,
    "devices": DEVICE_IDENTIFIER,
    "urls": URL,
    "ips": IP_ADDRESS,
    "biometric": BIOMETRIC_IDENTIFIER,
    "unique_ids": UNIQUE_IDENTIFIER,
    "student_records": INDIRECT_IDENTIFIER,
    "financial": INDIRECT_IDENTIFIER,
    "custom": OTHER_REIDENTIFICATION_RISK,
}

# Confidence bands.  Lower-confidence hits are still returned; they are
# never silently dropped.  Profiles may surface them for review.
CONFIRMED = "confirmed"
LIKELY = "likely"
POSSIBLE = "possible"

CONFIDENCE_SCORE = {CONFIRMED: 1.0, LIKELY: 0.85, POSSIBLE: 0.6}


@dataclass(frozen=True)
class PolicyProfile:
    """Redaction policy: which detector categories a profile enables.

    This is not a legal opinion.  Directory-information exceptions under
    FERPA, and the HIPAA 'actual knowledge' residual-risk test, require a
    human determination this tool cannot make.
    """

    key: str
    label: str
    categories: tuple[str, ...]
    notes: str


# Category keys must match detector.CATEGORY_MAP / PRESETS.
_FERPA_CATS = (
    "names", "addresses", "dates", "phones", "emails", "ssn",
    "unique_ids", "student_records", "financial",
)
_HIPAA_CATS = (
    "names", "addresses", "dates", "phones", "fax", "emails",
    "ssn", "mrn", "health_plan", "accounts", "licenses",
    "vehicles", "devices", "urls", "ips", "biometric", "unique_ids",
)
_ALL_CATS = _FERPA_CATS + tuple(c for c in _HIPAA_CATS if c not in _FERPA_CATS)

PROFILES: dict[str, PolicyProfile] = {
    "general": PolicyProfile(
        key="general",
        label="General PII",
        categories=_ALL_CATS,
        notes="High-recall general PII. Not a regulatory certification.",
    ),
    "ferpa": PolicyProfile(
        key="ferpa",
        label="FERPA-oriented",
        categories=_FERPA_CATS,
        notes=(
            "Targets 34 CFR § 99.3 PII in education records (names of the "
            "student and family, address, personal identifiers, DOB, place "
            "of birth, mother's maiden name, and other indirect identifiers). "
            "Directory-information fields may be public unless the student "
            "opted out; this profile still redacts them because this tool is "
            "used on investigative/case files, not directory publications. "
            "A reviewer must decide whether a given field is directory info."
        ),
    ),
    "hipaa": PolicyProfile(
        key="hipaa",
        label="HIPAA Safe Harbor-oriented",
        categories=_HIPAA_CATS,
        notes=(
            "Targets the 18 Safe Harbor identifier categories in 45 CFR "
            "§ 164.514(b)(2), including dates more specific than year when "
            "related to an individual, ages over 89, and identifiers of "
            "relatives, employers, and household members when they appear "
            "as names/addresses/phones. Full-face photos and biometric "
            "images are not auto-detected."
        ),
    ),
    "strict": PolicyProfile(
        key="strict",
        label="Maximum / Strict",
        categories=_ALL_CATS,
        notes=(
            "Recall-first: enables every detector category and keeps "
            "lower-confidence name/date candidates. Higher false-positive "
            "rate by design."
        ),
    ),
}

# HIPAA Safe Harbor identifier → detector coverage.
# "partial" means some but not all surface forms; "manual" means a human
# must add a box / extra literal; "gap" means not implemented.
HIPAA_COVERAGE: dict[str, tuple[str, str]] = {
    "1 Names": ("partial", "Labeled, honorific, dictionary, Title-Case, ledger variants. Uncommon unlabeled single tokens still missed without context."),
    "2 Geographic subdivisions smaller than a state": ("partial", "Street addresses, PO boxes, ZIP/ZIP+4, City+State. No full USPS gazetteer; counties/precincts unlabeled often missed. ZIP 3-digit Safe Harbor generalization is NOT applied — 5-digit ZIPs are removed entirely."),
    "3 Dates more specific than year + age >89": ("partial", "Absolute numeric/month dates including 2-digit years; some written and relative forms. Does not convert remaining dates to year-only (removal, not generalization)."),
    "4 Telephone numbers": ("yes", "US formats including +1."),
    "5 Fax numbers": ("partial", "Only when labeled Fax/Facsimile."),
    "6 Email addresses": ("yes", ""),
    "7 Social Security numbers": ("partial", "Dashed/spaced/labeled. Bare 9-digit caught as unique_ids when 7–10 digits."),
    "8 Medical record numbers": ("partial", "Context-anchored MRN / Medical Record."),
    "9 Health plan beneficiary numbers": ("partial", "Context-anchored."),
    "10 Account numbers": ("partial", "Context-anchored."),
    "11 Certificate/license numbers": ("partial", "Context-anchored."),
    "12 Vehicle identifiers and plates": ("partial", "Context-anchored VIN/plate labels. Bare 17-char VIN shape added."),
    "13 Device identifiers and serials": ("partial", "MAC addresses + labeled serials."),
    "14 URLs": ("yes", "http(s) and www."),
    "15 IP addresses": ("partial", "IPv4. IPv6 added as best-effort."),
    "16 Biometric identifiers": ("partial", "Text references only, not images."),
    "17 Full-face photographs": ("gap", "Not auto-detected. Manual review required."),
    "18 Other unique identifying numbers/codes": ("partial", "Labeled student/employee/case IDs and bare 7–10 digit tokens."),
}

FERPA_COVERAGE: dict[str, tuple[str, str]] = {
    "Student name": ("partial", "Same name detector as HIPAA #1."),
    "Parent / family names": ("partial", "Labeled parent/guardian/relative patterns + ledger."),
    "Student or family address": ("partial", "Same as HIPAA #2."),
    "Social Security number": ("partial", "Same as HIPAA #7."),
    "Student number / institutional ID": ("partial", "Labeled + unique_ids."),
    "Biometric record": ("partial", "Text references only."),
    "Date of birth": ("partial", "Labeled DOB + generic date detector."),
    "Place of birth": ("partial", "Labeled fields only."),
    "Mother's maiden name": ("partial", "Labeled fields only."),
    "Indirect identifiers / combinations": ("partial", "GPA/grades/financial amounts. Combinatorial re-identification is not modeled."),
    "Directory information exception": ("policy", "Not automatically applied. Reviewer decision."),
}


def entity_type_for(category: str, override: str = "") -> str:
    if override:
        return override
    return CATEGORY_TO_ENTITY.get(category, OTHER_REIDENTIFICATION_RISK)
