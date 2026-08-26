# Entity Policy

## Default structured entities

The deterministic detector supports:

- EMAIL_ADDRESS
- US_SSN
- PHONE_NUMBER
- CREDIT_CARD (Luhn-valid candidate only)
- IP_ADDRESS
- URL

These recognizers are intentionally conservative and are not a complete regulatory taxonomy.

## Optional Presidio entities

When `presidio-analyzer` and its local NLP dependencies are installed, `--presidio` can add recognizers supported by the local Presidio configuration, commonly including PERSON, LOCATION, ORGANIZATION and additional structured identifiers.

The skill uses Presidio as an in-process Python library. It must not launch the Presidio HTTP server.

## Custom policies

For a compliance-specific derivative, define:

1. exact entity categories;
2. jurisdiction/country where relevant;
3. deterministic validation rules (checksums, formats, context words);
4. minimum detection confidence;
5. required handling action: redact, mask, tokenize, or manual review;
6. whether metadata, annotations, attachments, form fields, signatures, faces, barcodes, or QR codes are in scope;
7. mandatory verification steps and evidence to retain.

A policy profile should support compliance workflows but must not claim that the skill alone establishes legal compliance.
