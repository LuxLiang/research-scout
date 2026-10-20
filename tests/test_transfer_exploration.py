"""SYNTHETIC scientific gates for exploration with unknown research obstacles."""
import pytest

from research_scout.domain.models import Application, Mechanism, PreciseProblem, Scope
from research_scout.storage import Archive
from research_scout.transfer import TransferDiscovery


def setup_archive(tmp_path, *, structures=True):
    archive = Archive(tmp_path / "synthetic-exploration")
    scope = Scope(domain="SYNTHETIC stochastic analysis", model="coupled kinetic diffusion",
                  objective="uniform relaxation bound", metric="weighted transport distance",
                  guarantee="exponential relaxation")
    source = PreciseProblem(id="source", title="SYNTHETIC source", statement="Source statement",
                            scope=scope, desired_result="Uniform decay",
                            structures=["degenerate covariance"] if structures else [], synthetic=True)
    target = PreciseProblem(id="target", title="SYNTHETIC target", statement="Target statement",
                            scope=scope.model_copy(update={"model": "delayed particle process",
                                                           "objective": "particle approximation bound",
                                                           "metric": "weak test function error"}),
                            desired_result="Uniform particle approximation",
                            structures=["degenerate covariance"] if structures else [], synthetic=True)
    mechanism = Mechanism(id="tool", title="SYNTHETIC tool", principle="Conditional smoothing",
                          structures=["degenerate covariance"] if structures else [], synthetic=True)
    application = Application(id="application", title="SYNTHETIC application",
                              scope=scope, problem_id=source.id, mechanism_id=mechanism.id, synthetic=True)
    archive.put_many([source, target, mechanism, application])
    return archive


def test_unknown_bottlenecks_produce_retained_exploration_not_a_fabricated_plan(tmp_path):
    archive = setup_archive(tmp_path)
    discovery = TransferDiscovery(archive)
    lead = discovery.propose("tool", "target")
    assert lead.source_bottleneck_id is None and lead.target_bottleneck_id is None
    assert lead.maturity == "EXPLORATORY_LEAD"
    assert lead.match_basis == ["Explicit shared structure: degenerate covariance"]
    assert not lead.bridge_statement and not lead.adaptation
    assert lead.missing_lemmas == [] and lead.first_falsification_test == ''
    assert "locate a possible use" in lead.next_action
    assert "not established" in lead.uncertainty
    assert archive.list("bottleneck") == []
    assert archive.list("opportunity") == []
    assert discovery.discover("technique-first", "tool") == [lead]
    assert Archive(archive.root).get(lead.id) == lead
    assert archive.validate() == []


def test_two_specific_scope_dimensions_can_retrieve_without_structure(tmp_path):
    archive = setup_archive(tmp_path, structures=False)
    source, target = archive.get("source"), archive.get("target")
    archive.put(target.model_copy(update={"scope": source.scope.model_copy(update={"model": "new process"})}))
    lead = TransferDiscovery(archive).propose("tool", "target")
    assert lead.shared_structures == []
    assert len(lead.match_basis) == 2
    assert any("objective" in basis for basis in lead.match_basis)
    assert any("metric" in basis for basis in lead.match_basis)
    assert lead.maturity == "EXPLORATORY_LEAD"


def test_archived_proof_role_can_retrieve_a_target_proof_step(tmp_path):
    archive = setup_archive(tmp_path, structures=False)
    tool, target = archive.get("tool"), archive.get("target")
    archive.put(tool.model_copy(update={"proof_role": "control the conditional smoothing error"}))
    archive.put(target.model_copy(update={"unresolved_scope": [
        "Need to control the conditional smoothing error uniformly in particle count"]}))
    lead = TransferDiscovery(archive).propose("tool", "target")
    assert lead.maturity == "EXPLORATORY_LEAD"
    assert any("proof role" in basis for basis in lead.match_basis)


def test_generic_text_titles_and_a_single_shared_metric_do_not_admit_all_pairs(tmp_path):
    archive = setup_archive(tmp_path, structures=False)
    source, target = archive.get("source"), archive.get("target")
    archive.put(target.model_copy(update={"title": source.title, "statement": source.statement,
                                         "scope": target.scope.model_copy(update={"metric": source.scope.metric})}))
    discovery = TransferDiscovery(archive)
    with pytest.raises(ValueError, match="shared structure"):
        discovery.propose("tool", "target")
    assert discovery.discover("technique-first", "tool") == []
    for identifier in ("source", "target"):
        problem = archive.get(identifier)
        archive.put(problem.model_copy(update={"scope": problem.scope.model_copy(update={
            "model": "not specified", "objective": "not known", "metric": "to be determined"})}))
    assert discovery.discover("technique-first", "tool") == []


def test_failure_of_exploration_retains_revisit_conditions_without_creating_bottlenecks(tmp_path):
    archive = setup_archive(tmp_path)
    discovery = TransferDiscovery(archive)
    lead = discovery.propose("tool", "target")
    failed = discovery.record_failure(lead.id, "Tool needs independent increments",
                                      revisit_when=["A correlated-increment version becomes available"])
    assert failed.outcome == "FAILED"
    assert failed.revisit_when == ["A correlated-increment version becomes available"]
    assert archive.get("tool").attempts[-1].reason == failed.failure_reason
    assert archive.list("bottleneck") == []
    assert TransferDiscovery(Archive(archive.root)).propose("tool", "target") == failed
    retry = discovery.discover("failure-first", failed.id)[0]
    assert retry.previous_transfer_id == failed.id
    assert retry.revisit_when == failed.revisit_when
    assert any(failed.revisit_when[0] in lemma for lemma in retry.missing_lemmas)
    assert failed.failure_reason in retry.next_action
    assert retry.first_falsification_test == ''
    assert retry.maturity == "EXPLORATORY_LEAD"
    assert archive.validate() == []
