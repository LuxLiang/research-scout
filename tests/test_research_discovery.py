"""Synthetic discovery checks are scientific guardrails, not mathematical validation."""
import pytest

from research_scout.breakthrough import BreakthroughDiscovery
from research_scout.domain.models import (
    AssessmentStatus, Bottleneck, OpportunityStatus, PreciseProblem, Result, TransferMode,
)
from research_scout.novelty import ExternalPriorArt, NoveltyAudit
from research_scout.opportunities import DIMENSIONS, OpportunityPortfolio
from research_scout.storage import Archive
from research_scout.transfer import TransferDiscovery
from research_scout.workflows.demo import import_history


@pytest.fixture
def archive(tmp_path):
    archive = Archive(tmp_path / "knowledge")
    import_history(archive)
    BreakthroughDiscovery(archive).analyze("result-c")
    return archive


def test_four_modes_are_grounded_unproved_and_persistent(archive):
    discovery = TransferDiscovery(archive)
    breakthrough = archive.list("breakthrough")[0]
    for mode, seed in [("technique-first", "mechanism-cross"),
                       ("problem-first", "problem-q"),
                       ("breakthrough-first", breakthrough.id)]:
        candidates = discovery.discover(mode, seed)
        assert candidates
        candidate = next(c for c in candidates if c.source_mechanism_id == "mechanism-cross")
        assert candidate.source_problem_id == "problem-p"
        assert candidate.target_problem_id == "problem-q"
        assert candidate.source_bottleneck_id == "bottleneck-dissipation"
        assert candidate.target_bottleneck_id == "bottleneck-delay"
        assert candidate.breakthrough_id == breakthrough.id
        assert candidate.structural_differences and candidate.shared_structures
        assert candidate.required_assumptions and candidate.missing_lemmas
        assert candidate.likely_counterexamples and candidate.prior_art_ids
        assert candidate.first_falsification_test and candidate.uncertainty
        assert candidate.outcome == "PROPOSED"
        assert candidate.assessment_status == AssessmentStatus.PROPOSED
        assert archive.get(candidate.id) == candidate
        assert discovery.discover(mode, seed) == candidates
    candidate = discovery.propose("mechanism-cross", "problem-q")
    discovery.record_failure(candidate.id, "Unbounded delay creates oscillation",
                             counterexamples=["Unbounded-delay oscillatory mode"],
                             evidence_ids=["evidence-q-failure"])
    retries = discovery.discover("failure-first", candidate.id)
    assert retries
    assert all(r.mode == TransferMode.FAILURE_FIRST for r in retries)
    assert all(r.previous_transfer_id == candidate.id for r in retries)
    assert all("Unbounded delay creates oscillation" in r.first_falsification_test for r in retries)
    assert all(any("Resolve retained failure" in x for x in r.missing_lemmas) for r in retries)
    assert all(r.outcome == "PROPOSED" for r in retries)


def test_failure_survives_restart_and_rediscovery_blocks_existing_portfolio(archive):
    discovery = TransferDiscovery(archive)
    transfer = discovery.propose("mechanism-cross", "problem-q")
    portfolio = OpportunityPortfolio(archive)
    opportunity = portfolio.from_transfer(transfer.id)
    failed = discovery.record_failure(transfer.id, "Missing delay commutator bound")
    assert failed.outcome == "FAILED"
    reloaded = Archive(archive.root)
    assert TransferDiscovery(reloaded).propose("mechanism-cross", "problem-q") == failed
    assert reloaded.get("mechanism-cross").attempts[-1].reason == failed.failure_reason
    assert reloaded.get("bottleneck-delay").attempts[-1].reason == failed.failure_reason
    blocked = reloaded.get(opportunity.id)
    assert blocked.status == OpportunityStatus.BLOCKED
    assert failed.failure_reason in blocked.history[-1]["reason"]
    assert reloaded.history(transfer.id)[0].outcome == "PROPOSED"
    assert reloaded.history(transfer.id)[-1].outcome == "FAILED"
    assert reloaded.validate() == []
    with pytest.raises(ValueError, match="original failure"):
        discovery.record_failure(transfer.id, "Rewrite history")


def test_shared_title_is_not_a_transfer_structure(archive):
    source = archive.get("problem-q")
    unrelated_b = Bottleneck(id="b-unrelated", title="Cross-term Lyapunov energy",
                             description="unrelated obstruction", obstruction="unknown",
                             insufficiency="unrelated", structures=[])
    unrelated = PreciseProblem(id="p-unrelated", title="Cross-term Lyapunov energy",
                               statement=source.statement, scope=source.scope,
                               desired_result="something", bottleneck_ids=[unrelated_b.id])
    archive.put_many([unrelated_b, unrelated])
    with pytest.raises(ValueError, match="shared structure"):
        TransferDiscovery(archive).propose("mechanism-cross", unrelated.id)
    assert not any(t.target_problem_id == unrelated.id
                   for t in TransferDiscovery(archive).discover("technique-first", "mechanism-cross"))
    with pytest.raises(ValueError, match="distinct precise problems"):
        TransferDiscovery(archive).propose("mechanism-cross", "problem-p")


def test_modes_validate_seeds_and_breakthrough_attribution(archive):
    discovery = TransferDiscovery(archive)
    transfer = discovery.propose("mechanism-cross", "problem-q")
    with pytest.raises(ValueError, match="retained failed"):
        discovery.discover("failure-first", transfer.id)
    with pytest.raises(TypeError):
        discovery.discover("breakthrough-first", "result-c")
    with pytest.raises(ValueError, match="does not attribute"):
        discovery.propose("mechanism-diagonal", "problem-q", mode="breakthrough-first",
                          breakthrough_id=archive.list("breakthrough")[0].id)


def test_lifecycle_reasons_rejection_history_and_ranking(archive):
    transfer = TransferDiscovery(archive).propose("mechanism-cross", "problem-q")
    portfolio = OpportunityPortfolio(archive)
    opportunity = portfolio.from_transfer(transfer.id)
    assert portfolio.from_transfer(transfer.id) == opportunity
    assert set(opportunity.ranking) == set(DIMENSIONS)
    assert all(x.score is None for x in opportunity.ranking.values())
    assert {"event-posed", "event-partial", "event-result"} <= set(opportunity.event_ids)
    assert opportunity.paper_ids and opportunity.closest_result_ids
    with pytest.raises(ValueError, match="Invalid"):
        portfolio.transition(opportunity.id, "proposal-ready", "skip review")
    with pytest.raises(ValueError, match="reason"):
        portfolio.transition(opportunity.id, "screened", " ")
    with pytest.raises(ValueError, match="attributable evidence"):
        portfolio.assess_dimension(opportunity.id, "novelty", 5, "guessed")
    with pytest.raises(ValueError, match="Unknown"):
        portfolio.rank("aggregate")
    portfolio.assess_dimension(opportunity.id, "falsifiability", 4,
                               "The failure witness supplies an explicit first check",
                               evidence_ids=["evidence-q-failure"])
    portfolio.transition(opportunity.id, "screened", "Literature retrieved")
    portfolio.transition(opportunity.id, "investigating", "Counterexample search planned")
    ready = portfolio.transition(opportunity.id, "proposal-ready", "Obligations and plan documented")
    assert ready.status == OpportunityStatus.PROPOSAL_READY
    assert ready.ranking["novelty"].score is None
    rejected = portfolio.transition(opportunity.id, "rejected", "Counterexample defeats this claim")
    archived = portfolio.transition(opportunity.id, "archived", "Retain negative research record")
    assert archived.rejection_reason == rejected.rejection_reason
    assert any(x.get("to") == "REJECTED" for x in archived.history)
    with pytest.raises(ValueError, match="Invalid"):
        portfolio.transition(opportunity.id, "hypothesis", "erase failure")
    assert len(portfolio.list()) == 1


def test_novelty_compares_exact_scope_and_never_infers_from_absence(archive):
    transfer = TransferDiscovery(archive).propose("mechanism-cross", "problem-q")
    audit = NoveltyAudit(archive).audit(transfer)
    assert not audit.comparable_result_ids
    assert "UNDETERMINED" in audit.assessment
    assert "not evidence of novelty" in audit.uncertainty
    assert {"result-b", "result-c"} <= set(audit.related_result_ids)
    source_result = archive.get("result-c")
    target = archive.get("problem-q")
    result = Result(**{**source_result.model_dump(), "id": "result-target", "revision": 1,
                       "scope": target.scope, "problem_ids": [target.id]})
    archive.put(result)
    report = NoveltyAudit(archive).audit(transfer)
    assert report.comparable_result_ids == [result.id]
    # Equal scope is retrieval evidence; statements may still differ.
    assert "Check statements" in report.assessment
    changed = result.model_copy(update={"id": "result-different-metric", "revision": 1,
                                        "scope": result.scope.model_copy(update={"metric": "different metric"})})
    archive.put(changed)
    assert changed.id not in NoveltyAudit(archive).audit(transfer).comparable_result_ids


def test_external_prior_art_is_optional_attributed_and_failures_visible(archive):
    transfer = TransferDiscovery(archive).propose("mechanism-cross", "problem-q")

    class Adapter:
        def search(self, hypothesis):
            assert hypothesis.id == transfer.id
            return [ExternalPriorArt(title="SYNTHETIC prior-art lead", url="synthetic://lead",
                                     relevance="requires full text comparison", source="fixture")]

    report = NoveltyAudit(archive, Adapter()).audit(transfer)
    assert report.external_searched and not report.external_error
    assert report.external_matches[0].source == "fixture"
    assert "requiring source verification" in report.assessment

    class Broken:
        def search(self, hypothesis):
            raise RuntimeError("provider unavailable")

    report = NoveltyAudit(archive, Broken()).audit(transfer)
    assert "provider unavailable" in report.external_error
    assert "audit is incomplete" in report.assessment
    assert "UNDETERMINED" in report.assessment


def test_failure_missing_evidence_aborts_whole_update(archive):
    discovery = TransferDiscovery(archive)
    transfer = discovery.propose("mechanism-cross", "problem-q")
    mechanism_before = archive.get("mechanism-cross")
    with pytest.raises(ValueError, match="missing references"):
        discovery.record_failure(transfer.id, "reported issue", evidence_ids=["evidence-missing"])
    assert archive.get(transfer.id) == transfer
    assert archive.get("mechanism-cross") == mechanism_before
