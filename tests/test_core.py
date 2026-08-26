import importlib.util, pathlib
P=pathlib.Path(__file__).parents[1]/"scripts"/"ocr_redact.py"
spec=importlib.util.spec_from_file_location("ocr_redact",P); m=importlib.util.module_from_spec(spec); import sys; sys.modules["ocr_redact"]=m; spec.loader.exec_module(m)

def test_luhn():
    assert m.luhn_ok("4111 1111 1111 1111")
    assert not m.luhn_ok("4111 1111 1111 1112")

def test_detect_structured():
    text="Email jane@example.com SSN 123-45-6789 card 4111 1111 1111 1111"
    types={x[2] for x in m.detect_spans(text)}
    assert "EMAIL_ADDRESS" in types
    assert "US_SSN" in types
    assert "CREDIT_CARD" in types

def test_masking():
    assert "6789" in m.mask_value("US_SSN","123-45-6789")
    assert "j***@example.com" == m.mask_value("EMAIL_ADDRESS","jane@example.com")
