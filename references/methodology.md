# Local Skill Methodology

1. **Define the privacy boundary first.** Identify what must never leave the machine and prohibit networked substitutes in the skill instructions.
2. **Prefer native/local interfaces.** Use an installed CLI, file format, or local library instead of adding a server layer.
3. **Keep reasoning separate from execution.** Hermes decides workflow and reviews results; deterministic scripts perform irreversible transformations.
4. **Use inspect/plan/apply/verify.** Destructive changes require a reviewable intermediate plan whenever practical.
5. **Minimize dependencies.** Require only packages that materially improve correctness; make heavyweight components optional.
6. **Fail closed.** Missing OCR, unsupported formats, conversion errors, or uncertain verification produce warnings/NEEDS_REVIEW rather than silent success.
7. **Avoid sensitive logs.** Store masked values and fingerprints by default instead of plaintext PII.
8. **Never overwrite originals by default.** Generate a new artifact and preserve provenance.
9. **Verify with a different pass.** Re-read/re-OCR the produced artifact rather than trusting only the write operation.
10. **Separate technical support from compliance claims.** Encode framework-specific rules as policy profiles, but never claim certification or legal compliance from tool execution alone.
