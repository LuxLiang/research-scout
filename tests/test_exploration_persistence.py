"""SYNTHETIC exploration records test persistence gates, not research validity."""
import pytest

from research_scout.domain.models import (
    AssessmentStatus, Mechanism, Opportunity, PreciseProblem, Scope, TransferHypothesis,
)
from research_scout.storage import Archive, IntegrityError


@pytest.fixture
def archive(tmp_path):
    archive = Archive(tmp_path / "SYNTHETIC-exploration")
    scope = Scope(domain="SYNTHETIC sampling", model="diffusion", objective="mixing",
                  metric="distance", guarantee="convergence")
    archive.put_many([
        PreciseProblem(id="source", title="SYNTHETIC source", statement="Source objective",
                       scope=scope, desired_result="mixing", synthetic=True),
        PreciseProblem(id="target", title="SYNTHETIC target", statement="Old open objective",
                       scope=scope, desired_result="faster mixing", synthetic=True),
        Mechanism(id="technique", title="SYNTHETIC technique", principle="Smoothed estimate",
                  synthetic=True),
    ])
    return archive


def lead(**updates):
    data = dict(
        id="lead", title="SYNTHETIC possible use", mode="TECHNIQUE_FIRST",
        maturity="EXPLORATORY_LEAD", source_problem_id="source",
        target_problem_id="target", source_mechanism_id="technique",
        shared_structures=["diffusion"], structural_differences=["noise may be degenerate"],
        required_assumptions=[], missing_lemmas=[], likely_counterexamples=[],
        proposed_result="Explore a stronger distance estimate",
        first_falsification_test="Check the source estimate in a degenerate toy model",
        uncertainty="No proof route or bottleneck has been identified",
        match_basis=["Shared diffusion structure"],
        next_action="Inspect whether the smoothing estimate tolerates degenerate noise", synthetic=True,
    )
    return TransferHypothesis(**(data | updates))


def opportunity(transfer_id="lead"):
    return Opportunity(
        id="opportunity", title="SYNTHETIC imported opportunity", target_problem_id="target",
        bottleneck_ids=[], mechanism_ids=["technique"], transfer_id=transfer_id,
        contribution="Improve the estimate", assumptions=[], proof_obligations=["Bridge estimate"],
        counterexamples=[], first_validation="Toy model", significance="Unknown",
        novelty_assessment="UNDETERMINED", uncertainty="Unproved", synthetic=True,
    )


def test_unknown_bottlenecks_roundtrip_without_fabricating_entities(archive):
    saved = archive.put(lead())
    reopened = Archive(archive.root)
    retained = reopened.get(saved.id)
    assert retained.source_bottleneck_id is None
    assert retained.target_bottleneck_id is None
    assert retained.maturity == "EXPLORATORY_LEAD"
    assert retained.match_basis == ["Shared diffusion structure"]
    assert not reopened.list("bottleneck")
    assert reopened.get("target").bottleneck_ids == []
    assert reopened.validate() == []
    assert reopened.rebuild() == 4


def test_claimed_unknown_bottleneck_still_requires_a_real_reference(archive):
    with pytest.raises(IntegrityError, match="missing references"):
        archive.put(lead(target_bottleneck_id="invented-obstruction"))
    assert not archive.list("transfer")
    assert not archive.list("bottleneck")


def test_raw_opportunity_import_cannot_bypass_exploration_gate(archive):
    # Atomic imports must check the proposed snapshot, regardless of batch order.
    with pytest.raises(IntegrityError, match="exploratory leads cannot become opportunities"):
        archive.put_many([opportunity(), lead()])
    assert not archive.list("transfer")
    archive.put(lead())
    with pytest.raises(IntegrityError, match="exploratory leads cannot become opportunities"):
        archive.put(opportunity())
    assert not archive.list("opportunity")


def test_existing_opportunity_prevents_demoting_its_transfer_to_a_lead(archive):
    hypothesis = archive.put(lead(maturity="TRANSFER_HYPOTHESIS",
                                  adaptation="Replace the smoothing step",
                                  bridge_statement="Show the degenerate estimate remains bounded",
                                  next_action="Prove the toy estimate"))
    archive.put(opportunity())
    with pytest.raises(IntegrityError, match="exploratory leads cannot become opportunities"):
        archive.put(hypothesis.model_copy(update={"maturity": "EXPLORATORY_LEAD"}))
    assert archive.get(hypothesis.id).maturity == "TRANSFER_HYPOTHESIS"


@pytest.mark.parametrize("promotion", [
    {"outcome": "SUPPORTED"},
    {"assessment_status": AssessmentStatus.SUPPORTED_BY_SOURCE},
])
def test_lead_cannot_claim_scientific_support(archive, promotion):
    # model_copy deliberately mimics callers attempting to skip assignment validation.
    with pytest.raises(ValueError, match="(?i)(exploratory|lead)"):
        archive.put(lead().model_copy(update=promotion))
    assert not archive.list("transfer")


def test_failed_lead_keeps_reason_and_revisit_conditions(archive):
    failed = archive.put(lead(outcome="FAILED", failure_reason="Tool needs nondegenerate noise",
                              revisit_when=["A degenerate covariance estimate becomes available"]))
    reopened = Archive(archive.root)
    retained = reopened.get(failed.id)
    assert retained.failure_reason == "Tool needs nondegenerate noise"
    assert retained.revisit_when == ["A degenerate covariance estimate becomes available"]
    with pytest.raises(IntegrityError, match="revisit conditions must be retained"):
        reopened.put(retained.model_copy(update={"revisit_when": []}))
    with pytest.raises(IntegrityError, match="failed transfer reasons are retained"):
        reopened.put(retained.model_copy(update={"failure_reason": "Different diagnosis"}))
    with pytest.raises(IntegrityError, match="failed transfer reasons are retained"):
        reopened.put(retained.model_copy(update={"outcome": "PROPOSED"}))
    expanded = reopened.put(retained.model_copy(update={"revisit_when": retained.revisit_when + [
        "A reduction to nondegenerate noise is established",
    ]}))
    assert len(expanded.revisit_when) == 2
    assert reopened.history(failed.id)[0].revisit_when == retained.revisit_when
    assert reopened.validate() == []
