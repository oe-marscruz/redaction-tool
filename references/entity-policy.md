# Entity Policy

The canonical FERPA/HIPAA-oriented entity taxonomy lives in
`redaction_tool/taxonomy.py` (`CATEGORY_TO_ENTITY`, `HIPAA_COVERAGE`,
`FERPA_COVERAGE`, `PROFILES`).  Detection classification is separated from
redaction policy: the detector returns `Match` objects carrying a
`category`, a finer `entity_type`, and a `confidence` band
(`confirmed` / `likely` / `possible`).  Lower-confidence hits are always
returned for review — never silently dropped.

## Detection pipeline (multi-pass)

`detector.detect()` runs:

1. **Normalization** — NFKC, hyphen-join, whitespace collapse, with original
   offset mapping (`redaction_tool/normalize.py`).
2. **Deterministic structured patterns** — SSN, phone/fax, email, MRN,
   account/license/vehicle/device, URL, IP (IPv4 + IPv6), ZIP, IDs
   (`redaction_tool/detector.py` `CATEGORIES`).
3. **Name detection** — honorifics, labeled roles, "Last, First", initials,
   compound surnames, appositives, unlabeled narrative names, accented and
   OCR-corrupted tokens (`redaction_tool/names.py`).
4. **Date/age detection** — numeric (incl. 2-digit years), month-name,
   written ordinals, relative temporal expressions, ages over 89
   (`redaction_tool/dates.py`).
5. **Document-level entity ledger** — propagates name variants ("Ms.
   Montoya", "A. Montoya", "Montoya") once a name is seen
   (`redaction_tool/ledger.py`).
6. **Custom literals / regex** — user-supplied exact-match and patterns.

## Policy profiles

`taxonomy.PROFILES` defines `general`, `ferpa`, `hipaa`, and `strict`
(Maximum) profiles.  Built-in GUI presets in `detector.PRESETS` include
"FERPA Only", "HIPAA Only", "Full (FERPA + HIPAA)", and "Maximum / Strict".

A policy profile should support compliance workflows but must not claim
that the tool alone establishes FERPA/HIPAA legal compliance.  Full-face
photos (HIPAA #17) and biometric images are not auto-detected.
