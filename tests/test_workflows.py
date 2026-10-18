"""End-to-end tests use explicitly fictional science and genuine archive APIs."""
from pathlib import Path
import json

from typer.testing import CliRunner

from research_scout.cli import app
from research_scout.storage import Archive
from research_scout.workflows.demo import run_demo
from research_scout.workflows.evaluation import run_evaluation


def test_full_offline_workflow_and_idempotence(tmp_path):
    archive=Archive(tmp_path/'knowledge')
    report=run_demo(archive,tmp_path/'proposal.md')
    assert report['timeline_status']=='RESOLVED_SUPPORTED'
    assert report['analogous_problem_ids']==['problem-q']
    assert report['synthetic'] and not report['scientific_correctness_verified']
    assert not archive.validate()
    count=len(archive.list())
    again=run_demo(archive,tmp_path/'proposal-again.md')
    assert len(archive.list())==count
    assert report['transfer_id']==again['transfer_id']
    assert report['opportunity_id']==again['opportunity_id']
    text=(tmp_path/'proposal.md').read_text()
    for heading in ['Research question','Closest known literature','Historical open problem',
                    'Relevant bottleneck','Proposed mechanism','Novelty assessment',
                    'Potential theorem or experiment','Required assumptions','Proof obligations',
                    'Risks and counterexamples','Initial validation plan','Evidence and provenance']:
        assert '## '+heading in text
    assert 'evidence-c-delta' in text and 'version-c-1' in text
    assert 'SYNTHETIC' in text


def test_packaged_evaluation():
    result=run_evaluation()
    assert result['failed']==0,result
    assert result['passed']>=12
    assert result['synthetic'] and not result['scientific_correctness_verified']


def test_cli_all_offline_commands(tmp_path):
    runner=CliRunner()
    args=['--workspace',str(tmp_path/'workspace')]
    def run(*command):
        response=runner.invoke(app,args+list(command))
        assert response.exit_code==0,(command,response.output,response.exception)
        return json.loads(response.stdout)
    run('init')
    local=tmp_path/'local-paper.md'
    local.write_text('# Local source\nThis source has no extracted scientific assertions.')
    ingestion=run('ingest',str(local),'--metadata-only')
    assert ingestion['processing']['ingestion']['version']['coverage']=='PARTIAL_TEXT'
    invalid_sync=runner.invoke(app,args+['sync','--since','invalid'])
    assert invalid_sync.exit_code==2
    run('import-history')
    report=run('demo','--output',str(tmp_path/'export.md'))
    for command in [('search','dissipation'),('problems',),('problem','problem-p'),
                    ('bottleneck','bottleneck-dissipation'),('mechanism','mechanism-cross'),
                    ('paper','paper-c'),('compare','paper-c'),('evolution','problem-p'),
                    ('breakthroughs',),('opportunities',),('doctor',),('index','rebuild')]:
        assert run(*command) is not None
    assert run('transfer','mechanism-cross','--target','problem-q')['target_problem_id']=='problem-q'
    run('export',report['opportunity_id'],'--format','research-harness','--output',str(tmp_path/'handoff.md'))
    assert Path(tmp_path/'handoff.md').is_file()
    invalid=runner.invoke(app,args+['problem','paper-c'])
    assert invalid.exit_code==2
    assert 'expected problem' in invalid.output


def test_incremental_extraction_triggers_discovery_without_promoting_truth(tmp_path):
    from research_scout.discovery import SourcePaper
    from research_scout.domain.models import AssessmentStatus, Coverage, Evidence, Result
    from research_scout.workflows.controller import ScoutController
    from research_scout.workflows.demo import import_history, SCOPE
    archive=Archive(tmp_path/'knowledge')
    import_history(archive)
    text='SYNTHETIC: mixed energy might control the full state.'
    class ExplicitSyntheticProvider:
        def extract(self,paper,version,source_text):
            assert source_text==text
            ev=Evidence(id='evidence-incremental',title='SYNTHETIC exact span',synthetic=True,
                paper_id=paper.id,version_id=version.id,locator=f'char:0-{len(text)}',
                quotation=text,source_hash=version.content_hash,coverage=version.coverage,
                assessment_status=AssessmentStatus.SUPPORTED_BY_SOURCE)
            result=Result(id='result-incremental',title='SYNTHETIC candidate energy claim',synthetic=True,
                paper_id=paper.id,version_id=version.id,result_type='THEOREM',statement=text,
                scope=SCOPE,evidence_ids=[ev.id],problem_ids=['problem-p'],
                mechanism_ids=['mechanism-cross'],bottleneck_ids=['bottleneck-dissipation'],
                technical_delta='Candidate mixed energy construction; not reviewed.')
            return [ev,result]
    source=SourcePaper(title='SYNTHETIC incremental paper',text=text,coverage=Coverage.FULL_TEXT,
        provenance='explicit synthetic workflow test')
    out=ScoutController(archive,tmp_path/'cache',ExplicitSyntheticProvider()).process(source)
    assert not out.analysis_errors
    assert out.breakthrough_ids and out.transfer_ids and out.opportunity_ids
    assert archive.get('result-incremental').assessment_status==AssessmentStatus.PROPOSED
    assert archive.get(out.breakthrough_ids[0]).resolution_scope.value=='CLAIMED_BUT_UNVERIFIED'


def test_missing_quantifiers_cannot_close_problem(tmp_path):
    from research_scout.workflows.demo import import_history
    from research_scout.evolution import assess_resolution
    archive=Archive(tmp_path/'knowledge')
    import_history(archive)
    problem=archive.get('problem-p')
    result=archive.get('result-c')
    problem.scope=problem.scope.model_copy(update={'quantifiers':[]})
    result.scope=result.scope.model_copy(update={'quantifiers':[]})
    archive.put_many([problem,result])
    assert assess_resolution(archive,problem.id,result.id).resolution.value=='INSUFFICIENT_EVIDENCE'


def test_raw_archive_cannot_bypass_portfolio_history(tmp_path):
    import pytest
    archive=Archive(tmp_path/'knowledge')
    report=run_demo(archive)
    opportunity=archive.get(report['opportunity_id'])
    from research_scout.domain.models import OpportunityStatus
    with pytest.raises(ValueError,match='lifecycle'):
        archive.put(opportunity.model_copy(update={'status':OpportunityStatus.PROPOSAL_READY}))
    with pytest.raises(ValueError,match='append-only'):
        archive.put(opportunity.model_copy(update={'history':[]}))
