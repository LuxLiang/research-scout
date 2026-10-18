from datetime import date
import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from research_scout.cli import app
from research_scout.discovery import SourcePaper
from research_scout.domain.models import Coverage
from research_scout.storage import Archive
from research_scout.workflows.weekly import WeeklyCollector, WeeklyProfile, _run_lock


def source(number,title):
    return SourcePaper(title=title,arxiv_id=f'2610.{number:05}',version='v1',
        published=date(2026,10,18),abstract='A source abstract about sampling.',
        coverage=Coverage.ABSTRACT_ONLY)


class Sources:
    def __init__(self,papers):
        self.papers=papers
    def search(self,*args,**kwargs):
        return self.papers


def profile(**kwargs):
    return WeeklyProfile(name='test',arxiv_queries=['all:sampling'],
        priority_terms=['underdamped Langevin'],request_interval_seconds=0,
        **kwargs)


def test_bounded_selection_taxonomy_checkpoint_and_no_duplicates(tmp_path):
    papers=[source(1,'Generic sampling'),source(2,'Underdamped Langevin convergence'),
            source(3,'Other sampling')]
    archive=Archive(tmp_path/'knowledge')
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',arxiv=Sources(papers))
    selected=profile(extract=False,max_papers=2,labels=['sampling'],
        topic_terms={'underdamped-langevin':['underdamped Langevin'],'discrete':['discrete']})
    report=worker.run(selected)
    assert report['selected']==2
    assert report['articles'][0]['arxiv_id']==papers[1].arxiv_id
    assert report['remaining_pending']==1
    assert len(archive.list('paper'))==2
    for p in archive.list('paper'):
        assert 'discrete' not in p.labels
        assert ('underdamped-langevin' in p.labels)==('Underdamped' in p.title)
    assert worker.run(selected)['selected']==1
    assert worker.run(selected)['selected']==0
    assert len(archive.list('paper'))==3
    assert json.loads((tmp_path/'weekly-pending.json').read_text())==[]
    assert (tmp_path/'reports/latest.md').is_file()


def test_full_text_extraction_uses_pdf_and_reports_downstream_errors(tmp_path):
    archive=Archive(tmp_path/'knowledge')
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),
        arxiv=Sources([source(1,'Underdamped Langevin')]))
    seen=[]
    def process(url,extract):
        seen.append((url,extract))
        return SimpleNamespace(processing=SimpleNamespace(version=SimpleNamespace(
            coverage=Coverage.FULL_TEXT),records=[]),breakthrough_ids=['b'],
            transfer_ids=['t'],opportunity_ids=['o'],analysis_errors=['Uncertain proof step'])
    worker.controller.process=process
    report=worker.run(profile())
    assert seen==[('https://arxiv.org/pdf/2610.00001v1',True)]
    assert report['articles'][0]['status']=='EXTRACTED'
    assert report['articles'][0]['coverage']=='FULL_TEXT'
    assert report['articles'][0]['analysis_errors']==['Uncertain proof step']
    assert not report['errors']


def test_failed_download_or_model_preserves_metadata_and_retry_queue(tmp_path):
    archive=Archive(tmp_path/'knowledge')
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),
        arxiv=Sources([source(1,'Underdamped Langevin')]))
    def fail(*args,**kwargs):
        raise RuntimeError('PDF unavailable')
    worker.controller.process=fail
    report=worker.run(profile())
    assert report['articles'][0]['status']=='RETRY_PENDING'
    assert report['articles'][0]['coverage']=='ABSTRACT_ONLY'
    assert report['remaining_pending']==1
    assert len(archive.list('paper'))==1
    assert json.loads((tmp_path/'weekly-pending.json').read_text())[0]['arxiv_id']=='2610.00001'
    worker.arxiv=Sources([])
    assert worker.run(profile())['selected']==1  # Retry survives discovery window expiry.
    assert len(archive.list('paper'))==1


def test_published_version_is_not_extracted_again(tmp_path):
    archive=Archive(tmp_path/'knowledge')
    paper=source(1,'Underdamped Langevin')
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),arxiv=Sources([paper]))
    ingested=worker.ingestor.ingest(paper)
    stage=worker.ingestor.cache_dir/'staging'/f'{ingested.version.id}.json'
    stage.write_text(json.dumps({'status':'PUBLISHED'}))
    assert worker.run(profile())['selected']==0


def test_discovery_failures_are_reported_and_lock_prevents_overlap(tmp_path):
    class Broken:
        def search(self,*args,**kwargs):
            raise RuntimeError('source unavailable')
    archive=Archive(tmp_path/'knowledge')
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',arxiv=Broken())
    report=worker.run(profile(extract=False))
    assert report['errors'][0]['stage']=='discovery'
    with _run_lock(tmp_path):
        with pytest.raises(RuntimeError,match='already active'):
            worker.run(profile(extract=False))
    with pytest.raises(ValueError,match='provider'):
        worker.run(profile())


def test_weekly_cli_validates_duration_before_external_calls(tmp_path):
    runner=CliRunner()
    args=['--workspace',str(tmp_path)]
    assert runner.invoke(app,args+['init']).exit_code==0
    (tmp_path/'tracking-profile.json').write_text(profile(extract=False).model_dump_json())
    response=runner.invoke(app,args+['weekly','--since','yesterday'])
    assert response.exit_code==2
    assert '--since' in response.output


def test_cron_installer_preserves_existing_jobs_and_is_idempotent(tmp_path,monkeypatch,capsys):
    import importlib.util
    from pathlib import Path
    import sys
    from datetime import datetime
    spec=importlib.util.spec_from_file_location('cron_installer',Path(__file__).parents[1]/'scripts/install_weekly_cron.py')
    installer=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    monkeypatch.setattr(installer,'ZoneInfo',lambda value:datetime.now().astimezone().tzinfo)
    (tmp_path/'tracking-profile.json').write_text(profile(extract=False).model_dump_json())
    original='15 2 * * * /usr/bin/true # another-job\n'
    state={'text':original}
    def run(args,**kwargs):
        if args==['crontab','-l']:
            return SimpleNamespace(returncode=0,stdout=state['text'],stderr='')
        assert args==['crontab','-']
        state['text']=kwargs['input']
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(installer.subprocess,'run',run)
    monkeypatch.setattr(sys,'argv',['install_weekly_cron.py','--workspace',str(tmp_path)])
    installer.main()
    installer.main()
    assert state['text'].startswith(original)
    assert state['text'].count('# research-scout-weekly:')==1
    runner=tmp_path/'run-weekly.sh'
    assert runner.stat().st_mode & 0o777 == 0o700
    assert '-m research_scout.cli' in runner.read_text()
    assert 'Installed' in capsys.readouterr().out


def test_pending_only_does_not_repeat_literature_requests(tmp_path):
    class NoRequests:
        def search(self,*args,**kwargs):
            raise AssertionError('Pending-only run must not query literature sources')
    paper=source(1,'Underdamped Langevin')
    (tmp_path/'weekly-pending.json').write_text(json.dumps([paper.model_dump(mode='json')]))
    archive=Archive(tmp_path/'knowledge')
    worker=WeeklyCollector(archive,tmp_path,tmp_path/'sources',arxiv=NoRequests())
    result=worker.run(profile(extract=False),discover=False)
    assert result['discovery_ran'] is False
    assert result['discovered']==0 and result['selected']==1
    assert not result['errors']
