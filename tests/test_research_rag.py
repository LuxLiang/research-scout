"""ARTIFICIAL sources verify retrieval-to-grounding, not mathematical correctness."""
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from research_scout.cli import app
from research_scout.configuration import WorkspaceConfig
from research_scout.workflows.transfer_review import TransferReview
from test_transfer_review import Model, setup


class RereadingModel(Model):
    def __init__(self, ideas):
        super().__init__(ideas)
        self.contexts = []

    def run_structured(self, prompt, schema):
        if prompt.startswith('Ground these unverified'):
            self.grounding_calls += 1
            windows = json.loads(prompt.split('\nRetrieved original source windows:\n')[1].split(
                '\nSource bibliography:\n')[0])
            assert any('ARTIFICIAL additional finite-fourth-moment condition' in p['parent_text']
                       for p in windows)
            assert {p['version_id'] for p in windows} == {'version:1', 'version:2'}
            batch = json.loads(prompt.split('\nCandidates:\n')[1].split(
                '\nOriginal source records and evidence:\n')[0])
            batch['ideas'][0]['missing_lemmas'].append('ARTIFICIAL verify finite fourth moment at target')
            batch['ideas'][0]['source_passage_ids'] = [p['id'] for p in windows]
            return {'batch_json': json.dumps(batch)}
        self.contexts.append(json.loads(prompt.split('\nContext:\n')[1]))
        return super().run_structured(prompt, schema)


def test_original_source_rereading_refines_candidate_and_retains_full_inventory(tmp_path):
    archive, idea = setup(tmp_path)
    path = Path(archive.get('version:1').text_path)
    path.write_text(path.read_text() + '\nARTIFICIAL additional finite-fourth-moment condition for Test only.')
    model = RereadingModel([idea])
    worker = TransferReview(archive, tmp_path, tmp_path/'sources', model)
    original_ids = {r['id'] for r in worker._context()['records']}
    report = worker.run(focus_paper_ids=['paper:1'])
    assert {r['id'] for r in model.contexts[0]['records']} == original_ids
    assert model.contexts[0]['retrieval']['inventory_preserved']
    assert model.grounding_calls == 1
    assert report['retrieval']['candidate_reread']['original_source_grounding']
    assert 'ARTIFICIAL verify finite fourth moment at target' in report['ideas'][0]['missing_lemmas']
    assert report['ideas'][0]['source_passage_ids']
    assert worker.run(focus_paper_ids=['paper:1']) == report
    assert model.calls == 1 and model.grounding_calls == 1
    # A changed, previously unextracted proof paragraph invalidates the review cache.
    path.write_text(path.read_text() + '\nARTIFICIAL changed proof context.')
    changed = worker.run(focus_paper_ids=['paper:1'])
    assert changed['input_fingerprint'] != report['input_fingerprint']
    assert model.calls == 2 and model.grounding_calls == 2
    assert not archive.list('transfer') and not archive.list('opportunity')


def test_model_cannot_invent_reread_source_passage(tmp_path):
    archive, idea = setup(tmp_path)
    class Invented(Model):
        def run_structured(self, prompt, schema):
            raw = super().run_structured(prompt, schema)
            if prompt.startswith('Ground these unverified'):
                batch = json.loads(raw['batch_json'])
                batch['ideas'][0]['source_passage_ids'] = ['fabricated-passage']
                return {'batch_json': json.dumps(batch)}
            return raw
    with pytest.raises(ValueError, match='unseen source passages'):
        TransferReview(archive, tmp_path, tmp_path/'sources', Invented([idea])).run()
    assert not (tmp_path/'reports'/'transfers'/'latest.json').exists()


def test_rag_cli_indexes_sources_without_model_and_filters_before_limit(tmp_path):
    archive, _ = setup(tmp_path)
    (tmp_path/'config.json').write_text(WorkspaceConfig().model_dump_json())
    runner = CliRunner()
    response = runner.invoke(app, ['--workspace', str(tmp_path), 'index', 'retrieve',
                                  'UNIT TEST', '--paper-id', 'paper:2', '--top-k', '1'])
    assert response.exit_code == 0, response.output
    result = json.loads(response.stdout)
    assert result['source_index']['indexed_versions'] == 2
    assert [p['paper_id'] for p in result['source_passages']] == ['paper:2']
    assert result['source_passages'][0]['coverage'] == 'FULL_TEXT'
    assert not archive.list('opportunity')


def test_rag_cli_eval_is_explicitly_synthetic_and_offline():
    response = CliRunner().invoke(app, ['index', 'eval'])
    assert response.exit_code == 0, response.output
    result = json.loads(response.stdout)
    assert result['errors'] == []
    assert 'SYNTHETIC' in result['fixture_qualification']
