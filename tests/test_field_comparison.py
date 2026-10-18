"""Synthetic fixtures exercising conservative field-table comparison gates."""
from copy import deepcopy

import pytest

from research_scout.comparison.field_comparison import compare_field_results
from research_scout.domain.models import AssessmentStatus, Result, Scope


@pytest.fixture
def result_pair():
    left = Result(
        id="synthetic-result-left", title="Synthetic theorem", synthetic=True,
        paper_id="synthetic-paper-left", version_id="synthetic-version-left",
        result_type="THEOREM", statement="Synthetic finite-time bound",
        scope=Scope(
            domain="continuous sampling", model="strongly log-concave density",
            objective="sample a fixed target", metric="W2",
            assumptions=["L-smooth potential", "warm start"],
            quantifiers=["all dimensions d", "all epsilon in (0,1)"],
            guarantee="error at most epsilon",
        ), rate="O(d / epsilon^2)",
    )
    right = left.model_copy(deep=True, update={
        "id": "synthetic-result-right", "paper_id": "synthetic-paper-right",
        "version_id": "synthetic-version-right",
    })
    return left, right


@pytest.mark.parametrize("field,value", [
    ("metric", "KL"), ("model", "nonconvex density"),
    ("objective", "estimate a stationary marginal"),
    ("assumptions", ["L-smooth potential", "arbitrary initialization"]),
    ("quantifiers", ["fixed dimension d", "all epsilon in (0,1)"]),
])
def test_different_setting_never_orders_theorems(result_pair, field, value):
    left, right = result_pair
    setattr(right.scope, field, value)
    compared = compare_field_results(left, right)
    assert compared["status"] == "DIFFERENT_SCOPE"
    assert compared["differing_dimensions"] == [field]
    assert compared["rate_comparison"] == "UNASSESSED"


def test_changed_guarantee_and_rate_do_not_change_the_setting(result_pair):
    left, right = result_pair
    right.scope.guarantee = "error at most epsilon/2"
    right.rate = "O(log(d) / epsilon)"
    right.statement = "Synthetic alternative bound"
    compared = compare_field_results(left, right)
    assert compared["status"] == "SAME_SCOPE_REQUIRES_REVIEW"
    assert compared["differing_dimensions"] == []
    assert compared["outcome_differences"] == ["guarantee", "rate", "statement"]
    assert compared["rate_comparison"] == "UNASSESSED"


@pytest.mark.parametrize("field,value", [
    ("quantifiers", []), ("assumptions", []), ("assumptions", ["unknown"]),
    ("assumptions", ["Assumptions 1-3 (not expanded)"]), ("metric", "not extracted"),
    ("unresolved", ["initialization not available"]),
])
def test_incomplete_setting_overrides_detected_differences(result_pair, field, value):
    left, right = result_pair
    right.scope.metric = "TV"
    setattr(right.scope, field, value)
    compared = compare_field_results(left, right)
    assert compared["status"] == "INSUFFICIENT_INFORMATION"
    assert compared["unresolved"]
    assert compared["rate_comparison"] == "UNASSESSED"


@pytest.mark.parametrize("status", [
    AssessmentStatus.NEEDS_REVIEW, AssessmentStatus.CHALLENGED, AssessmentStatus.UNCERTAIN,
])
def test_review_flags_prevent_potential_scope_match(result_pair, status):
    left, right = result_pair
    right.assessment_status = status
    compared = compare_field_results(left, right)
    assert compared["status"] == "INSUFFICIENT_INFORMATION"
    assert any("assessment_status" in note for note in compared["unresolved"])


@pytest.mark.parametrize("status", ["SOURCE_REVISED", "STALE", "NEEDS_REVIEW"])
def test_explicit_source_revision_flags_prevent_scope_match(result_pair, status):
    left, right = result_pair
    right.verification_status = status
    assert compare_field_results(left, right)["status"] == "INSUFFICIENT_INFORMATION"


def test_empirical_observation_is_not_theorem(result_pair):
    left, right = result_pair
    right.result_type = "EMPIRICAL"
    compared = compare_field_results(left, right)
    assert compared["status"] == "DIFFERENT_SCOPE"
    assert compared["differing_dimensions"] == ["result_type"]


def test_list_order_and_whitespace_only_normalization(result_pair):
    left, right = result_pair
    right.scope.assumptions = [" warm   start ", "L-smooth potential"]
    right.scope.quantifiers.reverse()
    compared = compare_field_results(left, right)
    assert compared["status"] == "SAME_SCOPE_REQUIRES_REVIEW"
    right.scope.assumptions[1] = "l-smooth potential"
    assert compare_field_results(left, right)["status"] == "DIFFERENT_SCOPE"


def test_comparison_leaves_records_and_verification_untouched(result_pair):
    left, right = result_pair
    before = deepcopy([left.model_dump(), right.model_dump()])
    compared = compare_field_results(left, right)
    assert [left.model_dump(), right.model_dump()] == before
    assert compared["status"] == "SAME_SCOPE_REQUIRES_REVIEW"
    assert left.verification_status == "NOT_MATHEMATICALLY_VERIFIED"


@pytest.mark.parametrize("term", [
    "Assumption 2.1", "Assumptions 1 and 2", "Assumption 1 (regularity).",
    "Assumptions 1–3", "Assumptions 1, 2, and 3.", " Assumption   2.1; ",
])
def test_unexpanded_numbered_assumptions_do_not_establish_matching_settings(result_pair, term):
    left, right = result_pair
    left.scope.assumptions = right.scope.assumptions = [term]
    compared = compare_field_results(left, right)
    assert compared["status"] == "INSUFFICIENT_INFORMATION"
    assert compared["differing_dimensions"] == []
    assert any("numbered references are not expanded" in note for note in compared["unresolved"])
    assert compared["rate_comparison"] == "UNASSESSED"


@pytest.mark.parametrize("term", [
    "Assumption 2.1: f is globally Lipschitz.",
    "Assumption 1 (regularity): f has a globally Lipschitz gradient.",
    "Assumption 1 (f is globally Lipschitz).",
    "Assumptions 1 and 2 state that f is convex and globally Lipschitz.",
])
def test_expanded_assumption_text_is_retained_without_semantic_guessing(result_pair, term):
    left, right = result_pair
    left.scope.assumptions = right.scope.assumptions = [term]
    compared = compare_field_results(left, right)
    assert compared["status"] == "SAME_SCOPE_REQUIRES_REVIEW"
    assert compared["unresolved"] == []
