"""Local-first CLI. All knowledge-management commands work without credentials."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from functools import wraps
import json
import os
from pathlib import Path
from typing import Annotated

import httpx
import typer
from pydantic import BaseModel

from research_scout.configuration import WorkspaceConfig, cache_path, default_workspace, load_config
from research_scout.domain.models import parse_record

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False,
    help='Evidence-grounded scientific discovery. Offline knowledge commands require no API key.')
index_app = typer.Typer(help='Rebuild the disposable search and graph projection.')
app.add_typer(index_app, name='index')
fields_app = typer.Typer(help='Maintain research fields, result tables and related work.')
app.add_typer(fields_app, name='fields')


def serializable(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode='json')
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def emit(value):
    typer.echo(json.dumps(value, default=serializable, ensure_ascii=False, indent=2))


def guarded(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except typer.Exit:
            raise
        except (ValueError, TypeError, KeyError, OSError, RuntimeError, httpx.HTTPError) as exc:
            typer.echo(f'Error: {exc}', err=True)
            raise typer.Exit(2) from exc
    return wrapped


@app.callback()
def main(ctx: typer.Context,
         workspace: Annotated[Path | None, typer.Option('--workspace', '-w', help='Canonical workspace directory.')] = None):
    ctx.obj = (workspace or default_workspace()).expanduser().resolve()


def archive(ctx):
    from research_scout.storage import Archive
    load_config(ctx.obj)
    return Archive(ctx.obj/'knowledge')


@app.command()
@guarded
def init(ctx: typer.Context):
    """Initialize an independent local knowledge workspace."""
    from research_scout.storage import Archive
    root = ctx.obj
    root.mkdir(parents=True, exist_ok=True)
    config = root/'config.json'
    if not config.exists():
        config.write_text(WorkspaceConfig().model_dump_json(indent=2)+'\n')
    store = Archive(root/'knowledge')
    cache_path(root, load_config(root)).mkdir(parents=True, exist_ok=True)
    emit({'workspace':root,'records':len(store.list()),'initialized':True})


@app.command('import-records')
@guarded
def import_records(ctx: typer.Context, source: Path):
    """Validate and atomically import a JSON list of typed scientific records."""
    payload = json.loads(source.read_text())
    if not isinstance(payload, list):
        raise ValueError('input must be a JSON list')
    result = archive(ctx).put_many(parse_record(r) for r in payload)
    emit({'imported':len(result)})


@app.command('import-history')
@guarded
def import_history(ctx: typer.Context):
    """Import the bundled, prominently SYNTHETIC three-paper history."""
    from research_scout.workflows.demo import import_history as run
    emit({'synthetic':True,'fixture_records':len(run(archive(ctx)))})


@app.command()
@guarded
def search(ctx: typer.Context, query: str,
           label: Annotated[list[str] | None, typer.Option('--label')] = None):
    """Search exact IDs/aliases, taxonomy, FTS and scientific relation neighbors."""
    emit(archive(ctx).search(query, labels=label))


@app.command()
@guarded
def problems(ctx: typer.Context):
    emit(archive(ctx).list('problem'))


def show(ctx, rid, expected):
    record = archive(ctx).get(rid)
    if record.kind != expected:
        raise ValueError(f'{rid} is {record.kind}; expected {expected}')
    emit(record)


@app.command()
@guarded
def problem(ctx: typer.Context, id: str):
    show(ctx,id,'problem')


@app.command()
@guarded
def bottleneck(ctx: typer.Context, id: str):
    show(ctx,id,'bottleneck')


@app.command()
@guarded
def mechanism(ctx: typer.Context, id: str):
    show(ctx,id,'mechanism')


@app.command()
@guarded
def paper(ctx: typer.Context, id: str):
    show(ctx,id,'paper')


@app.command()
@guarded
def compare(ctx: typer.Context, paper_id: str):
    from research_scout.comparison import ComparisonEngine
    emit(ComparisonEngine(archive(ctx)).compare(paper_id))


@app.command()
@guarded
def evolution(ctx: typer.Context, problem_id: str):
    from research_scout.evolution import ProblemEvolutionTimeline
    emit(ProblemEvolutionTimeline(archive(ctx),problem_id).build())


@app.command()
@guarded
def breakthroughs(ctx: typer.Context,
                  result: Annotated[str | None, typer.Option('--result',help='Analyze an archived result.')] = None):
    store=archive(ctx)
    if result:
        from research_scout.breakthrough import BreakthroughDiscovery
        emit(BreakthroughDiscovery(store).analyze(result))
    else:
        emit(store.list('breakthrough'))


@app.command()
@guarded
def opportunities(ctx: typer.Context):
    emit(archive(ctx).list('opportunity'))


@app.command('review-opportunity')
@guarded
def review_opportunity(ctx: typer.Context, source: Path):
    """Append a validated research review with pinned workspace artifacts."""
    from research_scout.opportunities.reviews import ResearchReview, ResearchReviewService
    from research_scout.workflows.weekly import _run_lock
    review = ResearchReview.model_validate(json.loads(source.read_text()))
    with _run_lock(ctx.obj):
        result = ResearchReviewService(archive(ctx), ctx.obj).record(review)
    emit(result)


@app.command('opportunity-reviews')
@guarded
def opportunity_reviews(ctx: typer.Context, opportunity_id: str):
    """Read retained research findings without network or model calls."""
    from research_scout.opportunities.reviews import ResearchReviewService
    emit(ResearchReviewService(archive(ctx), ctx.obj).reviews(opportunity_id))


@app.command('export')
@guarded
def export_command(ctx: typer.Context, opportunity_id: str,
                   format: Annotated[str,typer.Option('--format')] = 'research-harness',
                   output: Annotated[Path,typer.Option('--output','-o')] = Path('proposal.md')):
    if format != 'research-harness':
        raise ValueError('supported format: research-harness')
    from research_scout.integration import export_proposal
    emit({'path':export_proposal(archive(ctx),opportunity_id,output)})


@index_app.command('rebuild')
@guarded
def rebuild(ctx: typer.Context):
    emit({'indexed_records':archive(ctx).rebuild()})


@app.command()
@guarded
def doctor(ctx: typer.Context):
    store=archive(ctx)
    errors=store.validate()
    config=load_config(ctx.obj)
    if config.extraction_provider == 'codex':
        import shutil
        import subprocess
        executable=shutil.which(config.codex_binary)
        ready=bool(executable and subprocess.run([executable,'login','status'],capture_output=True,
                                                 timeout=15).returncode==0)
    else:
        ready=bool(os.environ.get(config.llm_api_key_env) and (config.llm_model or os.environ.get('SCOUT_MODEL')))
    emit({'workspace':ctx.obj,'records':len(store.list()),'errors':errors,
          'offline_ready':not errors,'extraction_provider':config.extraction_provider,'llm_configured':ready,
          'scientific_correctness_verified':False})
    if errors:
        raise typer.Exit(2)


@app.command()
@guarded
def ingest(ctx: typer.Context, source: str,
           extract: Annotated[bool,typer.Option('--extract/--metadata-only',help='Run configured structured scientific extraction.')] = False,
           discover: Annotated[bool,typer.Option('--discover',help='Also create breakthrough/transfer hypotheses.')] = False):
    """Ingest DOI/arXiv/URL/local PDF or text; scientific extraction is explicit."""
    from research_scout.configuration import extraction_provider
    from research_scout.workflows.controller import ScoutController
    config=load_config(ctx.obj)
    provider=None
    if extract:
        provider=extraction_provider(config)
    from research_scout.workflows.weekly import _run_lock
    with _run_lock(ctx.obj):
        outcome=ScoutController(archive(ctx),cache_path(ctx.obj,config),provider).process(
            source,extract=extract,discover=discover)
        result=asdict(outcome)
        if (ctx.obj/'fields.json').exists():
            from research_scout.workflows.fields import FieldDossiers
            reports=FieldDossiers(archive(ctx),ctx.obj).update()
            result['field_dossiers']=[r['field']['id'] for r in reports]
    emit(result)


@app.command()
@guarded
def sync(ctx: typer.Context,
         since: Annotated[str,typer.Option('--since')] = '7d',
         profile: Annotated[Path | None,typer.Option('--profile')] = None):
    """Discover recent arXiv metadata using configurable interest queries."""
    from datetime import date,timedelta
    import re
    from research_scout.discovery import ArxivClient, InterestProfile
    from research_scout.ingestion import PaperIngestor
    match=re.fullmatch(r'(\d+)d',since)
    if not match:
        raise ValueError('--since must be a duration such as 7d')
    config=load_config(ctx.obj)
    interests=InterestProfile.load(profile) if profile else InterestProfile(
        arxiv_queries=config.interest_queries, labels=config.interest_labels,
        max_results=config.max_results)
    ingestor=PaperIngestor(archive(ctx),cache_path(ctx.obj,config))
    results=[]
    for query in interests.arxiv_queries:
        for source in ArxivClient().search(query,since=date.today()-timedelta(days=int(match[1])),
                                         max_results=interests.max_results):
            source.labels=sorted(set(source.labels+interests.labels))
            results.append(ingestor.ingest(source))
    emit(results)


@app.command()
@guarded
def demo(ctx: typer.Context,
         output: Annotated[Path,typer.Option('--output','-o')] = Path('synthetic-proposal.md')):
    """Run the complete explicitly SYNTHETIC offline discovery-to-proposal workflow."""
    from research_scout.workflows.demo import run_demo
    emit(run_demo(archive(ctx),output))


@app.command()
@guarded
def transfer(ctx: typer.Context, mechanism_id: str,
             target: Annotated[str,typer.Option('--target')],
             mode: Annotated[str,typer.Option('--mode')] = 'TECHNIQUE_FIRST',
             breakthrough: Annotated[str | None,typer.Option('--breakthrough')] = None):
    """Generate a qualified transfer hypothesis with explicit proof obligations."""
    from research_scout.domain.models import TransferMode
    from research_scout.transfer import TransferDiscovery
    emit(TransferDiscovery(archive(ctx)).propose(mechanism_id,target,
        mode=TransferMode(mode.upper().replace('-','_')), breakthrough_id=breakthrough))


@app.command('discover')
@guarded
def discover(ctx: typer.Context, seed_id: str,
             mode: Annotated[str,typer.Option('--mode')] = 'BREAKTHROUGH_FIRST'):
    """Retrieve candidate transfers using any of four scientific discovery modes."""
    from research_scout.domain.models import TransferMode
    from research_scout.transfer import TransferDiscovery
    emit(TransferDiscovery(archive(ctx)).discover(TransferMode(mode.upper().replace('-','_')),seed_id))


@app.command('opportunity')
@guarded
def opportunity(ctx: typer.Context, transfer_id: str):
    """Create a persistent portfolio candidate from an archived transfer."""
    from research_scout.opportunities import OpportunityPortfolio
    emit(OpportunityPortfolio(archive(ctx)).from_transfer(transfer_id))


@app.command('transition')
@guarded
def transition(ctx: typer.Context, opportunity_id: str, status: str,
               reason: Annotated[str,typer.Option('--reason')]):
    """Apply an explicit portfolio lifecycle transition, retaining reasons."""
    from research_scout.domain.models import OpportunityStatus
    from research_scout.opportunities import OpportunityPortfolio
    emit(OpportunityPortfolio(archive(ctx)).transition(opportunity_id,OpportunityStatus(status.upper()),reason))


@app.command()
@guarded
def eval(ctx: typer.Context):
    """Run deterministic synthetic integrity evaluations in an isolated workspace."""
    from research_scout.workflows.evaluation import run_evaluation
    result=run_evaluation()
    emit(result)
    if result['failed']:
        raise typer.Exit(1)


@fields_app.command('configure')
@guarded
def fields_configure(ctx: typer.Context, source: Path):
    """Install a validated field registry in this workspace."""
    from research_scout.workflows.fields import FieldRegistry
    from research_scout.workflows.weekly import _atomic_json, _run_lock
    load_config(ctx.obj)
    registry=FieldRegistry.model_validate_json(source.read_text())
    with _run_lock(ctx.obj):
        _atomic_json(ctx.obj/'fields.json',registry.model_dump(mode='json'))
    emit({'configured':[f.id for f in registry.fields]})


@fields_app.command('list')
@guarded
def fields_list(ctx: typer.Context):
    """List configured research fields without model or network access."""
    from research_scout.workflows.fields import FieldRegistry
    emit(FieldRegistry.load(ctx.obj))


@fields_app.command('update')
@guarded
def fields_update(ctx: typer.Context,
                  field_id: Annotated[str | None,typer.Argument()] = None,
                  refresh_related_work: Annotated[bool,typer.Option('--refresh-related-work')] = False):
    """Update result dossiers offline; optionally refresh model-written prose."""
    from research_scout.workflows.fields import FieldDossiers, FieldRegistry
    from research_scout.workflows.weekly import _run_lock
    config=load_config(ctx.obj)
    registry=FieldRegistry.load(ctx.obj)
    if field_id is not None and field_id not in {f.id for f in registry.fields}:
        raise ValueError(f'Unknown field: {field_id}')
    with _run_lock(ctx.obj):
        if refresh_related_work:
            from research_scout.configuration import extraction_provider
            from research_scout.workflows.related_work import RelatedWorkReview
            RelatedWorkReview(archive(ctx),ctx.obj,cache_path(ctx.obj,config),
                              extraction_provider(config)).run(refresh=True)
        reports=FieldDossiers(archive(ctx),ctx.obj).update(field_id)
    emit({'index':ctx.obj/'fields/README.md','fields':[
        {'id':r['field']['id'],'result_count':len(r['results']),'snapshot_id':r['snapshot_id'],
         'narrative_status':r['narrative']['status'],'updated':r['updated'],
         'changes':r['update_changes']} for r in reports]})


@fields_app.command('show')
@guarded
def fields_show(ctx: typer.Context,field_id: str,
                markdown: Annotated[bool,typer.Option('--markdown')] = False):
    """Read the latest maintained field dossier."""
    from research_scout.workflows.fields import FieldRegistry
    if field_id not in {f.id for f in FieldRegistry.load(ctx.obj).fields}:
        raise ValueError(f'Unknown field: {field_id}')
    path=ctx.obj/'fields'/field_id/('latest.md' if markdown else 'latest.json')
    if not path.is_file():
        raise ValueError('Field dossier not built; run scout fields update')
    if markdown:
        typer.echo(path.read_text())
    else:
        emit(json.loads(path.read_text()))


@app.command()
@guarded
def related_work(ctx: typer.Context,
                 refresh: Annotated[bool,typer.Option('--refresh')] = False):
    """Write source-supported development tracks, comparisons and related-work prose."""
    from research_scout.configuration import extraction_provider
    from research_scout.workflows.related_work import RelatedWorkReview
    from research_scout.workflows.weekly import _run_lock
    config=load_config(ctx.obj)
    with _run_lock(ctx.obj):
        result=RelatedWorkReview(archive(ctx),ctx.obj,cache_path(ctx.obj,config),
                                 extraction_provider(config)).run(refresh=refresh)
        if (ctx.obj/'fields.json').exists():
            from research_scout.workflows.fields import FieldDossiers
            dossiers=FieldDossiers(archive(ctx),ctx.obj).update()
            result=dict(result,field_dossiers=[f['field']['id'] for f in dossiers])
    emit(result)


@app.command()
@guarded
def gaps(ctx: typer.Context,
         max_candidates: Annotated[int,typer.Option('--max-candidates',min=1,max=3)] = 3,
         refresh: Annotated[bool,typer.Option('--refresh')] = False,
         local_only: Annotated[bool,typer.Option('--local-only')] = False):
    """Propose theory questions with evidence, proof obligations and prior-art leads."""
    from research_scout.configuration import extraction_provider
    from research_scout.workflows.gaps import TheoryGapReview
    from research_scout.workflows.weekly import _run_lock
    config=load_config(ctx.obj)
    with _run_lock(ctx.obj):
        profile=ctx.obj/'tracking-profile.json'
        if profile.is_file() and json.loads(profile.read_text()).get('related_work_review'):
            from research_scout.workflows.related_work import RelatedWorkReview
            RelatedWorkReview(archive(ctx),ctx.obj,cache_path(ctx.obj,config),
                              extraction_provider(config)).run()
        result=TheoryGapReview(archive(ctx),ctx.obj,cache_path(ctx.obj,config),
                              extraction_provider(config)).run(max_candidates,refresh=refresh,
                                                               external=not local_only)
    emit(result)


@app.command()
@guarded
def weekly(ctx: typer.Context,
           profile: Annotated[Path | None,typer.Option('--profile')] = None,
           since: Annotated[str | None,typer.Option('--since')] = None,
           max_papers: Annotated[int | None,typer.Option('--max-papers',min=1,max=20)] = None,
           metadata_only: Annotated[bool,typer.Option('--metadata-only')] = False,
           pending_only: Annotated[bool,typer.Option('--pending-only',help='Resume the saved queue without new discovery.')] = False):
    """Collect a bounded shortlist, read full papers, update knowledge and write a report."""
    import re
    from research_scout.configuration import extraction_provider
    from research_scout.workflows.weekly import WeeklyCollector,WeeklyProfile
    path=profile or ctx.obj/'tracking-profile.json'
    selected=WeeklyProfile.load(path)
    if since is not None:
        match=re.fullmatch(r'(\d+)d',since)
        if not match:
            raise ValueError('--since must be a duration such as 8d')
        selected.lookback_days=int(match[1])
    if max_papers is not None:
        selected.max_papers=max_papers
    if metadata_only:
        selected.extract=False
    config=load_config(ctx.obj)
    provider=extraction_provider(config) if selected.extract else None
    result=WeeklyCollector(archive(ctx),ctx.obj,cache_path(ctx.obj,config),provider).run(selected,discover=not pending_only)
    emit(result)
    if result['errors']:
        raise typer.Exit(1)


if __name__ == '__main__':
    app()
