"""Pure, conservative setting checks for a field's result comparison table.

Matching extracted strings only nominates a pair for source review. It does not
establish equivalent assumptions, comparable oracle costs or a better theorem.
The caller must separately check whether each source version is current.
"""
from __future__ import annotations

import re

from research_scout.domain.models import AssessmentStatus, Result


_SETTING_DIMENSIONS = (
    "domain", "model", "objective", "assumptions", "quantifiers", "metric",
)
_REVIEW_STATUSES = {
    AssessmentStatus.UNCERTAIN, AssessmentStatus.CHALLENGED, AssessmentStatus.NEEDS_REVIEW,
}
_PLACEHOLDER = re.compile(
    r"^(?:unknown|unspecified|unresolved|unavailable|not provided|not stated|"
    r"not specified|not extracted|not available|to be verified|needs review|"
    r"n/?a|tbd|未知|未说明|未提取|待核验|待确认)(?:\s*[:：;(（].*)?$",
    re.IGNORECASE,
)
_INCOMPLETE = re.compile(
    r"\bnot (?:fully )?(?:expanded|extracted|specified|stated|available|checked|verified)\b"
    r"|未展开|未核验|尚不明确",
    re.IGNORECASE,
)
# Only reference-shaped terms: a number/list/range and optionally a one-word
# parenthetical label. A colon or any actual statement falls outside this gate.
_ASSUMPTION_NUMBER = r"\d+(?:\.\d+)*"
_UNEXPANDED_ASSUMPTION = re.compile(
    r"assumptions?\s+" + _ASSUMPTION_NUMBER
    + r"(?:\s*(?:,\s*(?:and\s+)?|and\s+|&\s*|to\s+|[-–—]\s*)"
    + _ASSUMPTION_NUMBER + r")*\s*(?:\([A-Za-z][A-Za-z-]*\))?\s*[.;]?",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    # Do not lowercase or strip punctuation: mathematical case can change meaning.
    return " ".join(value.split())


def _terms(value: str | list[str]):
    if isinstance(value, list):
        return tuple(sorted({_normalize(term) for term in value}))
    return _normalize(value)


def _unknown(value: str) -> bool:
    value = _normalize(value)
    return not value or bool(_PLACEHOLDER.fullmatch(value) or _INCOMPLETE.search(value))


def compare_field_results(left: Result, right: Result) -> dict:
    """Compare extracted settings without inferring mathematical superiority.

    Missing scope information overrides detected differences. Guarantees, rates
    and statements describe outcomes and are reported separately from settings.
    No semantic synonym matching, assumption implication or rate algebra is used.
    """
    differing = [
        field for field in _SETTING_DIMENSIONS
        if _terms(getattr(left.scope, field)) != _terms(getattr(right.scope, field))
    ]
    if left.result_type != right.result_type:
        differing.append("result_type")
    outcome_differences = []
    if _normalize(left.scope.guarantee) != _normalize(right.scope.guarantee):
        outcome_differences.append("guarantee")
    if (None if left.rate is None else _normalize(left.rate)) != (
        None if right.rate is None else _normalize(right.rate)
    ):
        outcome_differences.append("rate")
    if _normalize(left.statement) != _normalize(right.statement):
        outcome_differences.append("statement")

    unresolved = []
    for side, result in (("left", left), ("right", right)):
        for field in (*_SETTING_DIMENSIONS, "guarantee"):
            value = getattr(result.scope, field)
            if isinstance(value, list):
                if not value or any(_unknown(term) for term in value):
                    unresolved.append(f"{side}.scope.{field}: missing or unresolved terms")
                if field == "assumptions" and any(
                    _UNEXPANDED_ASSUMPTION.fullmatch(_normalize(term)) for term in value
                ):
                    unresolved.append(f"{side}.scope.assumptions: numbered references are not expanded")
            elif _unknown(value):
                unresolved.append(f"{side}.scope.{field}: missing or unresolved value")
        unresolved.extend(f"{side}.scope.unresolved: {term}" for term in result.scope.unresolved)
        if result.assessment_status in _REVIEW_STATUSES:
            unresolved.append(f"{side}.assessment_status: {result.assessment_status}")
        # Result has no source-currentness field. Respect explicit revision/review
        # markers when present; an ordinary unverified extraction remains eligible
        # for setting review, without being promoted to verified mathematics.
        if re.search(
            r"NEEDS[ _-]*REVIEW|STALE|SUPERSEDED|SOURCE[ _-]*(?:REVISED|REVISION|CHANGED)",
            result.verification_status, re.IGNORECASE,
        ):
            unresolved.append(f"{side}.verification_status: {result.verification_status}")

    if unresolved:
        status = "INSUFFICIENT_INFORMATION"
        rationale = "Resolve missing scope information or source review flags before comparison."
    elif differing:
        status = "DIFFERENT_SCOPE"
        rationale = "Extracted settings differ; no assumption implication or theorem ordering is inferred."
    else:
        status = "SAME_SCOPE_REQUIRES_REVIEW"
        rationale = (
            "Extracted setting strings match after whitespace and list-order normalization; "
            "source assumptions, initialization and oracle costs still require review."
        )
    return {
        "left_result_id": left.id,
        "right_result_id": right.id,
        "status": status,
        "differing_dimensions": differing,
        "outcome_differences": outcome_differences,
        "unresolved": unresolved,
        "rate_comparison": "UNASSESSED",
        "rationale": rationale,
    }
