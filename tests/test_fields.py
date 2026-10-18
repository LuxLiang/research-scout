"""SYNTHETIC domain fixtures; exercise attribution, revisions and default policy."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from research_scout.cli import app
from research_scout.configuration import WorkspaceConfig
from research_scout.domain.models import Evidence,Paper,PaperVersion,Result,Scope
from research_scout.storage import Archive
from research_scout.workflows.fields import FieldDossiers,ResultNote,result_fingerprint
from research_scout.workflows.weekly import WeeklyCollector,WeeklyProfile


def setup(tmp_path):
    (tmp_path/'config.json').write_text(WorkspaceConfig().model_dump_json())
    archive=Archive(tmp_path/'knowledge')
    scope=Scope(domain='SYNTHETIC',model='Exact test dynamics',objective='Test target',
        assumptions=['Uniform synthetic regularity'],quantifiers=['For every test dimension'],
        metric='W2',guarantee='C h')
    text='SYNTHETIC source, not a real paper.\n'
    digest=sha256(text.encode()).hexdigest()
    for i in (1,2):
        path=tmp_path/f'{i}.txt'
        path.write_text(text)
        archive.put_many([
            Paper(id=f'p{i}',title=f'SYNTHETIC paper {i}',labels=['synthetic-sampling'],
                extraction_status='EXTRACTED',version_ids=[f'v{i}'],published=date(2020+i,1,1),synthetic=True),
            PaperVersion(id=f'v{i}',title='SYNTHETIC version',paper_id=f'p{i}',version='v1',
                coverage='FULL_TEXT',source_path=str(path),text_path=str(path),content_hash=digest,synthetic=True),
            Evidence(id=f'e{i}',title='SYNTHETIC evidence',paper_id=f'p{i}',version_id=f'v{i}',
                locator='char:0-9',quotation=text[:9],coverage='FULL_TEXT',source_hash=digest,synthetic=True),
            Result(id=f'r{i}a',title='Exact synthetic bound',paper_id=f'p{i}',version_id=f'v{i}',
                result_type='THEOREM',statement='Synthetic theorem, no scientific meaning.',scope=scope,
                evidence_ids=[f'e{i}'],rate='O(h)',synthetic=True),
            Result(id=f'r{i}b',title='MC synthetic bound',paper_id=f'p{i}',version_id=f'v{i}',
                result_type='THEOREM',statement='Synthetic noisy theorem.',scope=scope.model_copy(
                    update={'model':'Estimated test dynamics','guarantee':'C h + C/sqrt(M)'}),
                evidence_ids=[f'e{i}'],rate='O(h+1/sqrt(M))',synthetic=True),
        ])
    registry=dict(fields=[dict(id='sampling',title='SYNTHETIC sampling',question='Test question',
        labels=['synthetic-sampling'],branches=[dict(id='exact',title='Exact test branch',
        question='Test exact bounds',match_terms=['Exact']),dict(id='mc',title='Estimated branch',
        question='Test estimated bounds',match_terms=['MC'])]),
        dict(id='cross-domain',title='SYNTHETIC cross domain',question='Test reuse',result_ids=['r1a'])])
    (tmp_path/'fields.json').write_text(json.dumps(registry))
    return archive,registry


def test_result_rows_multifield_reuse_cache_and_source_immutability(tmp_path):
    archive,_=setup(tmp_path)
    before={r.id:r.model_dump() for r in archive.list()}
    worker=FieldDossiers(archive,tmp_path)
    first=worker.update()
    assert [len(r['results']) for r in first]==[4,1]
    cards={c['result_id']:c for c in first[0]['results']}
    assert cards['r1a']['branch_ids']==['exact'] and cards['r1b']['branch_ids']==['mc']
    assert cards['r1a']['details'] is None
    assert first[0]['narrative']['status']=='MISSING'
    assert {r.id:r.model_dump() for r in archive.list()}==before
    assert not archive.list('opportunity')
    again=worker.update()
    assert [r['snapshot_id'] for r in again]==[r['snapshot_id'] for r in first]
    assert not any(r['updated'] for r in again)
    assert not any(r['update_changes']['added'] for r in again)
    assert len(list((tmp_path/'fields/sampling/revisions').glob('*.json')))==1
    md=(tmp_path/'fields/sampling/latest.md').read_text()
    assert 'SYNTHETIC' in md and '完整成本待核读' in md and 'UNASSESSED' in md
    assert (tmp_path/'fields/README.md').exists()


def test_snapshot_chain_preserves_change_reversion_and_membership_removal(tmp_path):
    archive,registry=setup(tmp_path)
    worker=FieldDossiers(archive,tmp_path)
    first=worker.update('sampling')[0]
    result=archive.get('r1a')
    archive.put(result.model_copy(update={'rate':'SYNTHETIC revised rate'}))
    second=worker.update('sampling')[0]
    assert second['changes']['changed']==['r1a']
    archive.put(archive.get('r1a').model_copy(update={'rate':result.rate}))
    third=worker.update('sampling')[0]
    assert third['content_fingerprint']==first['content_fingerprint']
    assert third['snapshot_id']!=first['snapshot_id']
    assert third['previous_snapshot_id']==second['snapshot_id']
    registry['fields'][0].update(labels=[],paper_ids=['p1'])
    (tmp_path/'fields.json').write_text(json.dumps(registry))
    fourth=worker.update('sampling')[0]
    assert fourth['changes']['removed']==['r2a','r2b']
    assert archive.get('r2a').id=='r2a'
    assert len(list((tmp_path/'fields/sampling/revisions').glob('*.json')))==4


def test_source_revision_retains_old_result_and_blocks_setting_comparison(tmp_path):
    archive,_=setup(tmp_path)
    original=archive.get('v1')
    archive.put_many([PaperVersion(id='v1-new',title='SYNTHETIC revised source',paper_id='p1',
        version='v2',coverage='FULL_TEXT',content_hash='new-hash',supersedes_version_id=original.id,synthetic=True),
        archive.get('p1').model_copy(update={'version_ids':['v1','v1-new'],'extraction_status':'NOT_EXTRACTED'})])
    report=FieldDossiers(archive,tmp_path).update('sampling')[0]
    card=next(c for c in report['results'] if c['result_id']=='r1a')
    assert card['version_id']=='v1' and card['warnings']
    assert report['comparisons'][0]['status']=='INSUFFICIENT_INFORMATION'


def test_result_notes_are_own_source_pinned_and_stale_notes_disabled(tmp_path):
    archive,_=setup(tmp_path)
    note=ResultNote(result_id='r1a',result_fingerprint=result_fingerprint(archive.get('r1a')),
        evidence_ids=['e1'],oracle='SYNTHETIC exact oracle',total_cost='SYNTHETIC N calls',
        initialization='SYNTHETIC point',provenance='Synthetic unit-test reading')
    (tmp_path/'result-notes.json').write_text(json.dumps([note.model_dump()]))
    worker=FieldDossiers(archive,tmp_path)
    report=worker.update('sampling')[0]
    assert next(c for c in report['results'] if c['result_id']=='r1a')['details']['total_cost']=='SYNTHETIC N calls'
    assert next(c for c in report['results'] if c['result_id']=='r1b')['details'] is None
    archive.put(archive.get('r1a').model_copy(update={'rate':'SYNTHETIC changed rate'}))
    report=worker.update('sampling')[0]
    c=next(c for c in report['results'] if c['result_id']=='r1a')
    assert c['details'] is None and any('旧结果' in w for w in c['warnings'])
    note.evidence_ids=['e2']
    (tmp_path/'result-notes.json').write_text(json.dumps([note.model_dump()]))
    with pytest.raises(ValueError,match='own paper/version'):
        worker.update()


@pytest.mark.parametrize('change',['path','duplicate','unknown_result','unknown_paper'])
def test_invalid_registry_rejected_before_projection_publication(tmp_path,change):
    archive,registry=setup(tmp_path)
    if change=='path':
        registry['fields'][0]['id']='../unsafe'
    elif change=='duplicate':
        registry['fields'].append(deepcopy(registry['fields'][0]))
    elif change=='unknown_result':
        registry['fields'][1]['result_ids']=['not-a-result']
    else:
        registry['fields'][1]['paper_ids']=['not-a-paper']
    (tmp_path/'fields.json').write_text(json.dumps(registry))
    with pytest.raises(ValueError):
        FieldDossiers(archive,tmp_path).update()
    assert not (tmp_path/'fields').exists()


def test_narrative_source_changes_mark_old_prose_stale(tmp_path):
    archive,_=setup(tmp_path)
    directory=tmp_path/'reports/related-work'
    directory.mkdir(parents=True)
    snapshot={'papers':[p.model_dump(mode='json') for p in archive.list('paper')],
              'records':[r.model_dump(mode='json') for r in archive.list() if r.kind in {'evidence','result','claim'}]}
    (directory/'test.input.json').write_text(json.dumps(snapshot))
    report=dict(input_fingerprint='test',recorded_at='2020-01-01',
        sections=[dict(title='SYNTHETIC related work',paragraphs=[dict(text='Artificial prose.',
            paper_ids=['p1'],evidence_ids=['e1'])])],source_nodes={'p1':{'title':'Synthetic','url':'https://example.org'}},
        missing_foundations=['Synthetic reading priority'],limitations=['SYNTHETIC'])
    (directory/'latest.json').write_text(json.dumps(report))
    worker=FieldDossiers(archive,tmp_path)
    assert worker.update('sampling')[0]['narrative']['status']=='CURRENT'
    archive.put(archive.get('r1a').model_copy(update={'rate':'Synthetic changed rate'}))
    newer=worker.update('sampling')[0]
    assert newer['narrative']['status']=='STALE'
    assert newer['narrative']['sections'][0]['paragraphs'][0]['text']=='Artificial prose.'
    report['sections'][0]['paragraphs'][0]['evidence_ids']=['e2']
    (directory/'latest.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='attributable'):
        worker.update()


def test_fields_cli_operates_without_provider_or_network(tmp_path):
    _,_=setup(tmp_path)
    runner=CliRunner()
    root=['--workspace',str(tmp_path),'fields']
    assert runner.invoke(app,root+['list']).exit_code==0
    result=runner.invoke(app,root+['update','sampling'])
    assert result.exit_code==0,result.output
    assert 'result_count' in result.output
    assert runner.invoke(app,root+['show','sampling','--markdown']).exit_code==0
    assert runner.invoke(app,root+['show','../outside']).exit_code==2
    assert runner.invoke(app,root+['update','unknown']).exit_code==2


def test_weekly_dossiers_update_after_related_work_gaps_are_opt_in(tmp_path,monkeypatch):
    from research_scout.workflows.related_work import RelatedWorkReview
    from research_scout.workflows.gaps import TheoryGapReview
    archive,_=setup(tmp_path)
    order=[]
    monkeypatch.setattr(RelatedWorkReview,'run',lambda self:order.append('related') or {'sections':[]})
    monkeypatch.setattr(TheoryGapReview,'run',lambda *a,**k:pytest.fail('Gaps must be opt-in'))
    real=FieldDossiers.update
    def update(self):
        order.append('fields')
        return real(self)
    monkeypatch.setattr(FieldDossiers,'update',update)
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),
                          arxiv=SimpleNamespace(search=lambda *a,**k:[]))
    profile=WeeklyProfile(name='test',arxiv_queries=['all:test'],related_work_review=True,field_dossiers=True)
    assert not profile.theory_gap_review and not profile.automatic_discovery
    report=worker.run(profile)
    assert not report['errors'] and order==['related','fields']
    assert len(report['field_dossiers']['fields'])==2
    assert '../fields/README.md' in (tmp_path/'reports/latest.md').read_text()


def test_controller_field_mode_extraction_does_not_create_discoveries(tmp_path,monkeypatch):
    from research_scout.workflows.controller import ScoutController
    from research_scout.breakthrough import BreakthroughDiscovery
    archive,_=setup(tmp_path)
    controller=ScoutController(archive,tmp_path/'sources',object())
    processed=SimpleNamespace(records=[archive.get('r1a')])
    controller.pipeline.process=lambda *a,**k:processed
    monkeypatch.setattr(BreakthroughDiscovery,'analyze',lambda *a:pytest.fail('Unexpected discovery'))
    out=controller.process('synthetic',discover=False)
    assert out.processing is processed
    assert not out.opportunity_ids and not archive.list('opportunity')


def test_related_work_does_not_drop_old_papers_after_twenty(tmp_path):
    from research_scout.workflows.related_work import RelatedWorkReview
    from research_scout.workflows.gaps import TheoryGapReview
    archive,_=setup(tmp_path)
    for i in range(3,23):
        archive.put(Paper(id=f'p{i}',title=f'SYNTHETIC historical paper {i}',
                          published=date(2020,1,1),extraction_status='EXTRACTED',synthetic=True))
    assert len(TheoryGapReview(archive,tmp_path,tmp_path/'sources',None)._context()['papers'])==20
    context=RelatedWorkReview(archive,tmp_path,tmp_path/'sources',None)._context()
    assert len(context['papers'])==22
    assert 'All extracted papers' in context['coverage']


def test_weekly_failed_prose_still_publishes_current_result_tables(tmp_path,monkeypatch):
    from research_scout.workflows.related_work import RelatedWorkReview
    archive,_=setup(tmp_path)
    def fail(self):
        raise RuntimeError('Synthetic unavailable writer')
    monkeypatch.setattr(RelatedWorkReview,'run',fail)
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),
                          arxiv=SimpleNamespace(search=lambda *a,**k:[]))
    profile=WeeklyProfile(name='test',arxiv_queries=['all:test'],related_work_review=True,field_dossiers=True)
    report=worker.run(profile)
    assert report['errors'][0]['stage']=='related_work_review'
    assert len(report['field_dossiers']['fields'])==2
    assert len(json.loads((tmp_path/'fields/sampling/latest.json').read_text())['results'])==4
    assert not report.get('theory_gap_review')


def test_weekly_default_passes_discovery_false_to_ingestion(tmp_path):
    from research_scout.discovery import SourcePaper
    archive,_=setup(tmp_path)
    source=SourcePaper(title='SYNTHETIC new source',arxiv_id='2610.12345',version='v1',abstract='Test')
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),
                          arxiv=SimpleNamespace(search=lambda *a,**k:[source]))
    seen=[]
    def process(source,extract,*,discover):
        seen.append(discover)
        return SimpleNamespace(processing=SimpleNamespace(version=SimpleNamespace(coverage=SimpleNamespace(
            value='FULL_TEXT')),records=[]),breakthrough_ids=[],transfer_ids=[],opportunity_ids=[],analysis_errors=[])
    worker.controller.process=process
    report=worker.run(WeeklyProfile(name='test',arxiv_queries=['all:test']))
    assert seen==[False] and not report['errors']
    assert report['articles'][0]['status']=='EXTRACTED'


def test_cli_ingest_discovery_is_explicit_and_refreshes_configured_fields(tmp_path,monkeypatch):
    from research_scout.workflows.controller import ScoutController,DiscoveryOutcome
    from research_scout.extraction import ProcessingOutcome
    from research_scout.ingestion import IngestionOutcome
    archive,_=setup(tmp_path)
    seen=[]
    def process(self,source,extract,*,discover):
        seen.append(discover)
        return DiscoveryOutcome(ProcessingOutcome(IngestionOutcome(archive.get('p1'),archive.get('v1'),False)))
    monkeypatch.setattr(ScoutController,'process',process)
    runner=CliRunner()
    args=['--workspace',str(tmp_path),'ingest','SYNTHETIC','--metadata-only']
    result=runner.invoke(app,args)
    assert result.exit_code==0,result.output
    assert seen==[False] and 'field_dossiers' in json.loads(result.output)
    assert runner.invoke(app,args+['--discover']).exit_code==0
    assert seen==[False,True]


def test_branch_explicit_results_select_members_without_paper_match(tmp_path):
    archive,registry=setup(tmp_path)
    registry['fields']=[dict(id='branch-only',title='Synthetic branch selection',question='Test',
        branches=[dict(id='chosen',title='Chosen result',question='Test',result_ids=['r1a'])])]
    (tmp_path/'fields.json').write_text(json.dumps(registry))
    report=FieldDossiers(archive,tmp_path).update()[0]
    assert [c['result_id'] for c in report['results']]==['r1a']
    assert report['results'][0]['branch_ids']==['chosen']


def test_conservative_evidence_coverage_is_retained_without_promotion(tmp_path):
    archive,_=setup(tmp_path)
    raw=archive.get('e1').model_dump(mode='json')
    archive.put(Evidence.model_validate(dict(raw,id='e1-partial',coverage='PARTIAL_TEXT')))
    archive.put(archive.get('r1a').model_copy(update={'evidence_ids':['e1-partial']}))
    report=FieldDossiers(archive,tmp_path).update('sampling')[0]
    card=next(c for c in report['results'] if c['result_id']=='r1a')
    assert card['evidence'][0]['coverage']=='PARTIAL_TEXT'
    assert card['warnings'] and card['coverage']=='FULL_TEXT'
    archive.put(Evidence.model_validate(dict(raw,id='e1-abstract',coverage='ABSTRACT_ONLY')))
    archive.put(archive.get('r1a').model_copy(update={'evidence_ids':['e1-abstract']}))
    report=FieldDossiers(archive,tmp_path).update('sampling')[0]
    assert next(c for c in report['results'] if c['result_id']=='r1a')['source_status']=='METADATA_ONLY'


def test_cross_field_narrative_dependency_changes_are_stale(tmp_path):
    archive,registry=setup(tmp_path)
    registry['fields']=[dict(id='only-one',title='Test cross-field support',question='Test',paper_ids=['p1'])]
    (tmp_path/'fields.json').write_text(json.dumps(registry))
    directory=tmp_path/'reports/related-work'
    directory.mkdir(parents=True)
    snapshot={'papers':[p.model_dump(mode='json') for p in archive.list('paper')],
              'records':[r.model_dump(mode='json') for r in archive.list() if r.kind in {'evidence','result'}]}
    (directory/'test.input.json').write_text(json.dumps(snapshot))
    report=dict(input_fingerprint='test',recorded_at='2020-01-01',
        sections=[dict(title='SYNTHETIC cross comparison',paragraphs=[dict(text='Artificial cross-field prose.',
            paper_ids=['p1','p2'],evidence_ids=['e1','e2'])])],
        source_nodes={f'p{i}':{'title':f'Synthetic {i}','url':'https://example.org'} for i in (1,2)},
        missing_foundations=[],limitations=['SYNTHETIC'])
    (directory/'latest.json').write_text(json.dumps(report))
    worker=FieldDossiers(archive,tmp_path)
    assert worker.update()[0]['narrative']['status']=='CURRENT'
    archive.put(archive.get('r2a').model_copy(update={'rate':'SYNTHETIC cross-field change'}))
    assert worker.update()[0]['narrative']['status']=='STALE'


def test_interrupted_publication_reuses_immutable_retained_snapshot(tmp_path,monkeypatch):
    import research_scout.workflows.fields as module
    archive,_=setup(tmp_path)
    original=module._atomic_json
    interrupted=[]
    def write(path,payload):
        if path.name=='latest.json' and not interrupted:
            interrupted.append(True)
            raise OSError('SYNTHETIC interruption before latest pointer')
        return original(path,payload)
    monkeypatch.setattr(module,'_atomic_json',write)
    worker=FieldDossiers(archive,tmp_path)
    with pytest.raises(OSError,match='interruption'):
        worker.update('sampling')
    retained=next((tmp_path/'fields/sampling/revisions').glob('*.json'))
    before=retained.read_bytes()
    saved=json.loads(before)
    report=worker.update('sampling')[0]
    assert report['recorded_at']==saved['recorded_at']
    assert retained.read_bytes()==before
