"""Maintained field dossiers derived from attributable, versioned result records."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator

from research_scout.domain.models import Evidence, Paper, Result, StrictModel
from research_scout.workflows.weekly import _atomic_json, _text


def fingerprint(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def result_fingerprint(result):
    return fingerprint(result.model_dump(mode='json',exclude={'created_at','updated_at','revision'}))


class FieldBranch(StrictModel):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]*$')
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    match_terms: list[str] = Field(default_factory=list)
    result_ids: list[str] = Field(default_factory=list)


class ResearchField(StrictModel):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]*$')
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    parent_id: str | None = None
    result_match_terms: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    exclude_labels: list[str] = Field(default_factory=list)
    match_terms: list[str] = Field(default_factory=list)
    paper_ids: list[str] = Field(default_factory=list)
    result_ids: list[str] = Field(default_factory=list)
    context_paper_ids: list[str] = Field(default_factory=list)
    branches: list[FieldBranch] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_branches(self):
        if len({b.id for b in self.branches})!=len(self.branches):
            raise ValueError('Duplicate branch IDs')
        return self


class FieldRegistry(StrictModel):
    schema_version: str = '1.0'
    fields: list[ResearchField] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_fields(self):
        if len({f.id for f in self.fields})!=len(self.fields):
            raise ValueError('Duplicate field IDs')
        fields={f.id:f for f in self.fields}
        for field in self.fields:
            seen={field.id}
            parent=field.parent_id
            while parent is not None:
                if parent not in fields:
                    raise ValueError(f'Unknown parent field: {parent}')
                if parent in seen:
                    raise ValueError('Field hierarchy contains a cycle')
                seen.add(parent)
                parent=fields[parent].parent_id
        return self

    @classmethod
    def load(cls,workspace):
        path=Path(workspace)/'fields.json'
        if not path.is_file():
            raise ValueError('Missing fields.json; configure the research fields first')
        return cls.model_validate_json(path.read_text())


class ResultNote(StrictModel):
    """Optional source-pinned details; never copied from a paper-level row."""
    result_id: str
    result_fingerprint: str
    evidence_ids: list[str] = Field(min_length=1)
    oracle: str | None = None
    total_cost: str | None = None
    initialization: str | None = None
    parameter_dependence: str | None = None
    proof_mechanism: str | None = None
    boundary: str | None = None
    provenance: str = Field(min_length=1)

    @field_validator('oracle','total_cost','initialization','parameter_dependence','proof_mechanism','boundary')
    @classmethod
    def nonblank_details(cls,value):
        if value is not None and not value.strip():
            raise ValueError('Use null for an unknown result detail')
        return value


def _match(terms,text):
    normalized=' '+_text(text)+' '
    return any(' '+_text(term)+' ' in normalized for term in terms if _text(term))


def field_result_memberships(registry, records):
    """Shared dossier/transfer membership, with result-level child filtering."""
    fields={f.id:f for f in registry.fields}
    memberships={}
    def select(field):
        if field.id in memberships:
            return memberships[field.id]
        parent=select(fields[field.parent_id]) if field.parent_id else None
        papers={p.id for p in records.values() if isinstance(p,Paper) and (
            p.id in field.paper_ids or (not set(p.labels)&set(field.exclude_labels) and
            (set(p.labels)&set(field.labels) or _match(field.match_terms,p.title))))}
        explicit=set(field.result_ids)|{rid for b in field.branches for rid in b.result_ids}
        selected=set()
        for r in records.values():
            if not isinstance(r,Result):
                continue
            if r.id in explicit:
                selected.add(r.id)
                continue
            if parent is not None and r.id not in parent:
                continue
            has_paper_selector=bool(field.paper_ids or field.labels or field.match_terms)
            if r.paper_id not in papers and (has_paper_selector or not field.result_match_terms):
                continue
            text=' '.join([r.title,r.statement,r.scope.model,r.scope.objective,r.scope.guarantee])
            if field.result_match_terms and not _match(field.result_match_terms,text):
                continue
            selected.add(r.id)
        if parent is not None and not selected<=parent:
            raise ValueError(f'Child field {field.id} includes results outside its parent')
        memberships[field.id]=selected
        return selected
    for field in registry.fields:
        select(field)
    return memberships


class FieldDossiers:
    def __init__(self,archive,workspace):
        self.archive,self.workspace=archive,Path(workspace)

    def _notes(self,records):
        path=self.workspace/'result-notes.json'
        notes=[ResultNote.model_validate(n) for n in json.loads(path.read_text())] if path.exists() else []
        if len({n.result_id for n in notes})!=len(notes):
            raise ValueError('Duplicate result notes')
        for note in notes:
            result=records.get(note.result_id)
            if not isinstance(result,Result):
                raise ValueError('Result note references an unknown result')
            for eid in note.evidence_ids:
                e=records.get(eid)
                if not isinstance(e,Evidence) or e.paper_id!=result.paper_id or e.version_id!=result.version_id:
                    raise ValueError('Result notes need evidence from their own paper/version')
        return {n.result_id:n for n in notes}

    def _narrative(self,field,paper_ids,records):
        path=self.workspace/'reports/related-work/latest.json'
        if not path.exists():
            return {'status':'MISSING','sections':[],'missing_foundations':[],
                    'reason':'尚未生成有证据支撑的 Related Work；定量结果仍可独立维护。'}
        report=json.loads(path.read_text())
        # Verify against the actual input snapshot, not just a matching paper title.
        input_path=path.parent/(report['input_fingerprint']+'.input.json')
        snapshot=json.loads(input_path.read_text()) if input_path.exists() else {}
        old={r['id']:r for r in snapshot.get('papers',[])+snapshot.get('records',[])}
        relevant=paper_ids|set(field.context_paper_ids)
        dependencies=set(relevant)
        for section in report['sections']:
            for paragraph in section['paragraphs']:
                if relevant.intersection(paragraph['paper_ids']):
                    dependencies.update(paragraph['paper_ids'])
        def depends(raw,source):
            return raw['id'] in dependencies or (raw.get('paper_id') in dependencies
                and raw['kind'] in {'evidence','result'}) or (
                raw['kind'] in {'problem','mechanism','bottleneck'} and
                not raw.get('provenance','').startswith('scout:theory-gap') and
                any(source.get(eid,{}).get('paper_id') in dependencies
                    for eid in raw.get('evidence_ids',[])))
        current_raw={r.id:r.model_dump(mode='json') for r in records.values()}
        dependency_ids={rid for rid,raw in old.items() if depends(raw,old)}
        dependency_ids.update(rid for rid,raw in current_raw.items() if depends(raw,current_raw))
        current=[records[rid] for rid in sorted(dependency_ids) if rid in records]
        stale=not input_path.exists() or bool(dependency_ids-set(records))
        # Timestamps/revision counters are bookkeeping, scientific content is not.
        def content(raw):
            return {k:v for k,v in raw.items() if k not in {'created_at','updated_at','revision'}}
        for r in current:
            if r.id not in old or content(old[r.id])!=content(r.model_dump(mode='json')):
                stale=True
        sections=[]
        for section in report['sections']:
            paragraphs=[]
            for p in section['paragraphs']:
                if not relevant.intersection(p['paper_ids']):
                    continue
                # No fabricated IDs or wrong-owner evidence, even in cached prose.
                nodes=report['source_nodes']
                if any(pid not in nodes for pid in p['paper_ids']):
                    raise ValueError('Related-work paragraph has unknown source nodes')
                owners=set()
                for eid in p['evidence_ids']:
                    e=records.get(eid)
                    if not isinstance(e,Evidence):
                        raise ValueError('Related-work paragraph has unknown evidence')
                    owners.add(e.paper_id)
                full={pid for pid in p['paper_ids'] if isinstance(records.get(pid),Paper)}
                if not full<=owners or not owners<=set(p['paper_ids']):
                    raise ValueError('Related-work paragraph lacks attributable source evidence')
                paragraphs.append(p)
            if paragraphs:
                sections.append(dict(title=section['title'],paragraphs=paragraphs))
        used={pid for s in sections for p in s['paragraphs'] for pid in p['paper_ids']}
        return dict(status='STALE' if stale else 'CURRENT',sections=sections,
            source_fingerprint=report['input_fingerprint'],source_recorded_at=report['recorded_at'],
            source_nodes={pid:report['source_nodes'][pid] for pid in sorted(used)},
            missing_foundations=report['missing_foundations'],limitations=report['limitations'],
            reason='旧稿保留供查阅，新增或变化的来源尚未合并。' if stale else
                   '来源版本已对照；定理解释与承接关系仍需科学审查。')

    def _build(self,field,records,notes,memberships=None):
        from research_scout.comparison.field_comparison import compare_field_results
        for pid in field.paper_ids+field.context_paper_ids:
            if not isinstance(records.get(pid),Paper):
                raise ValueError(f'Unknown field paper: {pid}')
        for rid in field.result_ids+[i for b in field.branches for i in b.result_ids]:
            if not isinstance(records.get(rid),Result):
                raise ValueError(f'Unknown field result: {rid}')
        papers={p.id:p for p in records.values() if isinstance(p,Paper) and (
            p.id in field.paper_ids or (not set(p.labels)&set(field.exclude_labels) and
            (set(p.labels)&set(field.labels) or _match(field.match_terms,p.title))))}
        explicit_results=set(field.result_ids)|{rid for b in field.branches for rid in b.result_ids}
        results=[r for r in records.values() if isinstance(r,Result) and
                 (r.paper_id in papers or r.id in explicit_results)]
        if memberships is not None:
            results=[r for r in records.values() if isinstance(r,Result) and r.id in memberships[field.id]]
            if field.parent_id or field.result_match_terms:
                papers={r.paper_id:records[r.paper_id] for r in results}
        papers.update({r.paper_id:records[r.paper_id] for r in results})
        cards=[]
        for r in sorted(results,key=lambda r:(str(records[r.paper_id].published or ''),r.id)):
            v=records[r.version_id]
            paper=records[r.paper_id]
            warnings=[]
            newer=[records[vid] for vid in paper.version_ids
                   if vid!=v.id and records[vid].supersedes_version_id==v.id]
            if newer:
                warnings.append('存在后续来源快照：本结果保留旧版陈述，需复核。')
            if r.assessment_status.value=='NEEDS_REVIEW':
                warnings.append('规范记录标记为 NEEDS_REVIEW。')
            if not r.scope.quantifiers:
                warnings.append('量词尚未完整抽取。')
            if r.scope.unresolved:
                warnings+=r.scope.unresolved
            owned=[]
            for eid in r.evidence_ids:
                e=records.get(eid)
                if not isinstance(e,Evidence) or e.paper_id!=r.paper_id or e.version_id!=r.version_id:
                    raise ValueError(f'Result lacks its own version-specific evidence: {r.id}')
                ranks={'METADATA_ONLY':0,'ABSTRACT_ONLY':1,'PARTIAL_TEXT':2,'FULL_TEXT':3}
                if e.source_hash!=v.content_hash or ranks[e.coverage.value]>ranks[v.coverage.value]:
                    raise ValueError(f'Result evidence hash/coverage differs from source: {r.id}')
                owned.append(e.model_dump(mode='json'))
            source_status='ATTRIBUTED' if owned else 'MISSING_EVIDENCE'
            if not owned:
                warnings.append('无结果级证据；不能作为已支撑的定量结论。')
            if v.coverage.value not in {'FULL_TEXT','PARTIAL_TEXT'} or (owned and not any(
                    e['coverage'] in {'FULL_TEXT','PARTIAL_TEXT'} for e in owned)):
                warnings.append('仅有摘要或元数据；定理范围尚待全文核读。')
                source_status='METADATA_ONLY'
            if owned and any(e['coverage']=='PARTIAL_TEXT' for e in owned):
                warnings.append('部分证据仅覆盖已核读节选，完整假设仍需确认。')
            note=notes.get(r.id)
            if note and note.result_fingerprint!=result_fingerprint(r):
                warnings.append('结构化阅读备注对应旧结果版本，已停用。')
                note=None
            if note and not owned:
                warnings.append('结果自身缺少证据，阅读备注暂不作为定量支撑。')
                note=None
            text=r.title+' '+r.scope.model+' '+r.scope.objective
            branch_ids=[b.id for b in field.branches if r.id in b.result_ids or _match(b.match_terms,text)]
            mechanisms=[dict(id=mid,title=records[mid].title,principle=records[mid].principle,
                             construction=records[mid].construction) for mid in r.mechanism_ids]
            cards.append(dict(result_id=r.id,paper_id=r.paper_id,version_id=r.version_id,title=r.title,
                paper_title=paper.title,published=str(paper.published) if paper.published else None,
                version=v.version,source_hash=v.content_hash,coverage=v.coverage.value,
                source_status=source_status,synthetic=r.synthetic,branch_ids=branch_ids or ['unassigned'],
                result_type=r.result_type,statement=r.statement,scope=r.scope.model_dump(mode='json'),
                rate=r.rate,problem_ids=r.problem_ids,mechanisms=mechanisms,evidence=owned,
                verification_status=r.verification_status,assessment_status=r.assessment_status.value,
                result_fingerprint=result_fingerprint(r),details=note.model_dump(mode='json') if note else None,
                warnings=warnings))
        comparisons=[]
        by_id={r.id:r for r in results}
        for left,right in combinations(cards,2):
            shared=set(left['branch_ids'])&set(right['branch_ids'])-{'unassigned'}
            if not shared:
                continue
            comparison=compare_field_results(by_id[left['result_id']],by_id[right['result_id']])
            if left['warnings'] or right['warnings'] or any(
                    c['source_status']!='ATTRIBUTED' for c in (left,right)):
                comparison['status']='INSUFFICIENT_INFORMATION'
                comparison['unresolved']+=left['warnings']+right['warnings']
            comparisons.append(comparison)
        return dict(field=field.model_dump(mode='json'),papers=[dict(id=p.id,title=p.title,
            arxiv_id=p.arxiv_id,doi=p.doi,extraction_status=p.extraction_status) for p in sorted(papers.values(),key=lambda p:p.id)],
            results=cards,comparisons=comparisons,narrative=self._narrative(field,set(papers),records),
            policy='分支是组织标签，不表示假设等价；来源归属不等于数学验证；不生成优劣排名或 gap。')

    def update(self,field_id=None):
        registry=FieldRegistry.load(self.workspace)
        fields=[f for f in registry.fields if field_id is None or f.id==field_id]
        if not fields:
            raise ValueError(f'Unknown field: {field_id}')
        records={r.id:r for r in self.archive.list()}
        notes=self._notes(records)
        memberships=field_result_memberships(registry,records)
        # Validate every selected dossier before writing any of their projections.
        payloads=[self._build(f,records,notes,memberships) for f in fields]
        reports=[]
        for payload in payloads:
            directory=self.workspace/'fields'/payload['field']['id']
            latest=directory/'latest.json'
            previous=json.loads(latest.read_text()) if latest.exists() else None
            content_key=fingerprint(payload)
            if previous and previous['content_fingerprint']==content_key:
                # Regenerate human-readable projections without adding a revision.
                report=previous
            else:
                before={c['result_id']:c for c in previous['results']} if previous else {}
                after={c['result_id']:c for c in payload['results']}
                changes=dict(added=sorted(set(after)-set(before)),removed=sorted(set(before)-set(after)),
                    changed=sorted(k for k in set(after)&set(before) if after[k]!=before[k]),
                    configuration_changed=bool(previous and previous['field']!=payload['field']),
                    narrative_changed=bool(previous and previous['narrative']!=payload['narrative']),
                    comparisons_changed=bool(previous and previous['comparisons']!=payload['comparisons']))
                parent=previous['snapshot_id'] if previous else None
                key=fingerprint([content_key,parent])[:24]
                report=dict(payload,content_fingerprint=content_key,snapshot_id=key,previous_snapshot_id=parent,
                    recorded_at=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),changes=changes)
                retained=directory/'revisions'/f'{key}.json'
                if retained.exists():
                    saved=json.loads(retained.read_text())
                    if saved['content_fingerprint']!=content_key or saved['previous_snapshot_id']!=parent:
                        raise ValueError('Retained field snapshot conflicts with requested update')
                    report=saved
                else:
                    _atomic_json(retained,report)
                readable=retained.with_suffix('.md')
                if not readable.exists():
                    readable.write_text(self.markdown(report))
            directory.mkdir(parents=True,exist_ok=True)
            (directory/'latest.md').write_text(self.markdown(report))
            _atomic_json(latest,report)
            updated=previous is None or previous['snapshot_id']!=report['snapshot_id']
            update_changes=report['changes'] if updated else dict(added=[],changed=[],removed=[],
                configuration_changed=False,narrative_changed=False,comparisons_changed=False)
            reports.append(dict(report,updated=updated,update_changes=update_changes))
        self._index(registry)
        return reports

    def _index(self,registry):
        lines=['# 研究领域档案','','每个领域维护问题分支、逐结果定量表、Related Work 与版本更新。',
               '同一规范结果可被多个领域引用，不复制科学记录。','',
               '| 领域 | 上级领域 | 结果数 | Related Work | 档案 |','| --- | --- | --- | --- | --- |']
        for f in registry.fields:
            path=self.workspace/'fields'/f.id/'latest.json'
            report=json.loads(path.read_text()) if path.exists() else None
            lines.append(f'| {f.title} | {f.parent_id or "总览"} | {len(report["results"]) if report else 0} | '
                f'{report["narrative"]["status"] if report else "待建立"} | [{f.id}]({f.id}/latest.md) |')
        (self.workspace/'fields').mkdir(exist_ok=True)
        index=self.workspace/'fields'/'README.md'
        previous=index.read_text() if index.exists() else ''
        # Preserve manually maintained research-note sections below the generated table.
        tail='\n## '+previous.split('\n## ',1)[1] if '\n## ' in previous else ''
        index.write_text('\n'.join(lines)+'\n'+tail)

    @staticmethod
    def markdown(report):
        f=report['field']
        n=report['narrative']
        lines=['# '+f['title'],'',f['question'],'',report['policy'],'',
            f"快照：`{report['snapshot_id']}`；更新时间：{report['recorded_at']}",'',
            '## 问题分支','']
        if f.get('parent_id'):
            lines[4:4]=[f"上级领域：[{f['parent_id']}](../{f['parent_id']}/latest.md)", '']
        lines += [f"- **{b['title']}**：{b['question']}" for b in f['branches']]
        lines += ['- 未分支结果仍保留在比较表中；分支匹配不构成严格可比性判断。','',
                  '## Related Work','',f"状态：{n['status']}。{n['reason']}",'']
        for section in n['sections']:
            lines+=['### '+section['title'],'']
            for p in section['paragraphs']:
                refs=' '.join(f"[{n['source_nodes'][pid]['title']}]({n['source_nodes'][pid]['url']})"
                              for pid in p['paper_ids'])
                lines += [p['text'],'',refs,'','证据：'+', '.join(p['evidence_ids']),'']
        lines+=['## 逐结果定量比较','','不同误差指标、假设与成本口径不直接排序；空缺明确保留。','',
            '| 结果／来源版本 | 分支 | 指标与保证 | 维度／精度依赖 | oracle／总成本 | 初始化 | 核验状态 |',
            '| --- | --- | --- | --- | --- | --- | --- |']
        def cell(v):
            return str(v).replace('|','\\|').replace('\n',' ')
        for c in report['results']:
            d=c['details'] or {}
            s=c['scope']
            values=[f"[{c['title']}](#{c['result_id']}) / {c['paper_title']} ({c['version']})",
                ', '.join(c['branch_ids']),s['metric']+'；'+s['guarantee'],
                d.get('parameter_dependence') or c['rate'] or '未单独抽取；见保证与假设',
                (d.get('oracle') or '未单独抽取')+'；'+(d.get('total_cost') or '完整成本待核读'),
                d.get('initialization') or '未单独抽取；见逐条假设',
                c['result_type']+'；'+c['source_status']+'；'+c['verification_status']+('；待复核' if c['warnings'] else '')]
            lines+=['| '+' | '.join(map(cell,values))+' |']
        lines+=['','## 结果范围与证据','']
        for c in report['results']:
            s=c['scope']
            d=c['details'] or {}
            lines += [f"<a id=\"{c['result_id']}\"></a>", '### '+c['title'],'',
                f"规范 ID：`{c['result_id']}`；版本：`{c['version_id']}`；覆盖：{c['coverage']}；类型：{c['result_type']}",'',
                '**模型**：'+s['model'],'','**目标**：'+s['objective'],'','**陈述**：'+c['statement'],'',
                '**假设**：','']+['- '+a for a in s['assumptions']]
            lines += ['','**量词**：','']+['- '+q for q in (s['quantifiers'] or ['未抽取，不能宣称完整覆盖'])]
            lines += ['','**证明机制**：'+(d.get('proof_mechanism') or '；'.join(m['title']+'：'+m['principle'] for m in c['mechanisms']) or '待核读'),'']
            lines += ['**保留边界**：'+(d.get('boundary') or '；'.join(s['unresolved']) or '尚未完整梳理，不代表没有限制'),'']
            if d:
                lines += ['备注来源：'+d['provenance']+'；证据：'+', '.join(d['evidence_ids']),'']
            if c['synthetic']:
                lines+=['**SYNTHETIC：人工测试记录，不是真实文献。**','']
            lines += ['- 待核对：'+w for w in c['warnings']]
            lines += ['- 证据：`'+e['id']+'`，`'+e['locator']+'`，SHA-256 `'+str(e['source_hash'])+'`' for e in c['evidence']]
            lines+=['']
        lines+=['## 比较边界','','仅在同一组织分支内检查范围；措辞一致也不构成数学等价证明。',
                 '率的优劣统一为 UNASSESSED。','']
        for p in report['comparisons']:
            lines += [f"- `{p['left_result_id']}` ↔ `{p['right_result_id']}`：{p['status']}；"
                      +'差异：'+', '.join(p['differing_dimensions'])+'；待核对：'+'；'.join(p['unresolved'])]
        lines += ['','## 本次更新','']
        for key,label in [('added','新增结果'),('changed','结果或证据变更'),('removed','退出当前档案')]:
            lines += ['- '+label+'：'+(', '.join(report['changes'][key]) or '无')]
        lines += [f"- 领域定义变化：{report['changes']['configuration_changed']}；脉络变化：{report['changes']['narrative_changed']}；比较变化：{report['changes'].get('comparisons_changed',False)}",
            '- 历史快照保存在 revisions/；退出当前档案不删除规范记录。','',
            '## 待补读与缺失环节','']+['- '+s for s in n.get('missing_foundations',[])]
        return '\n'.join(lines)+'\n'
