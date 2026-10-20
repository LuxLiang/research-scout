"""Explicit synthetic orchestration checks for unknown-difficulty exploration."""
from types import SimpleNamespace

from research_scout.domain.models import PreciseProblem
from research_scout.opportunities import OpportunityPortfolio
from research_scout.storage import Archive
from research_scout.workflows.controller import ScoutController
from research_scout.workflows.demo import import_history


def test_new_technique_explores_without_breakthrough_or_known_target_bottleneck(tmp_path, monkeypatch):
    archive = Archive(tmp_path / 'knowledge')
    import_history(archive)
    source = archive.get('problem-p')
    target = PreciseProblem(
        id='problem-unknown-difficulty', title='SYNTHETIC unknown difficulty', synthetic=True,
        statement='SYNTHETIC related state-decay question with an unknown proof route',
        scope=source.scope, desired_result='SYNTHETIC obtain the full-state decay bound',
        structures=source.structures, evidence_ids=source.evidence_ids,
        open_questions=['Can a different energy construction improve the bound?'],
    )
    archive.put(target)
    controller = ScoutController(archive, tmp_path / 'cache')
    monkeypatch.setattr(controller.pipeline, 'process', lambda *args, **kwargs:
                        SimpleNamespace(records=[archive.get('result-c')]))

    def unavailable(*args, **kwargs):
        raise ValueError('SYNTHETIC breakthrough assessment inconclusive')

    monkeypatch.setattr('research_scout.workflows.controller.BreakthroughDiscovery.analyze', unavailable)
    output = controller.process('SYNTHETIC source already extracted')
    leads = [archive.get(t) for t in output.transfer_ids
             if archive.get(t).target_problem_id == target.id]
    assert len(leads) == 1
    assert leads[0].maturity == 'EXPLORATORY_LEAD'
    assert leads[0].target_bottleneck_id is None
    assert leads[0].match_basis and leads[0].next_action
    assert output.analysis_errors  # Failure remains visible, but does not block exploration.
    assert not any(archive.get(o).target_problem_id == target.id for o in output.opportunity_ids)
    assert archive.get(target.id).bottleneck_ids == []
    assert archive.validate() == []
    import pytest
    with pytest.raises(ValueError, match='Exploratory leads'):
        OpportunityPortfolio(archive).from_transfer(leads[0].id)


def test_discovery_disabled_keeps_ingestion_only_behavior(tmp_path, monkeypatch):
    archive = Archive(tmp_path / 'knowledge')
    import_history(archive)
    controller = ScoutController(archive, tmp_path / 'cache')
    monkeypatch.setattr(controller.pipeline, 'process', lambda *args, **kwargs:
                        SimpleNamespace(records=[archive.get('result-c')]))
    output = controller.process('SYNTHETIC source', discover=False)
    assert output.transfer_ids == []
    assert output.opportunity_ids == []
    assert archive.list('transfer') == []
