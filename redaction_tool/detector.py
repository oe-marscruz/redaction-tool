"""PII/PHI detection engine.

Covers the 18 HIPAA identifiers plus FERPA-protected information using
regex patterns.  Each category can be toggled independently via presets.

Patterns are **case-sensitive by default** (proper nouns must be capitalized),
with ``(?i:...)`` groups where case-insensitivity is genuinely wanted
(keywords like "MRN", month names, honorifics).  This avoids classic false
positives such as email closings ("Thank You,\\nJennifer") matching
"Last, First" name patterns.

Name detection combines:
  1. Honorific patterns ("Dr. Jane Smith")
  2. A built-in list of common first names ("Brianna Ynostroza",
     "Ynostroza, Brianna", "Brianna M. Ynostroza")
  3. User-supplied literal texts (most reliable — pass known subject
     names via ``custom_texts``)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import dates as _dates
from . import ledger as _ledger
from . import names as _names
from . import normalize as _normalize
from .taxonomy import CONFIRMED, LIKELY, POSSIBLE, entity_type_for

# ---------------------------------------------------------------------------
# Match result
# ---------------------------------------------------------------------------

@dataclass
class Match:
    """A single detection result.

    ``text`` is always a slice of the original input (required for PDF
    ``search_for``).  ``entity_type`` is the FERPA/HIPAA taxonomy key;
    ``confidence`` is confirmed/likely/possible — lower-confidence hits
    are still returned, never silently dropped.
    """
    text: str
    category: str
    start: int
    end: int
    entity_type: str = ""
    confidence: str = CONFIRMED
    evidence: str = ""


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

@dataclass
class Category:
    key: str
    label: str
    patterns: list[re.Pattern] = field(default_factory=list)
    # Optional validator: called with the full match text; return True to keep.
    validator: Callable[[str], bool] | None = None


def _c(pat: str) -> re.Pattern:
    """Compile a case-SENSITIVE pattern (multiline)."""
    return re.compile(pat, re.MULTILINE)


def _has_digit(text: str) -> bool:
    """Validator: keep only matches containing at least one digit."""
    return any(ch.isdigit() for ch in text)


# ── Common first names (broad coverage across demographics) ───────────────

_COMMON_FIRST_NAMES: frozenset[str] = frozenset({
    # Male names
    "aaron","abdul","abraham","adam","adrian","alan","albert","alejandro",
    "alex","alexander","alfonso","alfred","allen","alonso","alvin","andre",
    "andres","andrew","angel","anthony","antonio","armando","arnold","arthur",
    "austin","barry","benjamin","bernard","bill","billy","blake","bob",
    "bobby","brad","bradley","brandon","brendan","brent","brian","bruce",
    "bryan","bryant","byron","caleb","calvin","camilo","carl","carlos",
    "casey","cesar","chad","charles","charlie","chris","christian",
    "christopher","clarence","clark","clayton","clifford","clinton","cody",
    "colin","conrad","corey","craig","curtis","dale","damian","dan","daniel",
    "danny","dario","darius","darrell","darren","david","dean","dennis",
    "derek","derrick","devin","diego","dominic","don","donald","douglas",
    "duane","dustin","dylan","earl","eddie","edgar","edmund","eduardo",
    "edward","edwin","eli","elias","elijah","elliott","emanuel","emiliano",
    "emmanuel","enrique","eric","erik","ernest","esteban","ethan","eugene",
    "evan","felix","fernando","floyd","francis","francisco","frank",
    "franklin","fred","frederick","gabriel","garrett","gary","gene",
    "geoffrey","george","gerald","gilbert","glen","glenn","gordon","grant",
    "greg","gregory","guillermo","gustavo","harold","harry","harvey",
    "hector","henry","herbert","herman","howard","hugh","ian","ignacio",
    "iker","isaac","isaiah","ivan","jack","jacob","jaime","james","jared",
    "jarvis","jason","javier","jay","jeff","jeffrey","jeremiah","jeremy",
    "jerome","jesse","jesus","jim","jimmy","joaquin","joel","john","johnny",
    "jon","jonathan","jordan","jorge","jose","joseph","joshua","josue",
    "juan","julian","julio","justin","karl","keith","kelvin","ken",
    "kenneth","kevin","kirk","kurt","kyle","lamar","lance","larry",
    "lawrence","lee","leo","leon","leonard","leonardo","leroy","lester",
    "levi","lewis","lloyd","logan","lonnie","louis","lucas","luis","luke",
    "manuel","marc","marcus","mario","mark","marshall","martin","marvin",
    "mateo","matthew","maurice","max","melvin","michael","micheal","miguel",
    "mike","mitchell","mohamed","mohammad","mohammed","morris","moses",
    "nathan","nathaniel","neil","nelson","nicholas","nick","nicolas","noah",
    "noel","norman","omar","oscar","owen","pablo","patrick","paul","pedro",
    "perry","pete","peter","philip","phillip","preston","ralph","ramon",
    "randall","randy","raul","ray","raymond","reginald","rene","ricardo",
    "richard","rick","ricky","robert","roberto","rodrigo","rodney","roger",
    "roland","ron","ronald","roy","ruben","russell","ryan","salvador","sam",
    "samuel","santiago","scott","sean","sebastian","sergio","seth","shane",
    "shawn","sidney","simon","spencer","stanley","stephen","steve","steven",
    "stewart","stuart","terrence","theodore","thomas","tim","timothy",
    "tobias","todd","tom","tommy","tony","travis","trevor","troy","tyler",
    "tyrone","victor","vincent","virgil","wade","wallace","walter","warren",
    "wayne","wesley","william","willie","zachary",
    # Female names
    "abigail","abril","adriana","adrienne","aisha","alana","alejandra",
    "alexa","alexandra","alexis","alice","alicia","alina","alison",
    "allison","alondra","alyson","alyssa","amanda","amaya","amber","amelia",
    "amy","ana","anahi","ananya","andrea","angela","angelica","angelina",
    "anita","ann","anna","annette","annie","antonia","april","ariana",
    "arianna","ariel","arlene","ashlee","ashleigh","ashley","audrey",
    "aurora","autumn","ava","ayesha","barbara","beatrice","beatriz","becky",
    "belen","belinda","bertha","beth","bethany","betty","beverly","bianca",
    "bonnie","brandi","brandy","brenda","briana","brianna","bridget",
    "brittany","brooke","caitlin","camila","camille","candace","candice",
    "carla","carmen","carol","carole","carolina","caroline","carolyn",
    "carrie","cassandra","cassie","catalina","catherine","cathy","cecilia",
    "celeste","celia","chantel","charlene","charlotte","chelsea","cheryl",
    "chloe","christa","christina","christine","christy","cindy","citlali",
    "claire","clara","claudia","colleen","connie","constance","cora",
    "courtney","cristina","crystal","cynthia","dahlia","daisy","dana",
    "daniela","danielle","daphne","darlene","dawn","dayana","deanna",
    "deborah","debra","denise","denisse","diana","diane","dianna","dolores",
    "dominique","donna","dora","doris","dorothy","edith","edna","eileen",
    "elaine","eleanor","elena","eliana","elisa","elizabeth","ella","ellen",
    "eloise","elsa","emily","emma","erica","erika","erin","esmeralda",
    "estefania","esther","estrella","eva","evelyn","faith","fatima",
    "felicia","fernanda","fiona","florence","frances","francisca",
    "gabriela","gabriella","gabrielle","gail","genesis","geneva",
    "genevieve","georgia","geraldine","gina","giselle","gladys","glenda",
    "gloria","grace","graciela","greta","guadalupe","gwen","hannah",
    "harriet","hazel","heather","heidi","helen","henrietta","hilda","holly",
    "hope","ida","iliana","ingrid","irene","iris","irma","isabel","isabela",
    "isabella","isabelle","itzel","jacqueline","jada","jade","jamie","jane",
    "janet","janice","jaqueline","jasmin","jasmine","jazmin","jean",
    "jeanette","jeanne","jenna","jennifer","jessica","jill","jillian",
    "jimena","jo","joan","joanna","joanne","jocelyn","jodi","jodie",
    "johanna","jordan","josephine","joy","joyce","juanita","judith","judy",
    "julia","juliana","julie","june","justina","karen","karina","karla",
    "kassandra","kate","katherine","kathleen","kathryn","kathy","katie",
    "katrina","kay","kayla","keisha","kelly","kendra","kenia","kerry","kim",
    "kimberly","kira","kristen","kristin","kristina","krystal","lana",
    "lara","laura","lauren","laurie","leah","leilani","lena","leona",
    "leslie","lesly","leticia","liliana","lillian","lillie","lily","linda",
    "lindsay","lindsey","lisa","lizbeth","lizeth","lois","lorena","loretta",
    "lori","lorraine","louise","lucia","lucille","lucy","lupe","luz",
    "lydia","lynn","mabel","mackenzie","madeline","madison","mae","maggie",
    "marcella","marcia","margaret","margarita","margie","maria","mariana",
    "marianne","maribel","marie","mariela","marilyn","marina","marion",
    "marisol","marjorie","marlene","marsha","martha","martina","mary",
    "maryann","maureen","maxine","maya","megan","melanie","melany",
    "melinda","melissa","mercedes","meredith","mia","michele","michelle",
    "mildred","mindy","miriam","misty","molly","monica","monique",
    "monserrat","morgan","muriel","myra","myrtle","nadia","nancy","naomi",
    "natalia","natalie","natasha","nayeli","nelida","nichole","nicole",
    "nina","noelle","nora","norma","olga","olive","olivia","paige","paloma",
    "pam","pamela","patricia","patsy","paula","paulina","pauline","pearl",
    "peggy","penelope","penny","perla","phyllis","priscilla","rachel",
    "raquel","rebecca","rebeca","regina","renee","rhonda","rita","roberta",
    "robin","rocio","rosa","rosalie","rose","rosemary","roxanne","rubi",
    "ruby","ruth","sabrina","sadie","sally","samantha","sandra","sara",
    "sarah","sarahi","selena","serena","shannon","shari","sharon","sheila",
    "shelby","shelley","sherry","shirley","sierra","silvia","simone",
    "sofia","sonia","sonja","sophia","sophie","stacey","stacy","stella",
    "stephanie","sue","susan","susana","susanne","suzanne","sylvia",
    "tabitha","tamara","tami","tammy","tanya","tara","tasha","teresa",
    "terri","thea","theresa","tiffany","tina","tonia","tracey","tracy",
    "tricia","valentina","valeria","valerie","vanessa","vera","veronica",
    "vicki","victoria","virginia","vivian","wanda","wendy","whitney",
    "wilma","winifred","ximena","yamileth","yareli","yesenia","yolanda",
    "yulissa","yvette","yvonne","zoe","zoey",
    # Neutral / modern names
    "avery","bailey","cameron","devon","drew","emerson","emery","finley",
    "harper","hayden","hunter","jaden","jameson","kai","kendall","kennedy",
    "marley","mason","mckenzie","micah","milan","miles","nash","parker",
    "peyton","phoenix","quinn","reagan","reese","riley","rowan","sage",
    "sawyer","skyler","taylor","toby","wren",
})

# Names alternation with capitalized and uppercase variants so the
# case-sensitive patterns still catch "BRIANNA" / "brianna" forms.
def _name_variants() -> str:
    variants: set[str] = set()
    for n in _COMMON_FIRST_NAMES:
        variants.add(n)
        variants.add(n.capitalize())
        variants.add(n.upper())
    return "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))

_NAMES_CI = _name_variants()  # used inside (?i:...) — lowercase forms suffice

# Names that are also common English words — excluded from *single-word*
# name matching to avoid redacting months, verbs and nouns.
_AMBIGUOUS_NAMES: frozenset[str] = frozenset({
    "april","may","june","aurora","autumn","dawn","summer","amber",
    "crystal","ruby","jasmine","rose","lily","iris","hazel","olive",
    "pearl","grace","hope","faith","joy","sage","robin","wren",
    "brooke","glen","dale","lee","ray","drew","brad","chad","sue",
    "penny","carol","holly","grant","wade","lance","dean","miles",
    "gene","jean","frank","bob","bill","mark","guy","art","al",
    "ed","ted","rob","rod","hunter","chase","parker","sawyer",
    "mason","blake","jordan","morgan","austin","madison","troy",
})

# Unambiguous first names, matched standalone when capitalized or ALL CAPS
# (e.g. a lone "Brianna" in a paragraph, or a "First Name" spreadsheet cell).
def _single_name_variants() -> str:
    variants: set[str] = set()
    for n in _COMMON_FIRST_NAMES - _AMBIGUOUS_NAMES:
        variants.add(n.capitalize())
        variants.add(n.upper())
    return "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))

_NAMES_SINGLE = _single_name_variants()

# Words that legitimately precede ", <FirstName>" in email closings and
# headers — excluded from the "Last, First" pattern.
_NOT_A_SURNAME = (
    r"Thank|Thanks|Best|Warm|Sincerely|Regards|Dear|Hello|Hi|Hey|Cheers|"
    r"From|To|Cc|Bcc|Sent|Subject|Attention|Att|Cordially|Respectfully|"
    r"Yours|Truly|Fondly|Gratefully|Blessings|Take|See|Talk|Speak|Miss|Love"
)

_NAME_PATTERNS: list[re.Pattern] = [
    # Honorific + First Last  ("Dr. Jane Smith", "Mr Smith")
    _c(r"\b(?i:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]{1,20}"
       r"(?:\s+[A-Z][a-z]{1,20})?\b"),
    # First [M.] Last  (surname must be properly capitalized)
    _c(rf"\b(?i:{_NAMES_CI})\s+(?:[A-Z]\.\s+)?[A-Z][a-z]{{1,20}}\b"),
    # Last, First [M.]  (e.g. "Ynostroza, Brianna", "Harding,Ryan J")
    # — excludes email closings
    _c(rf"\b(?!(?:{_NOT_A_SURNAME})\b)[A-Z][a-z]{{1,20}},\s*"
       rf"(?i:{_NAMES_CI})(?:\s+[A-Z]\.?)?\b"),
    # Standalone unambiguous first names (capitalized / ALL CAPS only)
    _c(rf"\b(?:{_NAMES_SINGLE})\b"),
]

_US_STATES = (
    r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    r"MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|"
    r"Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|"
    r"Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|"
    r"Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|"
    r"Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|"
    r"New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    r"Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|"
    r"Virginia|Washington|West Virginia|Wisconsin|Wyoming"
)

_MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)


# ---------------------------------------------------------------------------
# All categories
# ---------------------------------------------------------------------------

CATEGORIES: list[Category] = [
    # HIPAA #1 — Names
    Category(key="names", label="Names (person names)", patterns=_NAME_PATTERNS),

    # HIPAA #2 — Geographic subdivisions smaller than State
    Category(
        key="addresses",
        label="Addresses / Cities / ZIP Codes",
        patterns=[
            # US street address
            _c(
                r"\b\d{1,6}\s+[A-Za-z0-9.'\-]+(?:\s+[A-Za-z0-9.'\-]+){0,4}\s+"
                r"(?i:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|"
                r"Circle|Cir|Boulevard|Blvd|Way|Place|Pl|Terrace|Ter|Highway|"
                r"Hwy|Parkway|Pkwy|Trail|Trl)\b\.?"
                r"(?:\s*(?:#|(?i:Apt|Apartment|Suite|Ste|Unit))\s*\.?\s*\w+)?"
            ),
            # PO Box
            _c(r"\b(?i:P\.?\s*O\.?\s*Box)\s+\d+\b"),
            # ZIP / ZIP+4
            _c(r"\b\d{5}(?:-\d{4})?\b"),
            # City, State
            _c(rf"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+){{0,2}},\s*(?:{_US_STATES})\b"),
            # Apt / Suite / Unit with a number (not bare "Room 101" — too noisy)
            _c(r"\b(?i:Apt|Apartment|Suite|Ste|Unit)\.?\s*#?\s*"
               r"[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\b"),
            # Place of birth (FERPA indirect identifier)
            _c(r"\b(?i:Place\s+of\s+Birth|Birth\s+Place|Born\s+in)\s*[:\-–—]?\s*"
               r"[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3}\b"),
        ],
    ),

    # HIPAA #3 — Dates (except year) & ages over 89
    Category(
        key="dates",
        label="Dates (birth, admission, death, etc.) / Ages 90+",
        patterns=[
            # MM/DD/YYYY  MM-DD-YYYY  MM.DD.YYYY
            _c(r"\b(?:0?[1-9]|1[0-2])[/\-.](?:0?[1-9]|[12]\d|3[01])[/\-.](?:19|20)\d{2}\b"),
            # Month DD, YYYY
            _c(rf"\b(?i:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+(?:19|20)\d{{2}}\b"),
            # DD Month YYYY  ("6 May 2025")
            _c(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?i:{_MONTHS})\.?,?\s+(?:19|20)\d{{2}}\b"),
            # ISO YYYY-MM-DD
            _c(r"\b(?:19|20)\d{2}[/\-.](?:0?[1-9]|1[0-2])[/\-.](?:0?[1-9]|[12]\d|3[01])\b"),
            # Explicit DOB labels
            _c(rf"\b(?i:DOB|D\.O\.B|Date\s+of\s+Birth|Birth\s*date|Born)[:\s]*"
               rf"(?i:{_MONTHS})?\.?\s*\d{{1,2}}[,/\-. ]+(?:19|20)?\d{{2}}\b"),
            # Ages over 89
            _c(r"\b(?i:age|aged)[:\s]*(?:9\d|1\d{2})\b"),
            _c(r"\b(?:9\d|1\d{2})\s*(?i:years?\s+old|y/?o)\b\.?"),
        ],
    ),

    # HIPAA #4 — Phone numbers
    Category(
        key="phones",
        label="Phone Numbers",
        patterns=[
            _c(r"\b(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b"),
            _c(r"\(\d{3}\)\s?\d{3}-\d{4}"),
            # OCR: O/0 confusion in a phone-shaped token.
            _c(r"\(?[0-9O]{3}\)?[\s.\-][0-9O]{3}[\s.\-][0-9O]{4}"),
        ],
    ),

    # HIPAA #5 — Fax numbers (contextual)
    Category(
        key="fax",
        label="Fax Numbers",
        patterns=[
            _c(r"\b(?i:Fax|Facsimile)(?:\s*(?i:No|Number|#))?[:\s]*"
               r"(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b"),
        ],
    ),

    # HIPAA #6 — Email addresses
    Category(
        key="emails",
        label="Email Addresses",
        patterns=[
            _c(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        ],
    ),

    # HIPAA #7 — Social Security Numbers
    Category(
        key="ssn",
        label="Social Security Numbers",
        patterns=[
            _c(r"\b\d{3}-\d{2}-\d{4}\b"),
            _c(r"\b\d{3}\s\d{2}\s\d{4}\b"),
            _c(r"\b(?i:SSN)[:\s#]*\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
            # OCR: last digit confused with O/o
            _c(r"\b\d{3}-\d{2}-\d{3}[Oo]\b"),
        ],
    ),

    # HIPAA #8 — Medical Record Numbers
    Category(
        key="mrn",
        label="Medical Record Numbers",
        patterns=[
            _c(r"\b(?i:MRN|M\.?R\.?\s?#|Medical\s+Record(?:\s*(?:No|Number|#))?)"
               r"[\s:]*[A-Za-z0-9\-]*\d[A-Za-z0-9\-]{3,}\b"),
        ],
        validator=_has_digit,
    ),

    # HIPAA #9 — Health Plan Beneficiary Numbers
    Category(
        key="health_plan",
        label="Health Plan / Beneficiary Numbers",
        patterns=[
            _c(r"\b(?i:Health\s+Plan|Beneficiary|Member|Subscriber|Policy|Group|"
               r"Insurance)\s*(?i:ID|No|Number|#)[:\s]*"
               r"[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\b"),
        ],
        validator=_has_digit,
    ),

    # HIPAA #10 — Account Numbers
    Category(
        key="accounts",
        label="Account Numbers",
        patterns=[
            _c(r"\b(?i:Account|Acct|Bank\s+Account|Routing)\s*(?i:No|Number|#)?"
               r"[:\s]*[A-Za-z0-9\-]*\d[A-Za-z0-9\-]{3,}\b"),
        ],
        validator=_has_digit,
    ),

    # HIPAA #11 — Certificate / License Numbers
    Category(
        key="licenses",
        label="Certificate / License Numbers",
        patterns=[
            _c(r"\b(?i:License|Lic|Cert(?:ificate)?|DL|DLN|Driver'?s?\s*Lic(?:ense)?)"
               r"\s*(?i:No|Number|#)?[:.\s]*[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\b"),
        ],
        validator=_has_digit,
    ),

    # HIPAA #12 — Vehicle Identifiers
    Category(
        key="vehicles",
        label="Vehicle Identifiers / License Plates / VINs",
        patterns=[
            _c(r"\b(?i:License\s+Plate|Plate|VIN|Vehicle\s+ID)\s*(?i:No|Number|#)?"
               r"[:\s]*[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\b"),
            # ISO 3779 VIN (17 chars, no I/O/Q).
            _c(r"\b[A-HJ-NPR-Z0-9]{17}\b"),
        ],
        validator=_has_digit,
    ),

    # HIPAA #13 — Device Identifiers
    Category(
        key="devices",
        label="Device / Serial Numbers / MAC Addresses",
        patterns=[
            _c(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"),
            _c(r"\b(?i:Serial|S/N|Device\s+ID)\s*(?i:No|Number|#)?[:\s]*"
               r"[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\b"),
        ],
        validator=_has_digit,
    ),

    # HIPAA #14 — URLs
    Category(
        key="urls",
        label="Web URLs",
        patterns=[
            _c(r"\b(?i:https?)://[^\s<>\"')\]]+"),
            _c(r"\b(?i:www)\.[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+[^\s<>\"')\]]*"),
        ],
    ),

    # HIPAA #15 — IP Addresses
    Category(
        key="ips",
        label="IP Addresses",
        patterns=[
            _c(r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
               r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"),
            # IPv6 (uncompressed).
            _c(r"\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b"),
        ],
    ),

    # HIPAA #16 — Biometric identifiers (text references)
    Category(
        key="biometric",
        label="Biometric Identifier References",
        patterns=[
            _c(r"\b(?i:Fingerprint|Retina\s+Scan|Voice\s*print|DNA\s+(?:Profile|Sample))"
               r"\s*(?i:No|Number|#|ID)?[:\s]*[A-Za-z0-9\-]*\b"),
        ],
    ),

    # HIPAA #17 — Full-face photos: NOT text-detectable.  See README —
    # PDF image redaction must be reviewed manually.

    # HIPAA #18 — Any other unique identifying number
    Category(
        key="unique_ids",
        label="Unique IDs (Student / Employee / Case / File Numbers)",
        patterns=[
            _c(r"\b(?i:Student|Employee|Faculty|Staff|Case|File|Reference|Personnel|"
               r"Applicant|Patient|Client)\s*(?i:ID|Number|No|#)[:\s]*"
               r"[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\b"),
            _c(r"\b(?i:SID|EID|UID|EMPLID|Banner\s*ID)\s*[:\-#]?\s*"
               r"[A-Za-z0-9\-]*\d[A-Za-z0-9\-]*\b"),
            # Bare 7–10 digit identifiers (case numbers, campus IDs, undashed SSNs)
            _c(r"\b\d{7,10}\b"),
        ],
        validator=_has_digit,
    ),

    # ── FERPA extras ──
    Category(
        key="student_records",
        label="Student Records (GPA / grades / course references)",
        patterns=[
            _c(r"\b(?i:GPA|Grade\s+Point\s+Average|Cumulative\s+GPA)[:\s]*\d\.\d{1,3}\b"),
            _c(r"\b(?i:Final\s+Grade|Course\s+Grade|Grade)[:\s]*[ABCDF][+\-]?\b"),
        ],
    ),

    Category(
        key="financial",
        label="Financial Info (tuition, aid, salaries — FERPA/GLBA)",
        patterns=[
            _c(r"\b(?i:Tuition|Fees|Balance|Payment|Financial\s+Aid|Loan|Grant|"
               r"Scholarship|Salary|Wages?|Stipend|Award)[:\s]*\$[\d,]+(?:\.\d{2})?\b"),
        ],
    ),
]

CATEGORY_MAP: dict[str, Category] = {c.key: c for c in CATEGORIES}

# ── built-in presets ───────────────────────────────────────────────────────

PRESETS: dict[str, list[str]] = {
    "FERPA Only": [
        "names", "addresses", "dates", "phones", "emails", "ssn",
        "unique_ids", "student_records", "financial",
    ],
    "HIPAA Only": [
        "names", "addresses", "dates", "phones", "fax", "emails",
        "ssn", "mrn", "health_plan", "accounts", "licenses",
        "vehicles", "devices", "urls", "ips", "biometric", "unique_ids",
    ],
    "Full (FERPA + HIPAA)": [c.key for c in CATEGORIES],
    "Maximum / Strict": [c.key for c in CATEGORIES],
}

# ── detection ──────────────────────────────────────────────────────────────

_NAME_EVIDENCE_CONF = {
    "honorific": CONFIRMED,
    "honorific_ci": LIKELY,
    "labeled": CONFIRMED,
    "role": CONFIRMED,
    "last_first": CONFIRMED,
    "initial_last": LIKELY,
    "titlecase": LIKELY,
    "appositive": CONFIRMED,
    "context_first": POSSIBLE,
    "dictionary": LIKELY,
    "ledger": LIKELY,
}

_DATE_EVIDENCE_CONF = {
    "written_the_of": CONFIRMED,
    "written_month_day": LIKELY,
    "d_mon_yy": CONFIRMED,
    "month_day_year": CONFIRMED,
    "day_month_year": CONFIRMED,
    "iso": CONFIRMED,
    "numeric": CONFIRMED,
    "md_padded": LIKELY,
    "relative": POSSIBLE,
    "age_over_89": CONFIRMED,
}


def _mk(text: str, category: str, start: int, end: int,
        evidence: str = "", confidence: str = CONFIRMED,
        entity_type: str = "") -> Match:
    return Match(
        text=text[start:end] if 0 <= start <= end <= len(text) else text[start:end],
        category=category,
        start=start,
        end=end,
        entity_type=entity_type or entity_type_for(category),
        confidence=confidence,
        evidence=evidence,
    )


def _dedupe(matches: list[Match]) -> list[Match]:
    matches.sort(key=lambda x: (x.start, -(x.end - x.start)))
    deduped: list[Match] = []
    for m in matches:
        if deduped and m.start < deduped[-1].end:
            if (m.end - m.start) > (deduped[-1].end - deduped[-1].start):
                deduped[-1] = m
            continue
        deduped.append(m)
    deduped.sort(key=lambda x: x.start)
    return deduped


def _map_norm_span(index: list[int], start: int, end: int, orig_len: int) -> tuple[int, int]:
    return _normalize.map_span(index, start, end, orig_len)


def detect(text: str,
           enabled_categories: list[str] | None = None,
           custom_patterns: list[str] | None = None,
           custom_texts: list[str] | None = None) -> list[Match]:
    """Scan *text* and return all PII/PHI matches, sorted and de-duplicated.

    Pipeline:
      PASS 0  NFKC / hyphen-join / whitespace normalize (offset-mapped)
      PASS 1  deterministic structured-pattern detection
      PASS 2  high-recall name + date detectors
      PASS 3  document-level entity ledger (propagate known names)
      PASS 4  custom literals / regex
      PASS 5  overlap union (longest span wins)

    ``custom_texts`` are matched as whole words (case-insensitive) so that
    e.g. adding "Ann" does not redact inside "Anna".
    Lower-confidence hits are returned, never dropped.
    """
    if enabled_categories is None:
        enabled_categories = list(CATEGORY_MAP)
    enabled = set(enabled_categories)
    matches: list[Match] = []
    orig = text
    orig_len = len(orig)

    # PASS 0 — normalized view for wrap/OCR-tolerant detectors.
    norm, index = _normalize.build_normalized(orig)

    def add_orig(start: int, end: int, category: str, evidence: str,
                 confidence: str = CONFIRMED) -> None:
        if start < 0 or end > orig_len or start >= end:
            return
        matches.append(_mk(orig, category, start, end, evidence, confidence))

    def add_norm(ns: int, ne: int, category: str, evidence: str,
                 confidence: str = CONFIRMED) -> None:
        s, e = _map_norm_span(index, ns, ne, orig_len)
        add_orig(s, e, category, evidence, confidence)

    # PASS 1 — structured regex on original text (precise offsets).
    skip_regex = set()
    if "names" in enabled:
        skip_regex.add("names")  # replaced by PASS 2
    if "dates" in enabled:
        skip_regex.add("dates")  # replaced by PASS 2
    for cat_key in enabled_categories:
        if cat_key in skip_regex:
            continue
        cat = CATEGORY_MAP.get(cat_key)
        if cat is None:
            continue
        for pat in cat.patterns:
            for m in pat.finditer(orig):
                matched = m.group()
                if cat.validator and not cat.validator(matched):
                    continue
                add_orig(m.start(), m.end(), cat_key, "regex", CONFIRMED)

    # Also run structured regex on the normalized view so hyphen-wrapped
    # emails / IDs still hit, then map back.
    for cat_key in enabled_categories:
        if cat_key in skip_regex:
            continue
        cat = CATEGORY_MAP.get(cat_key)
        if cat is None:
            continue
        for pat in cat.patterns:
            for m in pat.finditer(norm):
                matched = m.group()
                if cat.validator and not cat.validator(matched):
                    continue
                add_norm(m.start(), m.end(), cat_key, "regex_norm", CONFIRMED)

    # PASS 2 — names
    if "names" in enabled:
        # Keep the dictionary patterns as a high-precision supplement.
        cat = CATEGORY_MAP.get("names")
        if cat is not None:
            for pat in cat.patterns:
                for m in pat.finditer(orig):
                    add_orig(m.start(), m.end(), "names", "dictionary", LIKELY)
        for s, e, _val, evidence in _names.detect_names(orig):
            conf = _NAME_EVIDENCE_CONF.get(evidence, LIKELY)
            add_orig(s, e, "names", evidence, conf)
        for s, e, _val, evidence in _names.detect_names(norm):
            conf = _NAME_EVIDENCE_CONF.get(evidence, LIKELY)
            add_norm(s, e, "names", evidence + "+norm", conf)

    # PASS 2 — dates
    if "dates" in enabled:
        for s, e, _val, evidence in _dates.detect_dates(orig):
            conf = _DATE_EVIDENCE_CONF.get(evidence, LIKELY)
            add_orig(s, e, "dates", evidence, conf)
        for s, e, _val, evidence in _dates.detect_dates(norm):
            conf = _DATE_EVIDENCE_CONF.get(evidence, LIKELY)
            add_norm(s, e, "dates", evidence + "+norm", conf)

    # PASS 3 — document-level entity ledger for names.
    if "names" in enabled:
        book = _ledger.EntityLedger()
        for m in matches:
            if m.category == "names" and (m.end - m.start) >= 3:
                book.ingest(m.text)
        for s, e, _val in book.extra_spans(orig):
            add_orig(s, e, "names", "ledger", LIKELY)
        for s, e, _val in book.extra_spans(norm):
            add_norm(s, e, "names", "ledger+norm", LIKELY)

    # PASS 4 — custom patterns / literals (always on; highest priority).
    for pattern_str in (custom_patterns or []):
        if not pattern_str.strip():
            continue
        try:
            pat = re.compile(pattern_str, re.IGNORECASE)
        except re.error:
            continue
        for m in pat.finditer(orig):
            if m.group():
                add_orig(m.start(), m.end(), "custom", "custom_regex", CONFIRMED)

    for literal in (custom_texts or []):
        literal = literal.strip()
        if not literal:
            continue
        pat = re.compile(rf"\b{re.escape(literal)}\b", re.IGNORECASE)
        for m in pat.finditer(orig):
            add_orig(m.start(), m.end(), "custom", "custom_literal", CONFIRMED)

    return _dedupe(matches)


def detect_summary(text: str,
                   enabled_categories: list[str] | None = None,
                   custom_patterns: list[str] | None = None,
                   custom_texts: list[str] | None = None) -> dict[str, int]:
    """Return a count of detected items per category."""
    summary: dict[str, int] = {}
    for m in detect(text, enabled_categories, custom_patterns, custom_texts):
        summary[m.category] = summary.get(m.category, 0) + 1
    return summary
