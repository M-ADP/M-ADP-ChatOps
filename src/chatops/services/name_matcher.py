from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher


def normalize_name(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


@dataclass(frozen=True)
class NameMatchResult:
    matched_name: str | None
    match_type: str | None
    auto_corrected: bool
    suggestions: list[str]


def match_name(query: str, candidates: list[str]) -> NameMatchResult:
    if not query.strip() or not candidates:
        return NameMatchResult(matched_name=None, match_type=None, auto_corrected=False, suggestions=[])

    stripped_query = query.strip()
    lowered_query = stripped_query.lower()
    normalized_query = normalize_name(stripped_query)

    for candidate in candidates:
        if candidate == stripped_query:
            return NameMatchResult(
                matched_name=candidate,
                match_type="exact",
                auto_corrected=False,
                suggestions=[],
            )

    for candidate in candidates:
        if candidate.lower() == lowered_query:
            return NameMatchResult(
                matched_name=candidate,
                match_type="case_insensitive_exact",
                auto_corrected=True,
                suggestions=[],
            )

    normalized_candidates = {
        candidate: normalize_name(candidate)
        for candidate in candidates
    }
    for candidate, normalized_candidate in normalized_candidates.items():
        if normalized_candidate == normalized_query:
            return NameMatchResult(
                matched_name=candidate,
                match_type="normalized_exact",
                auto_corrected=True,
                suggestions=[],
            )

    scored: list[tuple[str, float]] = []
    for candidate, normalized_candidate in normalized_candidates.items():
        if not normalized_candidate:
            continue
        score = _score_candidate(normalized_query, normalized_candidate)
        if score > 0:
            scored.append((candidate, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    if not scored:
        return NameMatchResult(matched_name=None, match_type=None, auto_corrected=False, suggestions=[])

    top_candidate, top_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    suggestions = [candidate for candidate, _score in scored[:3]]
    if (
        top_score >= 0.84
        and (top_score - second_score) >= 0.08
        and _is_safe_auto_correction(normalized_query, normalized_candidates[top_candidate])
    ):
        return NameMatchResult(
            matched_name=top_candidate,
            match_type="fuzzy_unique",
            auto_corrected=True,
            suggestions=suggestions[1:],
        )
    return NameMatchResult(
        matched_name=None,
        match_type=None,
        auto_corrected=False,
        suggestions=suggestions,
    )


def _score_candidate(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    if candidate.startswith(query) or query.startswith(candidate):
        return 0.95
    if query in candidate:
        return 0.9
    return SequenceMatcher(a=query, b=candidate).ratio()


def _is_safe_auto_correction(query: str, candidate: str) -> bool:
    if not query or not candidate:
        return False
    if candidate.startswith(query) or query.startswith(candidate) or query in candidate:
        length_ratio = min(len(query), len(candidate)) / max(len(query), len(candidate))
        return length_ratio >= 0.75
    return True
