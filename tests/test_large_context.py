"""Artificial fixtures exercise complete window coverage and original-source grounding."""
import json
from copy import deepcopy

import pytest

from research_scout.workflows.large_context import LargeContextReview, alias_identifiers, replace_strings
from research_scout.workflows.transfer_review import TransferIdeas
from test_transfer_review import field_context


class DigestModel:
    def __init__(self, failure=None):
        self.calls=[]
        self.failure=failure

    def run_structured(self,prompt,schema):
        self.calls.append(prompt)
        window=json.loads(prompt.split('\nEvidence passages:\n')[1])
        ids=[r['id'] for r in window]
        if self.failure=='missing':
            ids=ids[:-1]
        if self.failure=='duplicate':
            ids+=ids[:1]
        if self.failure=='invented':
            ids[0]='invented'
        return {'digests_json':json.dumps(dict(summaries=[dict(evidence_id=e,
            summary='ARTIFICIAL UNIT-TEST READING NOTE') for e in ids],limitations=['Artificial only']))}


def test_aliases_roundtrip_and_literal_collision_avoidance():
    original={'id':'paper-very-long-canonical-identifier','result_ids':['result-very-long-canonical-identifier'],
              'title':'ID0','source_field_id':'a-short-field','nested':{'unknown':None}}
    encoded,reverse=alias_identifiers(original)
    assert replace_strings(encoded,reverse)==original
    assert 'ID0' not in reverse
    assert encoded['title']=='ID0'


def test_windowed_reading_retains_every_source_and_scientific_scope(tmp_path,monkeypatch):
    import research_scout.workflows.large_context as module
    worker,context,_,_=field_context(tmp_path)
    original=deepcopy(context)
    records=[r for r in context['records'] if r['kind']=='evidence']
    budget=max(len(json.dumps([r],ensure_ascii=False)) for r in records)+10
    monkeypatch.setattr(module,'EVIDENCE_WINDOW_BUDGET',budget)
    directory=tmp_path/'windows'
    directory.mkdir()
    model=DigestModel()
    reader=LargeContextReview(model,directory,'artificial-test')
    encoded,reverse=reader.prepare(context)
    restored=replace_strings(encoded,reverse)
    assert reader.summary_windows==2 and len(model.calls)==2
    assert context==original
    assert {r['id'] for r in restored['records']}=={r['id'] for r in context['records']}
    for r in restored['records']:
        original=next(o for o in context['records'] if o['id']==r['id'])
        if r['kind']=='evidence':
            assert 'quotation' not in r and r['model_passage_summary']=='ARTIFICIAL UNIT-TEST READING NOTE'
            assert r['locator']==original['locator']
        if r['kind']=='result':
            assert r['scope']=={k:v for k,v in original['scope'].items() if v not in (None,[],{})}
    reader.prepare(context)
    assert len(model.calls)==2  # Validated reading windows are reusable.


@pytest.mark.parametrize('failure',['missing','duplicate','invented'])
def test_incomplete_or_invented_passage_coverage_rejected(tmp_path,failure):
    _,context,_,_=field_context(tmp_path)
    directory=tmp_path/'windows'
    directory.mkdir()
    with pytest.raises(ValueError,match='every supplied passage'):
        LargeContextReview(DigestModel(failure),directory,'artificial-test').prepare(context)
    assert not (directory/'artificial-test.synthesis-input.json').exists()


def test_grounding_receives_original_quotes_and_cannot_add_unseen_ids(tmp_path):
    _,context,idea,pair=field_context(tmp_path)
    batch=TransferIdeas(ideas=[idea],field_pair_reviews=[pair],limitations=['Artificial only'])
    raw={'batch_json':batch.model_dump_json()}
    class Grounding:
        def run_structured(self,prompt,schema):
            assert 'UNIT TEST SOURCE EVIDENCE' in prompt
            assert 'not original quotations' not in prompt
            result=json.loads(raw['batch_json'])
            result['ideas'][0]['evidence_ids'].append('invented')
            return {'batch_json':json.dumps(result)}
    with pytest.raises(ValueError,match='unseen records'):
        LargeContextReview(Grounding(),tmp_path,'artificial-test').ground(raw,context,TransferIdeas.model_json_schema())


def test_alias_output_restoration_before_scientific_validation():
    context={'id':'result-long-canonical-identifier','evidence_ids':['evidence-long-canonical-identifier']}
    encoded,reverse=alias_identifiers(context)
    raw={'batch_json':json.dumps(dict(ideas=[dict(source_result_id=encoded['id'],evidence_ids=encoded['evidence_ids'])]))}
    restored=json.loads(LargeContextReview.restore(raw,reverse)['batch_json'])
    assert restored['ideas'][0]['source_result_id']==context['id']
    assert restored['ideas'][0]['evidence_ids']==context['evidence_ids']
