"""High-recall person-name detection.

Detection is independent of redaction policy.  Ambiguous tokens (May, Jordan,
Brown) require person-context or a document-level ledger hit; they are not
blindly redacted.
"""

from __future__ import annotations

import re

# Tokens that are almost never the first word of a person name.
_FIRST_STOP = frozenset({
    "a", "an", "the", "this", "that", "these", "those", "please", "see", "call",
    "lives", "host", "version", "room", "grade", "new", "united", "ratio",
    "page", "building", "follow", "return", "symptoms", "incident", "hearing",
    "enrollment", "appointment", "surgery", "lab", "imaging", "discharge",
    "exam", "suspension", "seen", "born", "visit", "service", "date", "student",
    "patient", "parent", "guardian", "respondent", "sibling", "spouse", "father",
    "mother", "teacher", "counselor", "emergency", "infant", "alias",
    "complainant", "investigative", "contact", "phone", "email", "fax",
    "account", "member", "license", "device", "health", "banner", "fingerprint",
    "tuition", "plate", "address", "mailing", "callback", "ssn", "dob", "mrn",
    "vin", "ip", "zip", "on", "in", "at", "for", "with", "from", "after",
    "before", "during", "admitted", "discharged", "enrolled", "procedure",
    "next", "last", "tomorrow", "yesterday", "today", "age", "aged", "office",
    "university", "college", "hospital", "clinic", "department", "school",
    "campus", "table", "figure", "policy", "summary", "note", "report",
    "record", "file", "form", "number", "street", "avenue", "road", "drive",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december", "jan", "feb", "mar", "apr",
    "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    "dr", "mr", "mrs", "ms", "miss", "prof", "professor", "mx",
    "dear", "hello", "hi", "hey", "thanks", "thank", "sincerely", "regards",
    "best", "warm", "cheers", "from", "subject", "sent", "attention",
})

# Last-token words that indicate a place, date, or document artifact.
_LAST_STOP = frozenset({
    "street", "st", "avenue", "ave", "road", "rd", "drive", "dr", "lane", "ln",
    "court", "ct", "circle", "cir", "boulevard", "blvd", "way", "place", "pl",
    "terrace", "ter", "highway", "hwy", "parkway", "pkwy", "trail", "trl",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "university", "college", "hospital", "clinic", "county", "state",
    "department", "office", "school", "campus", "building", "room", "page",
    "table", "figure", "version", "policy", "council", "constitution",
    "summary", "note", "report", "record", "file", "form", "number", "id",
    "llc", "inc", "corp", "ltd", "company", "center", "centre", "institute",
    "district", "division", "unit", "team", "committee", "board",
    "edu", "com", "org", "net", "gov",
})

# Lowercase particles that appear inside compound surnames.
_PARTICLES = (
    r"d[aeio]|del|della|dei|des|du|la|le|los|las|van(?:\s+den|\s+der|\s+de)?"
    r"|von|el|al|bin|ibn|ten|ter|di|da|do|dos|das|st\.?"
)

# Honorifics.  Miss is listed before Ms so the longer alternative wins inside
# a case-insensitive group when both could apply; in practice they don't.
_HONORIFIC = r"Mr|Mrs|Ms|Miss|Dr|Prof(?:essor)?|Mx|Sir|Madam|Rev|Hon"

# A single name token: Xiuying, N'golo, O'Brien, Jean-Luc, QUINN, J0hn (OCR).
# ACCENT covers common Latin-script diacritics so Hispanic/French/German
# and other names ("María-José García", "O'Brien", "François") are matched.
_ACCENT = (
    r"áàâäãåāăąǎæçćĉčďđéèêëēĕėęěğģìíîïĩīĭįıĵķĺļľłñńņňòóôöõōŏőø"
    r"ŕŗřśŝšşťŧùúûüũūŭůűųŵýÿŷźżž"
    r"ÁÀÂÄÃÅĀĂĄǍÆÇĆĈČĎĐÉÈÊËĒĔĖĘĚĞĢÌÍÎÏĨĪĬĮİĴĶĹĻĽŁÑŃŅŇÒÓÔÖÕŌŎŐØ"
    r"ŔŖŘŚŜŠŞŤŦÙÚÛÜŨŪŬŮŰŲŴÝŶŸŹŻŽ"
)
_UPPER = f"[A-Z{_ACCENT}]"
_LETTER = f"[A-Za-z{_ACCENT}]"

# A name token (title/upper-cased), optionally hyphen-joined, optionally
# containing OCR digits.  Structure mirrors the original three-alternative
# pattern with the character classes widened to include diacritics.
_TOKEN = (
    rf"(?:{_UPPER}(?:{_LETTER}{{0,20}}|['’]{_LETTER}{{1,20}})"
    rf"(?:-{_UPPER}(?:{_LETTER}{{0,20}}|['’]{_LETTER}{{1,20}}))?"
    rf"|[A-Z]{{2,20}}(?:-[A-Z]{{2,20}})?"
    rf"|{_UPPER}[A-Za-z0-9]{{1,20}})"
)

# A token that may be all-lowercase (title/leading-position matches).
_TOKEN_LOWER = (
    rf"(?:{_LETTER}(?:{_LETTER}{{0,20}}|['’]{_LETTER}{{1,20}})"
    rf"(?:-{_LETTER}(?:{_LETTER}{{0,20}}|['’]{_LETTER}{{1,20}}))?)"
)

_INITIAL = rf"{_UPPER}\."

# Role / form labels that introduce a person.
_LABEL = (
    r"Patient|Student|Parent(?:/Guardian)?|Guardian|Respondent|Complainant|"
    r"Spouse|Sibling|Father|Mother|Emergency\s+Contact|"
    r"(?:Full\s+)?Name|Client|Employee|Infant(?:\s+of)?|"
    r"Teacher|Counselor|Physician|Doctor|Nurse|Advisor|"
    r"Alias|AKA|A\.?K\.?A\.?|Legal\s+Name|Preferred\s+Name|"
    r"Child|Son|Daughter|Husband|Wife|Partner|Relative|"
    r"Witness|Accused|Victim|Reporting\s+Party|"
    r"Maiden\s+Name|Mother'?s?\s+Maiden\s+Name"
)

_PERSON_VERB = (
    r"met|called|said|reported|attended|was|is|has|had|declined|requested|"
    r"emailed|signed|lives|returned|submitted|enrolled|stated|denied|"
    r"acknowledged|arrived|left|visited|spoke|wrote|testified"
)

_NOT_SURNAME = (
    r"Thank|Thanks|Best|Warm|Sincerely|Regards|Dear|Hello|Hi|Hey|Cheers|"
    r"From|To|Cc|Bcc|Sent|Subject|Attention|Att|Cordially|Respectfully|"
    r"Yours|Truly|Fondly|Gratefully|Blessings|Take|See|Talk|Speak|Miss|Love|"
    r"Date|Name|Patient|Student|Parent|Address|Phone|Email|Please|Notify"
)


def _c(pat: str, flags: int = 0) -> re.Pattern:
    return re.compile(pat, re.MULTILINE | flags)


_HONORIFIC_RE = _c(
    rf"\b(?:{_HONORIFIC})\.?\s+"
    rf"(?:{_INITIAL}\s+)?(?:(?i:{_PARTICLES})\s+)*{_TOKEN}"
    rf"(?:\s+(?:(?i:{_PARTICLES})\s+)*{_TOKEN})?"
    rf"(?:\s+{_INITIAL})?"
    rf"\b"
)

_HONORIFIC_LOWER_RE = _c(
    rf"\b(?:{_HONORIFIC})\.?\s+"
    rf"(?:[A-Za-z]\.\s+)?(?:(?i:{_PARTICLES})\s+)*{_TOKEN_LOWER}"
    rf"(?:\s+(?:(?i:{_PARTICLES})\s+)*{_TOKEN_LOWER})?"
    rf"\b",
    re.IGNORECASE,
)

_LABELED_RE = _c(
    rf"\b(?i:{_LABEL})\s*[:\-–—]\s*"
    rf"['\"“”‘’]?"
    rf"(?:(?:{_HONORIFIC})\.?\s+)?"
    rf"(?:{_INITIAL}\s+)?(?:(?i:{_PARTICLES})\s+)*{_TOKEN}"
    rf"(?:\s+(?:(?i:{_PARTICLES})\s+)*{_TOKEN}){{0,3}}"
    rf"(?:\s+{_INITIAL})?"
    rf"['\"“”‘’]?"
)

# Last, First [M.]  including ALL-CAPS.
_LAST_FIRST_RE = _c(
    rf"\b(?!(?:{_NOT_SURNAME})\b){_TOKEN},\s*{_TOKEN}"
    rf"(?:\s+{_INITIAL})?\b"
)

# R. Patel / A. Montoya
_INITIAL_LAST_RE = _c(
    rf"\b{_INITIAL}\s+(?:(?i:{_PARTICLES})\s+)*{_TOKEN}\b"
)

# Title-case (or ALL-CAPS) First [Middle|Initial] [particles] Last
_FULL_RE = _c(
    rf"\b{_TOKEN}"
    rf"(?:\s+(?:{_INITIAL}|{_TOKEN}))?"
    rf"(?:\s+(?i:{_PARTICLES})){{0,3}}"
    rf"\s+{_TOKEN}\b"
)

# "Maria's father, Ernesto de la Cruz" — already covered by _FULL_RE if
# Ernesto de la Cruz is Title-case + particles.

# Ambiguous/unlabeled first name + person verb: "Jordan met with..."
# First token must be capitalized.
_CONTEXT_FIRST_RE = _c(
    rf"\b({_TOKEN})\s+(?i:{_PERSON_VERB})\b"
)

# Possessive first+last already in _FULL_RE; standalone "Maria's" is handled
# by ledger / unambiguous first names in detector.

_APPOSITIVE_RE = _c(
    rf"\b(?:student|patient|respondent|complainant|parent|teacher|counselor|"
    rf"physician|nurse|advisor|child|infant|employee|client)\s*,\s*"
    rf"({_TOKEN}(?:\s+(?:(?i:{_PARTICLES})\s+)*{_TOKEN}){{0,3}})\s*,",
    re.IGNORECASE,
)


def _ok_first(token: str) -> bool:
    t = token.strip(".,;:").replace("'s", "")
    if not t:
        return False
    return t.lower().strip(".") not in _FIRST_STOP


def _ok_last(token: str) -> bool:
    t = token.strip(".,;:")
    if not t:
        return False
    return t.lower().strip(".") not in _LAST_STOP


def _split_name(text: str) -> tuple[str, str]:
    """Return (first_token, last_token) of a matched name span."""
    cleaned = re.sub(rf"^(?:{_HONORIFIC})\.?\s+", "", text, flags=re.I)
    parts = cleaned.replace(",", " ").split()
    parts = [p for p in parts if p.lower() not in {
        "de", "da", "di", "do", "del", "della", "dei", "des", "du", "la", "le",
        "los", "las", "van", "von", "el", "al", "bin", "ibn", "ten", "ter",
        "den", "der", "dos", "das", "st", "st.",
    }]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], parts[-1]


def _keep_full(span: str) -> bool:
    first, last = _split_name(span)
    if not first or not last:
        return False
    if not _ok_first(first.rstrip(".")):
        return False
    if not _ok_last(last.rstrip(".")):
        return False
    # Reject "New York", "United States" style
    if first.lower() in {"new", "united", "north", "south", "east", "west"} and \
            last.lower() in {"york", "states", "carolina", "dakota", "jersey",
                             "mexico", "hampshire", "virginia", "island"}:
        return False
    return True


def detect_names(text: str) -> list[tuple[int, int, str, str]]:
    """Return (start, end, matched_text, evidence) tuples."""
    hits: list[tuple[int, int, str, str]] = []

    def add(m: re.Match, evidence: str, group: int | None = None) -> None:
        if group is None:
            s, e, val = m.start(), m.end(), m.group()
        else:
            s, e, val = m.start(group), m.end(group), m.group(group)
        val = val.strip(" \t,;:")
        # Trim trailing punctuation that regex word-boundary left off already.
        if not val:
            return
        # Recompute end if we stripped.
        e = s + len(m.group() if group is None else m.group(group))
        # If we stripped trailing from val, shrink end.
        raw = m.group() if group is None else m.group(group)
        if raw != val and raw.startswith(val):
            e = s + len(val)
        hits.append((s, e, val, evidence))

    for m in _HONORIFIC_RE.finditer(text):
        add(m, "honorific")
    for m in _HONORIFIC_LOWER_RE.finditer(text):
        # Skip if already captured as case-sensitive honorific.
        add(m, "honorific_ci")
    _ROLE_NAME_RE = _c(
        rf"\b(?i:student|patient|respondent|complainant|parent|guardian|"
        rf"teacher|counselor|physician|nurse|advisor|employee|client|"
        rf"legal\s+name|preferred\s+name|infant\s+of|child\s+of)\s+"
        rf"(?:(?:{_HONORIFIC})\.?\s+)?"
        rf"(?:{_INITIAL}\s+)?(?:(?i:{_PARTICLES})\s+)*{_TOKEN}"
        rf"(?:\s+(?:(?i:{_PARTICLES})\s+)*{_TOKEN}){{0,3}}"
        rf"(?:\s+{_INITIAL})?"
        rf"\b"
    )

    for m in _LABELED_RE.finditer(text):
        # Drop the label; keep the name portion after the separator.
        full = m.group()
        split = re.split(r"[:\-–—]", full, maxsplit=1)
        if len(split) == 2:
            name = split[1].strip(" \t'\"“”‘’")
            idx = m.group().find(split[1])
            # Locate the stripped name inside the original match.
            raw_tail = split[1]
            inner = raw_tail.find(name)
            if idx >= 0 and name:
                s = m.start() + idx + max(inner, 0)
                if _keep_full(name) or _ok_first(_split_name(name)[0]):
                    hits.append((s, s + len(name), name, "labeled"))
        else:
            add(m, "labeled")
    for m in _ROLE_NAME_RE.finditer(text):
        full = m.group()
        # Strip the leading role word(s).
        name = re.sub(
            r"^(?:student|patient|respondent|complainant|parent|guardian|"
            r"teacher|counselor|physician|nurse|advisor|employee|client|"
            r"legal\s+name|preferred\s+name|infant\s+of|child\s+of)\s+",
            "", full, flags=re.I).strip()
        if name and (_keep_full(name) or _ok_first(_split_name(name)[0])):
            s = m.start() + (len(full) - len(name)) if full.endswith(name) else m.start()
            # Prefer locating name inside the match.
            loc = full.lower().rfind(name.lower())
            if loc >= 0:
                s = m.start() + loc
                name = full[loc:]
            if _keep_full(name) or len(name.split()) >= 2:
                hits.append((s, s + len(name), name.strip(" ,;"), "role"))
    for m in _LAST_FIRST_RE.finditer(text):
        if _keep_full(m.group().replace(",", " ")):
            add(m, "last_first")
    for m in _INITIAL_LAST_RE.finditer(text):
        last = m.group().split()[-1]
        if _ok_last(last):
            add(m, "initial_last")
    for m in _FULL_RE.finditer(text):
        if _keep_full(m.group()):
            add(m, "titlecase")
    for m in _APPOSITIVE_RE.finditer(text):
        add(m, "appositive", group=1)
    for m in _CONTEXT_FIRST_RE.finditer(text):
        token = m.group(1)
        if _ok_first(token) and token.lower() not in _LAST_STOP:
            hits.append((m.start(1), m.end(1), token, "context_first"))

    return hits
