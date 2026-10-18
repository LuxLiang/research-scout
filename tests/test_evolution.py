"""SYNTHETIC scientific histories: software gates, not mathematical validation."""
from datetime import date, datetime, timezone

import pytest

from research_scout.breakthrough import BreakthroughDiscovery
from research_scout.domain.models import (
    AssessmentStatus as A, Attempt, Bottleneck, Coverage, DeltaKind, Evidence,
    EvolutionEvent, EventType as E, LiteratureDelta, Mechanism, Paper, PaperVersion,
    PreciseProblem, ProblemStatus as P, ResolutionKind as R, Result, Scope,
)
from research_scout.evolution import (
    EventStore, ProblemEvolutionTimeline, assess_resolution, flag_version_review,
)
from research_scout.storage import Archive


@pytest.fixture
def history(tmp_path):
    archive = Archive(tmp_path / "SYNTHETIC-archive")
    scope = Scope(domain="sampling", model="kinetic diffusion", objective="mixing",
                  assumptions=["smooth potential"], quantifiers=["all dimensions"],
                  metric="W2", guarantee="exponential decay")
    paper = Paper(id="paper-c", title="SYNTHETIC paper C", synthetic=True,
                  version_ids=["version-c1"])
    version = PaperVersion(id="version-c1", title="SYNTHETIC C v1", paper_id=paper.id,
                           version="v1", published=date(2026, 1, 1), synthetic=True,
                           coverage=Coverage.FULL_TEXT)
    evidence = Evidence(id="evidence-c1", title="SYNTHETIC supplied theorem span",
                        paper_id=paper.id, version_id=version.id, locator="Synthetic theorem S1",
                        coverage=Coverage.FULL_TEXT, assessment_status=A.SUPPORTED_BY_SOURCE,
                        synthetic=True)
    problem = PreciseProblem(id="problem-p", title="SYNTHETIC P", statement="Mix kinetic diffusion",
                             scope=scope, desired_result="exponential decay", synthetic=True,
                             bottleneck_ids=["bottleneck-b"], structures=["degenerate dissipation"])
    bottleneck = Bottleneck(id="bottleneck-b", title="SYNTHETIC missing dissipation",
                            description="No direct position noise", obstruction="degenerate generator",
                            insufficiency="Euclidean contraction misses velocity transport",
                            problem_ids=[problem.id], structures=["degenerate dissipation"],
                            attempts=[Attempt(description="Euclidean metric", outcome="FAILED",
                                              mechanism_id="mechanism-old",
                                              reason="Cross term has indefinite sign",
                                              evidence_ids=[evidence.id])], synthetic=True)
    old = Mechanism(id="mechanism-old", title="SYNTHETIC old metric", principle="Euclidean metric",
                    synthetic=True)
    new = Mechanism(id="mechanism-new", title="SYNTHETIC corrected metric",
                    principle="transport-corrected metric", structures=["degenerate dissipation"],
                    necessary_assumptions=["smooth potential"], synthetic=True)
    result = Result(id="result-c", title="SYNTHETIC C theorem", paper_id=paper.id,
                    version_id=version.id, result_type="THEOREM", statement="SYNTHETIC mixing bound",
                    scope=scope, problem_ids=[problem.id], mechanism_ids=[new.id],
                    bottleneck_ids=[bottleneck.id], evidence_ids=[evidence.id],
                    assessment_status=A.SUPPORTED_BY_SOURCE, synthetic=True,
                    technical_delta="Replace the indefinite Euclidean cross term with a "
                                    "transport-corrected quadratic form; smoothness controls its remainder.")
    archive.put_many([paper, version, evidence, problem, bottleneck, old, new, result])
    return archive


def event(archive, eid, event_type, year=2026, previous=None, related=None, **kwargs):
    return EvolutionEvent(
        id=eid, title=f"SYNTHETIC {event_type}", event_type=event_type,
        subject_id="problem-p", scientific_date=date(year, 1, 1),
        recorded_at=datetime(year, 2, 1, tzinfo=timezone.utc), paper_id="paper-c",
        version_id="version-c1", scope=archive.get("problem-p").scope,
        previous_event_ids=previous or [], related_ids=related or [],
        evidence_ids=["evidence-c1"], assessment_status=A.SUPPORTED_BY_SOURCE,
        rationale="SYNTHETIC attribution", synthetic=True, **kwargs,
    )


def close(archive):
    assessment = assess_resolution(archive, "problem-p", "result-c")
    e = event(archive, "event-resolution", E.SUPPORTED_RESOLUTION,
              related=["result-c", assessment.id], resolution=R.FULL_RESOLUTION_SUPPORTED)
    EventStore(archive).append(e)
    return e


def test_exact_resolution_is_attribution_not_proof(history):
    assessment = assess_resolution(history, "problem-p", "result-c")
    assert assessment.resolution == R.FULL_RESOLUTION_SUPPORTED
    assert assessment.assessment_status == A.SUPPORTED_BY_SOURCE
    assert "not independent mathematical verification" in assessment.rationale
    assert history.get("result-c").verification_status == "NOT_MATHEMATICALLY_VERIFIED"


def test_stronger_assumptions_never_close_original(history):
    result = history.get("result-c")
    result.scope = result.scope.model_copy(update={"assumptions": ["smooth potential", "convexity"]})
    history.put(result)
    assessment = assess_resolution(history, "problem-p", "result-c")
    assert assessment.resolution == R.CONDITIONAL_RESOLUTION
    EventStore(history).append(event(history, "conditional", E.CONDITIONAL_RESOLUTION,
                                    related=["result-c", assessment.id],
                                    resolution=R.CONDITIONAL_RESOLUTION))
    snapshot = ProblemEvolutionTimeline(history, "problem-p").build()
    assert snapshot.status == P.CONDITIONALLY_RESOLVED
    assert snapshot.unresolved_scope


@pytest.mark.parametrize("field,value", [
    ("metric", "KL divergence"), ("quantifiers", ["one dimension"]),
    ("model", "overdamped diffusion"), ("objective", "optimization"),
    ("guarantee", "polynomial decay"), ("assumptions", ["log-concavity"]),
])
def test_unknown_implication_is_incomparable(history, field, value):
    result = history.get("result-c")
    result.scope = result.scope.model_copy(update={field: value})
    history.put(result)
    assert assess_resolution(history, "problem-p", result.id).resolution == R.INCOMPARABLE


def test_author_claim_and_abstract_only_never_close(history):
    result = history.get("result-c")
    result.assessment_status = A.EXTRACTED
    history.put(result)
    assert assess_resolution(history, "problem-p", result.id).resolution == R.CLAIMED_BUT_UNVERIFIED
    result = history.get(result.id)
    result.assessment_status = A.SUPPORTED_BY_SOURCE
    history.put(result)
    ev = history.get("evidence-c1")
    ev = ev.model_copy(update={"id": "evidence-c1-abstract", "coverage": Coverage.ABSTRACT_ONLY})
    history.put(ev)
    result = history.get(result.id)
    result.evidence_ids = [ev.id]
    history.put(result)
    assert assess_resolution(history, "problem-p", result.id).resolution == R.CLAIMED_BUT_UNVERIFIED


def test_immutable_timeline_replay_challenge_reopen_and_rebuild(history):
    store = EventStore(history)
    posed = event(history, "event-posed", E.PROBLEM_POSED, 2023)
    partial = event(history, "event-partial", E.PARTIAL_PROGRESS, 2024, [posed.id])
    store.append(posed)
    store.append(partial)
    resolved = close(history)
    timeline = ProblemEvolutionTimeline(history, "problem-p")
    assert timeline.build(as_of=date(2023, 12, 31)).status == P.OPEN
    assert timeline.build(as_of=date(2024, 12, 31)).status == P.PARTIAL
    assert timeline.build().status == P.RESOLVED_SUPPORTED
    challenge = event(history, "event-challenge", E.CHALLENGED, 2027, [resolved.id])
    store.append(challenge)
    assert timeline.build().status == P.CHALLENGED
    store.append(event(history, "event-reopen", E.REOPENED, 2028))
    assert timeline.build().status == P.REOPENED
    assert len(timeline.build().events) == 5
    assert timeline.build().first_posed == date(2023, 1, 1)
    with pytest.raises(ValueError, match="immutable"):
        store.append(resolved.model_copy(update={"rationale": "rewritten"}))
    history.rebuild()
    assert timeline.build().status == P.REOPENED
    assert timeline.build(as_of=date(2026, 12, 31)).status == P.RESOLVED_SUPPORTED


def test_supersession_retains_history_and_removes_closure(history):
    resolved = close(history)
    EventStore(history).append(event(history, "event-supersede", E.SUPERSEDED, 2027,
                                    [resolved.id]))
    snapshot = ProblemEvolutionTimeline(history, "problem-p").build()
    assert len(snapshot.events) == 2
    assert snapshot.status != P.RESOLVED_SUPPORTED
    assert history.get(resolved.id) == resolved


def test_revision_flags_assessments_preserves_events_and_as_known_history(history):
    resolved = close(history)
    breakthrough = BreakthroughDiscovery(history).analyze("result-c")
    comparison = LiteratureDelta(
        id="comparison-c", title="SYNTHETIC comparison", paper_id="paper-c",
        version_id="version-c1", new_result_id="result-c", delta_kinds=[DeltaKind.POTENTIAL_RESOLUTION],
        rationale="SYNTHETIC", evidence_ids=["evidence-c1"], synthetic=True,
    )
    history.put(comparison)
    version2 = PaperVersion(id="version-c2", title="SYNTHETIC C v2 revised theorem",
                            paper_id="paper-c", version="v2", supersedes_version_id="version-c1",
                            coverage=Coverage.FULL_TEXT, synthetic=True)
    history.put(version2)
    affected = flag_version_review(history, "version-c1", "version-c2")
    assert breakthrough.id in affected
    assert comparison.id in affected
    assert history.get(breakthrough.id).needs_review
    timeline = ProblemEvolutionTimeline(history, "problem-p")
    assert timeline.build().status != P.RESOLVED_SUPPORTED
    assert timeline.build().requires_review
    assert timeline.build(recorded_before=datetime(2026, 3, 1, tzinfo=timezone.utc)).status == P.RESOLVED_SUPPORTED
    assert history.get(resolved.id) == resolved
    assert history.get("version-c1").version == "v1"
    assert flag_version_review(history, "version-c1", "version-c2") == []


def test_breakthrough_reports_actual_delta_attempt_and_unresolved_analogs(history):
    target = PreciseProblem(
        id="problem-q", title="SYNTHETIC online learning Q", statement="Control delayed feedback",
        scope=history.get("problem-p").scope.model_copy(update={"domain": "learning"}),
        desired_result="regret bound", structures=["degenerate dissipation"], synthetic=True,
    )
    history.put(target)
    assessment = BreakthroughDiscovery(history).analyze("result-c")
    assert assessment.technical_delta == history.get("result-c").technical_delta
    assert assessment.previous_mechanisms == ["mechanism-old"]
    assert assessment.analogous_problem_ids == [target.id]
    assert any("Cross term has indefinite sign" in q for q in assessment.unresolved_questions)
    assert any("smooth potential" in q for q in assessment.unresolved_questions)
    assert assessment.assessment_status == A.SUPPORTED_BY_SOURCE
    again = BreakthroughDiscovery(history).analyze("result-c")
    assert again.id == assessment.id
    assert len(history.list("breakthrough")) == 1


def test_missing_delta_stays_uncertain_without_inventing_proof(history):
    result = history.get("result-c")
    result.technical_delta = ""
    history.put(result)
    assessment = BreakthroughDiscovery(history).analyze(result.id)
    assert assessment.assessment_status == A.UNCERTAIN
    assert "not documented" in assessment.technical_delta


def test_empirical_result_is_not_a_quantified_theorem(history):
    result = history.get("result-c")
    result.result_type = "EMPIRICAL"
    history.put(result)
    assert assess_resolution(history, "problem-p", result.id).resolution == R.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize("version_name", ["v2", "v1+content-enriched"])
def test_revision_without_cached_assessment_invalidates_direct_event(history, version_name):
    store = EventStore(history)
    store.append(event(history, "direct-resolution", E.SUPPORTED_RESOLUTION,
                       related=["result-c"], resolution=R.FULL_RESOLUTION_SUPPORTED))
    timeline = ProblemEvolutionTimeline(history, "problem-p")
    assert timeline.build().status == P.RESOLVED_SUPPORTED
    # Direct imports are permitted; no derived assessment existed at revision time.
    assert history.list("resolution_assessment") == []
    history.put(PaperVersion(
        id="version-c-revised", title="SYNTHETIC revised source", paper_id="paper-c",
        version=version_name, supersedes_version_id="version-c1", coverage=Coverage.FULL_TEXT,
        published=date(2027, 1, 1), synthetic=True,
    ))
    assert flag_version_review(history, "version-c1", "version-c-revised") == []
    snapshot = timeline.build()
    assert snapshot.status != P.RESOLVED_SUPPORTED
    assert snapshot.requires_review
    late_assessment = assess_resolution(history, "problem-p", "result-c")
    assert late_assessment.needs_review
    assert late_assessment.resolution == R.CLAIMED_BUT_UNVERIFIED
    assert BreakthroughDiscovery(history).analyze("result-c").needs_review
    # Scientific chronology and recording chronology remain independent.
    assert timeline.build(as_of=date(2026, 12, 31)).status == P.RESOLVED_SUPPORTED
    assert timeline.build(recorded_before=datetime(2026, 3, 1, tzinfo=timezone.utc)).status == P.RESOLVED_SUPPORTED


def test_existing_assessment_becomes_stale_even_without_explicit_invalidation_hook(history):
    before = assess_resolution(history, "problem-p", "result-c")
    history.put(PaperVersion(
        id="version-c2", title="SYNTHETIC source revision", paper_id="paper-c",
        version="v2", supersedes_version_id="version-c1", synthetic=True,
    ))
    after = assess_resolution(history, "problem-p", "result-c")
    assert after.id == before.id
    assert after.needs_review
    assert after.assessment_status == A.NEEDS_REVIEW
    assert history.history(before.id)[0].needs_review is False


@pytest.mark.parametrize("changed_field", [None, "model", "metric"])
def test_counterexample_subclass_can_challenge_only_matching_original_formulation(history, changed_field):
    resolved = close(history)
    changes = {"assumptions": history.get("problem-p").scope.assumptions + ["quadratic potential"]}
    if changed_field:
        changes[changed_field] = "different formulation"
    witness_scope = history.get("problem-p").scope.model_copy(update=changes)
    witness = event(history, "subclass-counterexample", E.COUNTEREXAMPLE_DISCOVERED,
                    year=2027, previous=[resolved.id]).model_copy(update={"scope": witness_scope})
    EventStore(history).append(witness)
    status = ProblemEvolutionTimeline(history, "problem-p").build().status
    assert status == (P.CHALLENGED if changed_field is None else P.RESOLVED_SUPPORTED)


def test_proposed_counterexample_does_not_refute_source_supported_resolution(history):
    resolved = close(history)
    witness = event(history, "unreviewed-counterexample", E.COUNTEREXAMPLE_DISCOVERED,
                    year=2027, previous=[resolved.id]).model_copy(update={
                        "assessment_status": A.PROPOSED,
                    })
    EventStore(history).append(witness)
    assert ProblemEvolutionTimeline(history, "problem-p").build().status == P.RESOLVED_SUPPORTED


def test_seeded_future_results_and_attempts_are_not_presented_as_prior_history(history):
    future = Result(
        id="result-future", title="SYNTHETIC future theorem", paper_id="paper-future",
        version_id="version-future", scope=history.get("problem-p").scope,
        result_type="THEOREM", statement="A future result", problem_ids=["problem-p"],
        mechanism_ids=["mechanism-future"], synthetic=True,
    )
    problem = history.get("problem-p").model_copy(update={"known_result_ids": [future.id]})
    result = history.get("result-c").model_copy(update={"previous_result_ids": [future.id]})
    bottleneck = history.get("bottleneck-b")
    bottleneck.attempts.append(Attempt(description="Future failed attempt", outcome="FAILED",
                                       result_id=future.id, mechanism_id="mechanism-future"))
    history.put_many([
        Paper(id="paper-future", title="SYNTHETIC future paper", synthetic=True),
        PaperVersion(id="version-future", title="SYNTHETIC future source", paper_id="paper-future",
                     version="v1", published=date(2027, 1, 1), synthetic=True),
        Mechanism(id="mechanism-future", title="SYNTHETIC future mechanism",
                  principle="Future construction", synthetic=True),
        future, problem, result, bottleneck,
    ])
    assessment = BreakthroughDiscovery(history).analyze("result-c")
    assert future.id not in assessment.historical_results
    assert "mechanism-future" not in assessment.previous_mechanisms
    assert any(f"Excluded {future.id}" in q for q in assessment.unresolved_questions)
