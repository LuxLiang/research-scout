"""Bounded, resumable weekly literature collection and scientific extraction."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata
from zoneinfo import ZoneInfo

from pydantic import Field

from research_scout.discovery import ArxivClient, SourcePaper
from research_scout.domain.models import Paper, StrictModel
from research_scout.ingestion import IngestionOutcome, PaperIngestor
from research_scout.workflows.controller import ScoutController


class WeeklyProfile(StrictModel):
    name: str
    arxiv_queries: list[str] = Field(min_length=1)
    labels: list[str] = Field(default_factory=list)
    priority_terms: list[str] = Field(default_factory=list)
    topic_terms: dict[str,list[str]] = Field(default_factory=dict)
    max_results_per_query: int = Field(default=20, ge=1, le=100)
    max_papers: int = Field(default=5, ge=1, le=20)
    lookback_days: int = Field(default=8, ge=1, le=3650)
    request_interval_seconds: float = Field(default=3.1, ge=0, le=60)
    timezone: str = 'Asia/Shanghai'
    extract: bool = True
    theory_gap_review: bool = False
    related_work_review: bool = False
    field_dossiers: bool = False
    automatic_discovery: bool = False
    max_gap_candidates: int = Field(default=3, ge=1, le=3)

    @classmethod
    def load(cls, path):
        return cls.model_validate_json(Path(path).read_text())


def _text(value):
    value=unicodedata.normalize('NFKD',value).casefold()
    value=''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.findall(r'\w+',value))


def _key(source):
    return f'{source.arxiv_id}:{source.version or "unversioned"}'


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.scout-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(payload,f,ensure_ascii=False,indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def _run_lock(workspace):
    handle=(workspace/'.weekly.lock').open('a')
    try:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('A weekly collection run is already active') from exc
        yield
    finally:
        handle.close()


class WeeklyCollector:
    def __init__(self,archive,workspace,cache_dir,provider=None,arxiv=None,http_client=None):
        self.archive=archive
        self.workspace=Path(workspace).resolve()
        self.workspace.mkdir(parents=True,exist_ok=True)
        self.ingestor=PaperIngestor(archive,cache_dir,http_client)
        self.controller=ScoutController(archive,cache_dir,provider,http_client)
        self.arxiv=arxiv or ArxivClient(http_client)
        self.provider=provider

    def _processed(self,source,extract):
        paper=next((p for p in self.archive.list('paper') if isinstance(p,Paper)
                    and p.arxiv_id==source.arxiv_id),None)
        if paper is None:
            return False
        versions=[self.archive.get(v) for v in paper.version_ids]
        matches=[v for v in versions if v.version.split('+content-')[0]==source.version]
        if not extract:
            return bool(matches)
        staging=self.ingestor.cache_dir/'staging'
        for version in matches:
            stage=staging/f'{version.id}.json'
            if stage.is_file() and json.loads(stage.read_text()).get('status')=='PUBLISHED':
                return True
        return False

    def run(self,profile: WeeklyProfile, *, discover=True):
        if profile.extract and self.provider is None:
            raise ValueError('Weekly extraction requires an explicit configured provider')
        with _run_lock(self.workspace):
            return self._run(profile,discover=discover)

    def _run(self,profile, *, discover=True):
        current=datetime.now(ZoneInfo(profile.timezone))
        since=current.date()-timedelta(days=profile.lookback_days)
        queue_path=self.workspace/'weekly-pending.json'
        queued=json.loads(queue_path.read_text()) if queue_path.is_file() else []
        candidates={_key(s):s for s in map(SourcePaper.model_validate,queued)}
        errors=[]
        discovered=0
        for index,query in enumerate(profile.arxiv_queries if discover else []):
            if index and profile.request_interval_seconds:
                time.sleep(profile.request_interval_seconds)
            try:
                for source in self.arxiv.search(query,since=since,max_results=profile.max_results_per_query):
                    discovered+=1
                    searchable=_text(source.title+' '+(source.abstract or ''))
                    matched=[label for label,terms in profile.topic_terms.items()
                             if any(_text(term) in searchable for term in terms)]
                    source.labels=sorted(set(source.labels+profile.labels+matched))
                    candidates[_key(source)]=source
            except Exception as exc:
                errors.append({'stage':'discovery','query':query,'error':f'{type(exc).__name__}: {exc}'})
        eligible=[s for s in candidates.values() if not self._processed(s,profile.extract)]
        def priority(source):
            title,abstract=_text(source.title),_text(source.abstract or '')
            terms=[_text(t) for t in profile.priority_terms]
            score=sum(6 for t in terms if t in title)+sum(2 for t in terms if t in abstract)
            return (-score,-(source.published or date.min).toordinal(),_key(source))
        eligible.sort(key=priority)
        selected=eligible[:profile.max_papers]
        pending={_key(s):s for s in eligible}
        articles=[]
        # Checkpoint all candidates before costly downloads/model calls. A crash
        # leaves the selected and overflow candidates available to the next run.
        _atomic_json(queue_path,[s.model_dump(mode='json') for s in pending.values()])
        for index,source in enumerate(selected):
            if index and profile.request_interval_seconds:
                time.sleep(profile.request_interval_seconds)
            item={'title':source.title,'arxiv_id':source.arxiv_id,'version':source.version,
                  'url':f'https://arxiv.org/abs/{source.arxiv_id}{source.version or ""}',
                  'abstract':source.abstract,'priority_score':-priority(source)[0],
                  'status':'PENDING','paper_id':None}
            try:
                ingested=self.ingestor.ingest(source)
                item['paper_id']=ingested.paper.id
                item['coverage']=ingested.version.coverage.value
                if profile.extract:
                    if not source.arxiv_id:
                        raise ValueError('Automatic full-text retrieval requires an arXiv identity')
                    pdf=f'https://arxiv.org/pdf/{source.arxiv_id}{source.version or ""}'
                    # Cache the original PDF and actual extracted coverage before
                    # invoking the model; an abstract is never labeled full text.
                    paper=self.archive.get(ingested.paper.id)
                    cached=[self.archive.get(v) for v in paper.version_ids]
                    cached=[v for v in cached if v.version.split('+content-')[0]==source.version
                            and v.source_path and v.source_path.endswith('.pdf')
                            and Path(v.source_path).is_file()
                            and v.text_path and Path(v.text_path).is_file()]
                    material=IngestionOutcome(paper,cached[-1],False) if cached else pdf
                    if profile.automatic_discovery:
                        outcome=self.controller.process(material,extract=True)
                    else:
                        outcome=self.controller.process(material,extract=True,discover=False)
                    item.update(status='EXTRACTED',coverage=outcome.processing.version.coverage.value,
                        result_ids=[r.id for r in outcome.processing.records if r.kind=='result'],
                        breakthrough_ids=outcome.breakthrough_ids,transfer_ids=outcome.transfer_ids,
                        opportunity_ids=outcome.opportunity_ids,analysis_errors=outcome.analysis_errors)
                else:
                    item['status']='METADATA_ONLY'
                pending.pop(_key(source),None)
            except Exception as exc:
                item.update(status='RETRY_PENDING',error=f'{type(exc).__name__}: {exc}')
                errors.append({'stage':'article','arxiv_id':source.arxiv_id,'error':item['error']})
            articles.append(item)
            _atomic_json(queue_path,[s.model_dump(mode='json') for s in pending.values()])
        related_work = None
        lineage_ready = True
        if profile.related_work_review and profile.extract:
            try:
                from research_scout.workflows.related_work import RelatedWorkReview
                related_work = RelatedWorkReview(self.archive,self.workspace,
                    self.ingestor.cache_dir,self.provider).run()
            except Exception as exc:
                lineage_ready = False
                errors.append({'stage':'related_work_review','error':f'{type(exc).__name__}: {exc}'})
        fields = None
        if profile.field_dossiers and profile.extract:
            try:
                from research_scout.workflows.fields import FieldDossiers
                fields = FieldDossiers(self.archive,self.workspace).update()
            except Exception as exc:
                lineage_ready = False
                errors.append({'stage':'field_dossiers','error':f'{type(exc).__name__}: {exc}'})
        gap_review = None
        if profile.theory_gap_review and profile.extract and lineage_ready:
            try:
                from research_scout.workflows.gaps import TheoryGapReview
                gap_review = TheoryGapReview(self.archive,self.workspace,self.ingestor.cache_dir,
                                             self.provider,arxiv=self.arxiv).run(profile.max_gap_candidates)
            except Exception as exc:
                errors.append({'stage':'theory_gap_review','error':f'{type(exc).__name__}: {exc}'})
        report={'profile':profile.name,'recorded_at':current.isoformat(),'since':since.isoformat(),
            'selection':'Keyword matching priority; not a scientific quality or novelty score.',
            'discovery_ran':discover,'discovered':discovered,'unique_candidates':len(candidates),'selected':len(selected),
            'remaining_pending':len(pending),'extract':profile.extract,'articles':articles,'errors':errors}
        if fields is not None:
            report['field_dossiers'] = {'index':'../fields/README.md','fields':[
                {'id':f['field']['id'],'result_count':len(f['results']),
                 'snapshot_id':f['snapshot_id'],'narrative_status':f['narrative']['status'],
                 'updated':f['updated'],'changes':f['update_changes']} for f in fields]}
        if related_work is not None:
            report['related_work_review'] = {'report':'related-work/latest.md',
                                             'track_count':len(related_work['sections'])}
        if gap_review is not None:
            query_errors = sum(len(c.get('external_errors',[])) for c in gap_review['cards'])
            report['theory_gap_review'] = {'candidate_count':len(gap_review['cards']),
                'report':'gaps/latest.md','novelty':'UNDETERMINED',
                'external_query_error_count':query_errors}
            if query_errors:
                errors.append({'stage':'theory_prior_art',
                               'error':f'{query_errors} prior-art queries failed; see gaps/latest.md'})
        directory=self.workspace/'reports'
        filename=current.strftime('%Y-%m-%dT%H%M%S%f')
        _atomic_json(directory/f'{filename}.json',report)
        _atomic_json(directory/'latest.json',report)
        markdown=self._markdown(report)
        (directory/f'{filename}.md').write_text(markdown,encoding='utf-8')
        (directory/'latest.md').write_text(markdown,encoding='utf-8')
        return report

    @staticmethod
    def _markdown(report):
        lines=[f'# Research Scout 周报 — {report["recorded_at"][:10]}','',
            f'方向：{report["profile"]}；检索起始日期：{report["since"]}。',
            f'本次处理 {report["selected"]} 篇；队列剩余 {report["remaining_pending"]} 篇。','',
            '排序依据是关键词匹配，不能代表科学质量、新颖性或数学正确性。','']
        for item in report['articles']:
            lines += [f'## {item["title"]}','',f'- 论文：{item["url"]}',
                f'- 状态：{item["status"]}；覆盖范围：{item.get("coverage","unknown")}',
                f'- 知识库 ID：{item["paper_id"]}']
            if item.get('error'):
                lines.append('- 待重试原因：'+item['error'])
            for key in ('result_ids','breakthrough_ids','transfer_ids','opportunity_ids'):
                if item.get(key):
                    lines.append(f'- {key}: '+', '.join(item[key]))
            if item.get('analysis_errors'):
                lines.append('- 下游分析待处理：'+'; '.join(item['analysis_errors']))
            lines += ['', '### 摘要（作者原文）','',item.get('abstract') or '未提供摘要。','']
        if report.get('field_dossiers'):
            lines += ['## 研究领域档案','',
                      '[查看逐结果定量表、发展脉络与本次变更](../fields/README.md)','']
            for field in report['field_dossiers']['fields']:
                changes=field['changes']
                lines += [f"- {field['id']}：{field['result_count']} 项结果；新增 {len(changes['added'])}、"
                          f"变化 {len(changes['changed'])}、退出 {len(changes['removed'])}；"
                          f"Related Work {field['narrative_status']}"]
            lines += ['']
        if report.get('related_work_review'):
            lines += ['## 发展脉络与 Related Work','',
                '[查看问题主线、跨论文比较和证据关系](related-work/latest.md)','']
        if report.get('theory_gap_review'):
            lines += ['## 理论 gap 候选','',
                f"本轮 {report['theory_gap_review']['candidate_count']} 个待验证假说；新颖性未确定。",
                '[查看问题、证明义务和外部查重记录](gaps/latest.md)','']
        if report['errors']:
            lines += ['## 本次未完成项','']
            lines += ['- '+str(e) for e in report['errors']]
        return '\n'.join(lines)+'\n'
