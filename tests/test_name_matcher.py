from __future__ import annotations

from chatops.services.name_matcher import match_name


def test_match_name_accepts_normalized_exact_variants() -> None:
    result = match_name("Demo_Prod", ["demo-prod", "alpha"])

    assert result.matched_name == "demo-prod"
    assert result.match_type == "normalized_exact"
    assert result.auto_corrected is True


def test_match_name_auto_corrects_unique_high_confidence_candidate() -> None:
    result = match_name("api dem", ["api-demo", "web-demo"])

    assert result.matched_name == "api-demo"
    assert result.match_type == "fuzzy_unique"
    assert result.auto_corrected is True


def test_match_name_returns_suggestions_when_match_is_ambiguous() -> None:
    result = match_name("demo", ["demo-prod", "demo-test"])

    assert result.matched_name is None
    assert result.auto_corrected is False
    assert "demo-prod" in result.suggestions
    assert "demo-test" in result.suggestions


def test_match_name_does_not_auto_correct_short_prefix_candidate() -> None:
    result = match_name("demo", ["demo-test", "alpha"])

    assert result.matched_name is None
    assert result.auto_corrected is False
    assert "demo-test" in result.suggestions
