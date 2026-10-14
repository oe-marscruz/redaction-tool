"""Tests for expanded Presidio recognizer integration, category mapping, and fail-closed safety.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from redaction_tool import detector


def test_use_presidio_false_equivalence_to_baseline():
    """use_presidio=False must preserve exact baseline behavior and never touch Presidio."""
    text = "Call John Doe at 555-123-4567 or email john@example.com."
    baseline = detector.detect(text, use_presidio=False)
    default_call = detector.detect(text)
    assert baseline == default_call

    # Ensure get_presidio_engine is never called when use_presidio=False
    with patch.object(detector, "get_presidio_engine", side_effect=AssertionError("Should not be called")):
        res = detector.detect(text, use_presidio=False)
        assert res == baseline


def test_exact_category_whitelist_and_disabled_category_filtering():
    """Verify category filtering before requesting Presidio entities AND after mapping results."""
    text = "Jane Doe lives in Boston, SSN 214-55-1234."

    class MockAnalyzer:
        def __init__(self):
            self.requested_entities = []

        def analyze(self, *, text, entities, language):
            self.requested_entities.append(list(entities))
            # Return a mix of requested and unknown/disabled entities
            return [
                SimpleNamespace(start=0, end=8, entity_type="PERSON", score=0.9),
                SimpleNamespace(start=18, end=24, entity_type="LOCATION", score=0.85),
                SimpleNamespace(start=30, end=41, entity_type="US_SSN", score=0.95),
                SimpleNamespace(start=0, end=8, entity_type="UNKNOWN_TYPE", score=0.99),
            ]

    mock_engine = MockAnalyzer()
    with patch.object(detector, "get_presidio_engine", return_value=mock_engine):
        # 1. Request only 'names'
        matches_names = detector.detect(text, enabled_categories=["names"], use_presidio=True)
        assert mock_engine.requested_entities[-1] == ["PERSON"]
        assert all(m.category == "names" for m in matches_names)
        assert not any(m.category == "addresses" or m.category == "ssn" for m in matches_names)

        # 2. Request 'addresses' and 'ssn'
        matches_addr_ssn = detector.detect(
            text, enabled_categories=["addresses", "ssn"], use_presidio=True
        )
        assert sorted(mock_engine.requested_entities[-1]) == ["LOCATION", "US_SSN"]
        categories = {m.category for m in matches_addr_ssn}
        assert "names" not in categories
        assert "UNKNOWN_TYPE" not in categories


def test_none_versus_empty_list_enabled_categories():
    """None defaults to all categories; [] enables no standard categories."""
    text = "John Doe at john@example.com"

    # None -> all standard categories enabled
    res_none = detector.detect(text, enabled_categories=None, use_presidio=False)
    assert len(res_none) > 0

    # [] -> no standard categories enabled
    res_empty = detector.detect(text, enabled_categories=[], use_presidio=False)
    assert res_empty == []

    # [] with use_presidio=True should not request any Presidio entities
    if detector.presidio_is_available():
        res_empty_presidio = detector.detect(text, enabled_categories=[], use_presidio=True)
        assert res_empty_presidio == []


def test_person_and_location_detection():
    """Verify PERSON -> names and LOCATION -> addresses mapping."""
    if not detector.presidio_is_available():
        return

    text = "Alice Johnson travelled to Chicago."
    matches = detector.detect(text, enabled_categories=["names", "addresses"], use_presidio=True)
    categories_found = {m.category: m.text for m in matches}
    assert "names" in categories_found
    assert "Alice Johnson" in categories_found["names"]
    assert "addresses" in categories_found
    assert "Chicago" in categories_found["addresses"]


def test_at_least_six_builtin_entity_types_real_presidio():
    """Test at least 6 available built-in entity types using real pinned Presidio."""
    if not detector.presidio_is_available():
        raise AssertionError("Presidio optional package must be installed for this required test")

    test_cases = [
        ("Contact Alice Johnson for details.", "names", "Alice Johnson"),
        ("Located in San Francisco.", "addresses", "San Francisco"),
        ("Email user@example.org today.", "emails", "user@example.org"),
        ("Call 555-867-5309 immediately.", "phones", "555-867-5309"),
        ("Card number 4532015112830366 on file.", "accounts", "4532015112830366"),
        ("Server IP is 192.168.1.1.", "ips", "192.168.1.1"),
        ("Visit https://www.example.org now.", "urls", "https://www.example.org"),
        ("MAC address is 00:0a:95:9d:68:16.", "devices", "00:0a:95:9d:68:16"),
        ("Bank account 1234567890 active.", "accounts", "1234567890"),
    ]

    detected_categories = set()
    for text, expected_category, expected_subtext in test_cases:
        matches = detector.detect(
            text, enabled_categories=[expected_category], use_presidio=True
        )
        for m in matches:
            if m.category == expected_category and expected_subtext in m.text:
                detected_categories.add(expected_category)

    assert len(detected_categories) >= 6, (
        f"Expected at least 6 distinct categories detected via real Presidio, got {len(detected_categories)}: {detected_categories}"
    )


def test_mocked_results_and_invalid_spans():
    """Invalid spans (start < 0, end > len(text), start >= end) must be safely dropped."""
    text = "Sample text for testing."
    text_len = len(text)

    class InvalidSpanAnalyzer:
        def analyze(self, **kwargs):
            return [
                SimpleNamespace(start=-1, end=5, entity_type="PERSON", score=0.9),
                SimpleNamespace(start=0, end=text_len + 10, entity_type="PERSON", score=0.9),
                SimpleNamespace(start=5, end=5, entity_type="PERSON", score=0.9),
                SimpleNamespace(start=10, end=4, entity_type="PERSON", score=0.9),
                SimpleNamespace(start=0, end=6, entity_type="PERSON", score=0.85),  # "Sample"
            ]

    with patch.object(detector, "get_presidio_engine", return_value=InvalidSpanAnalyzer()):
        matches = detector.detect(text, enabled_categories=["names"], use_presidio=True)
        assert len(matches) == 1
        assert matches[0].text == "Sample"
        assert matches[0].start == 0
        assert matches[0].end == 6


def test_collision_with_deterministic_regex():
    """Deduplication must combine evidence without error when regex and Presidio match same span."""
    text = "Email test@example.com for help."

    class MockPresidio:
        def analyze(self, **kwargs):
            start = text.index("test@example.com")
            end = start + len("test@example.com")
            return [SimpleNamespace(start=start, end=end, entity_type="EMAIL_ADDRESS", score=1.0)]

    with patch.object(detector, "get_presidio_engine", return_value=MockPresidio()):
        matches = detector.detect(text, enabled_categories=["emails"], use_presidio=True)
        email_matches = [m for m in matches if m.text == "test@example.com"]
        assert len(email_matches) == 1
        m = email_matches[0]
        assert "regex" in m.evidence
        assert "presidio:EMAIL_ADDRESS:1.00" in m.evidence


def test_fail_closed_on_model_analyzer_or_registry_errors():
    """If use_presidio=True and analysis or engine fails, raise RuntimeError immediately."""
    class BrokenAnalyzer:
        def analyze(self, **kwargs):
            raise ValueError("Internal engine error")

    with patch.object(detector, "get_presidio_engine", return_value=BrokenAnalyzer()):
        try:
            detector.detect("Clean text.", enabled_categories=["names"], use_presidio=True)
        except RuntimeError as exc:
            assert "Presidio analysis failed" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError when Presidio analyze fails")

    with patch.object(detector, "get_presidio_engine", side_effect=RuntimeError("Engine init failed")):
        try:
            detector.detect("Clean text.", enabled_categories=["names"], use_presidio=True)
        except RuntimeError as exc:
            assert "Engine init failed" in str(exc)
        else:
            raise AssertionError("Expected RuntimeError when get_presidio_engine fails")


def test_offline_socket_and_tldextract_behavior():
    """Verify Presidio engine operates strictly offline without network sockets."""
    def guarded_socket(*args, **kwargs):
        raise RuntimeError("Network socket creation blocked during offline test")

    with patch("socket.socket", side_effect=guarded_socket):
        engine = detector.get_presidio_engine()
        assert engine is not None
        matches = detector.detect("User email test@domain.org", enabled_categories=["emails"], use_presidio=True)
        assert len(matches) > 0


def test_repeated_engine_use_and_thread_safety():
    """Verify AnalyzerEngine caching and thread-safe concurrent execution."""
    engine1 = detector.get_presidio_engine()
    engine2 = detector.get_presidio_engine()
    assert engine1 is engine2

    text = "Alice Johnson lives in Boston with email alice@example.com."

    def run_detection(idx: int):
        res = detector.detect(text, enabled_categories=["names", "addresses", "emails"], use_presidio=True)
        return len(res)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_detection, i) for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 10
    assert all(count > 0 for count in results)
    assert len(set(results)) == 1  # All threads get identical match counts


def test_optional_package_absent_fails_closed():
    """When optional Presidio dependencies are absent, use_presidio=True must raise RuntimeError."""
    with patch.object(detector, "presidio_is_available", return_value=False):
        with patch.object(detector, "get_presidio_engine", side_effect=RuntimeError("Presidio not installed")):
            try:
                detector.detect("Text here.", use_presidio=True)
            except RuntimeError as exc:
                assert "Presidio not installed" in str(exc)
            else:
                raise AssertionError("Expected RuntimeError when Presidio package is absent")


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
