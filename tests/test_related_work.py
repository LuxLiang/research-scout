"""Artificial related-work sources: references are evidence, chronology is not."""
from datetime import date
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from research_scout.discovery import SourcePaper
from research_scout.domain.models import Evidence, Paper, PaperVersion
from research_scout.storage import Archive
from research_scout.workflows.gaps import TheoryGapReview
from research_scout.workflows.related_work import RelatedWorkReview


def setup(tmp_path):
    archive = Archive(tmp_path/'knowledge')
    for i, title in enumerate(['Unit Test Related One','Unit Test Related Two'],1):
        text = 'UNIT TEST SOURCE.\nReferences\nAuthor. Unit Test Related One. 2020.\n'
        path = tmp_path/f'{i}.txt'
        path.write_text(text)
        digest = sha256(text.encode()).hexdigest()
        archive.put_many([
            Paper(id=f'paper:{i}',title=title,published=date(2020+i,1,1),
                  extraction_status='EXTRACTED',version_ids=[f'version:{i}']),
            PaperVersion(id=f'version:{i}',title='Artificial test source',paper_id=f'paper:{i}',
                version='v1',coverage='FULL_TEXT',text_path=str(path),content_hash=digest),
            Evidence(id=f'evidence:{i}',title='Artificial test evidence',paper_id=f'paper:{i}',
                version_id=f'version:{i}',locator='char:0-16',quotation=text[:16],
                coverage='FULL_TEXT',source_hash=digest),
        ])
    draft = dict(sections=[dict(title='Unit test development track',motivating_question='Test only',
        paragraphs=[dict(text='Artificial supported comparison.',paper_ids=['paper:1','paper:2'],
                         evidence_ids=['evidence:1','evidence:2'])])],
        matrix=[dict(paper_id=f'paper:{i}',assumptions='Test assumptions',metric='Test metric',
            guarantee='Artificial guarantee',oracle_and_cost='Test oracle cost',initialization='Test point',
            proof_mechanism='Test proof idea',remaining_boundary='Unresolved test case',
            evidence_ids=[f'evidence:{i}']) for i in (1,2)],
        relations=[],synthesis=[dict(text='Unit test synthesis',paper_ids=['paper:1'],
            evidence_ids=['evidence:1'])],missing_foundations=['Read the full foundational source'],
        limitations=['Artificial unit-test data; no scientific conclusions'])
    return archive, draft


class Model:
    def __init__(self,draft):
        self.draft,self.calls=draft,0

    def run_structured(self,prompt,schema):
        assert 'Time order is not technical' in prompt
        assert 'untrusted data' in prompt and schema['additionalProperties'] is False
        self.calls += 1
        return {'draft_json':json.dumps(self.draft)}


def test_connected_prose_matrix_cache_and_downstream_context(tmp_path):
    archive,draft=setup(tmp_path)
    model=Model(draft)
    worker=RelatedWorkReview(archive,tmp_path,tmp_path/'sources',model)
    original=worker.run()
    assert worker.run()==original and model.calls==1
    gap=TheoryGapReview(archive,tmp_path,tmp_path/'sources',model)
    assert 'related_work' in gap._context()
    assert 'related_work' not in gap._context(include_related_work=False)
    assert '跨论文比较表' in (tmp_path/'reports/related-work/latest.md').read_text()
    assert not archive.list('opportunity')  # Writing history cannot manufacture a gap.


def test_documented_citation_is_anchored_to_actual_bibliography(tmp_path):
    archive,draft=setup(tmp_path)
    worker=RelatedWorkReview(archive,tmp_path,tmp_path/'sources',Model(draft))
    observations=worker._context()['citation_observations']
    observed=next(o for o in observations if o['citing_paper_id']=='paper:2')
    version=archive.get(observed['version_id'])
    start,end=map(int,observed['locator'].removeprefix('char:').split('-'))
    from pathlib import Path
    assert Path(version.text_path).read_text()[start:end]==observed['quotation']
    draft['relations']=[dict(earlier_id='paper:1',later_id='paper:2',
        relation_type='DOCUMENTED_CITATION',technical_difference='Only a documented reference, not an improvement',
        evidence_ids=['evidence:1','evidence:2'],citation_observation_ids=[observed['id']])]
    assert worker.run()['relations'][0]['relation_type']=='DOCUMENTED_CITATION'


@pytest.mark.parametrize('relation_type,observation',[
    ('DOCUMENTED_CITATION',[]),('DOCUMENTED_CITATION',['citation:invented']),('PROVED_IMPROVEMENT',[]),
])
def test_time_order_cannot_create_citation_or_proved_improvement(tmp_path,relation_type,observation):
    archive,draft=setup(tmp_path)
    draft['relations']=[dict(earlier_id='paper:1',later_id='paper:2',relation_type=relation_type,
        technical_difference='A claim requiring support',evidence_ids=['evidence:1','evidence:2'],
        citation_observation_ids=observation)]
    with pytest.raises(ValueError):
        RelatedWorkReview(archive,tmp_path,tmp_path/'sources',Model(draft)).run()
    assert not (tmp_path/'reports/related-work/latest.json').exists()


@pytest.mark.parametrize('change',['unknown_paper','unknown_evidence','wrong_owner','missing_matrix_row'])
def test_unattributable_or_incomplete_comparison_rejected(tmp_path,change):
    archive,draft=setup(tmp_path)
    p=draft['sections'][0]['paragraphs'][0]
    if change=='unknown_paper':
        p['paper_ids']=['missing']
    elif change=='unknown_evidence':
        p['evidence_ids']=['missing']
    elif change=='wrong_owner':
        p['evidence_ids']=['evidence:1']
    else:
        draft['matrix']=draft['matrix'][:1]
    with pytest.raises(ValueError):
        RelatedWorkReview(archive,tmp_path,tmp_path/'sources',Model(draft)).run()


def test_foundation_metadata_cannot_promote_itself_to_full_text(tmp_path):
    archive,draft=setup(tmp_path)
    foundation=SourcePaper(title='Unit Test Foundation Source',arxiv_id='1901.12345',
                          abstract='Artificial foundation abstract',coverage='FULL_TEXT')
    (tmp_path/'related-work-foundations.json').write_text(json.dumps([foundation.model_dump(mode='json')]))
    draft['sections'][0]['paragraphs'].append(dict(text='Abstract-level historical motivation.',
        paper_ids=['external:1901.12345'],evidence_ids=[]))
    report=RelatedWorkReview(archive,tmp_path,tmp_path/'sources',Model(draft)).run()
    assert report['source_nodes']['external:1901.12345']['coverage']=='ABSTRACT_ONLY'


def test_related_foundation_reference_is_available_to_downstream_exclusions(tmp_path):
    from research_scout.workflows.gaps import GapBatch, ExcludedIdea
    archive,draft=setup(tmp_path)
    foundation=SourcePaper(title='Unit Test Foundation Source',arxiv_id='1901.12345',abstract='Unit test abstract')
    (tmp_path/'related-work-foundations.json').write_text(json.dumps([foundation.model_dump(mode='json')]))
    RelatedWorkReview(archive,tmp_path,tmp_path/'sources',Model(draft)).run()
    worker=TheoryGapReview(archive,tmp_path,tmp_path/'sources',object())
    batch=GapBatch(proposals=[],excluded_ideas=[ExcludedIdea(idea='Known question',reason='Related foundation',
        prior_art_urls=['https://arxiv.org/abs/1901.12345'])])
    worker._validate(batch,worker._context())


def test_weekly_history_runs_before_gaps_and_failure_blocks_gap_generation(tmp_path,monkeypatch):
    from research_scout.workflows.weekly import WeeklyCollector,WeeklyProfile
    archive,_=setup(tmp_path)
    order=[]
    monkeypatch.setattr(RelatedWorkReview,'run',lambda self:order.append('history') or {'sections':[{}]})
    monkeypatch.setattr(TheoryGapReview,'run',lambda self,n:order.append('gaps') or {'cards':[]})
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),
                          arxiv=SimpleNamespace(search=lambda *a,**k:[]))
    profile=WeeklyProfile(name='test',arxiv_queries=['all:test'],related_work_review=True,theory_gap_review=True)
    report=worker.run(profile)
    assert order==['history','gaps'] and report['related_work_review']['track_count']==1
    assert 'related-work/latest.md' in (tmp_path/'reports/latest.md').read_text()
    order.clear()
    def fail(self):
        raise RuntimeError('History unavailable')
    monkeypatch.setattr(RelatedWorkReview,'run',fail)
    report=worker.run(profile)
    assert not order and report['errors'][0]['stage']=='related_work_review'
    assert not report.get('theory_gap_review')
