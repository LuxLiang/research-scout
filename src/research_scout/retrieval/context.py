"""Research RAG: ranked leads plus version-pinned original source windows.

The complete scientific inventory is preserved by the caller. Retrieved passages
are source context, not canonical Evidence or a scientific assessment.
"""
from __future__ import annotations

from pathlib import Path

from .fusion import ResearchRetriever
from .sources import SourceIndex


class ResearchContext:
    def __init__(self, archive, cache_dir, *, semantic=None, reranker=None):
        self.records = archive.list()
        self.source_index = SourceIndex(Path(cache_dir) / 'retrieval' / 'sources.sqlite3')
        self.manifest = self.source_index.rebuild(self.records)
        self.semantic, self.reranker = semantic, reranker

    @staticmethod
    def _query(record):
        fields = ('principle', 'construction', 'proof_role', 'input_objects',
                  'output_guarantees', 'reusable_steps', 'structures', 'statement',
                  'desired_result', 'adaptation', 'bridge_statement', 'missing_lemmas')
        parts = []
        for field in fields:
            value = record.get(field)
            if isinstance(value, str) and value.strip():
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(v for v in value if isinstance(v, str) and v.strip())
        return ' '.join(dict.fromkeys(parts))

    def prepare(self, context):
        records = {r['id']: r for r in context['records']}
        retriever = ResearchRetriever(context['records'], semantic=self.semantic,
                                      reranker=self.reranker)
        focus = [records[t['source_mechanism_id']] for t in context['techniques_to_review']]
        queries = [(r['id'], self._query(r), r.get('structures', [])) for r in focus]
        # With no new papers the scheduled directions still receive traceable retrieval.
        if not queries:
            fields = context.get('field_index', {})
            for pair in context['field_pairs_to_review']:
                field = fields[pair['source_field_id']]
                queries.append((pair['source_field_id'], field['question'], []))
        paper_ids = [p['id'] for p in context['papers']]
        traces, passages = [], {}
        used_characters = 0
        for seed, query, structures in queries:
            hits = retriever.search(query, structures=structures, top_k=16,
                                    kinds=['problem', 'mechanism', 'result', 'bottleneck'])
            raw = self.source_index.search(query, top_k=6, paper_ids=paper_ids)
            raw = [{**self.source_index.get(p['id']), 'score': p['score']} for p in raw]
            selected = []
            for passage in raw:
                if passage['id'] in passages:
                    selected.append(passage['id'])
                elif used_characters + len(passage['parent_text']) <= 48_000:
                    passages[passage['id']] = passage
                    selected.append(passage['id'])
                    used_characters += len(passage['parent_text'])
            traces.append(dict(seed_id=seed, query=query, record_hits=hits,
                               passage_ids=selected, retrieved_passage_count=len(raw)))
        return dict(
            protocol='RRF_LEADS_AND_CHILD_TO_PARENT_SOURCES_V1',
            corpus_manifest=self.manifest, queries=traces, source_passages=list(passages.values()),
            semantic_enabled=self.semantic is not None, reranker_enabled=self.reranker is not None,
            inventory_record_count=len(records), inventory_preserved=True,
            coverage='Ranked source windows are partial reading context, not exhaustive full-text review.',
            passage_character_budget=48_000,
        )

    def reread(self, batch, context):
        """Use each candidate's proposed bridge to fetch source and target separately."""
        records = {r['id']: r for r in context['records']}
        evidence = {r['id']: r for r in context['records'] if r['kind'] == 'evidence'}
        passages, traces = {}, []
        for idea in batch.ideas:
            source = records[idea.source_result_id]
            target = records[idea.target_problem_id]
            target_evidence = [evidence[e] for e in target['evidence_ids'] if e in evidence]
            target_versions = {e['version_id'] for e in target_evidence}
            target_versions.update(records[r]['version_id'] for r in idea.target_result_ids)
            query = self._query(idea.model_dump()) + ' ' + self._query(target)
            for role, versions in [('source', [source['version_id']]),
                                   ('target', sorted(target_versions))]:
                # Version filters are explicit: never substitute another paper revision.
                found = self.source_index.search(query, top_k=2, version_ids=versions) if versions else []
                found = [{**self.source_index.get(p['id']), 'score': p['score']} for p in found]
                traces.append(dict(source_mechanism_id=idea.source_mechanism_id,
                    target_problem_id=idea.target_problem_id, role=role, version_ids=versions,
                    query=query, passage_ids=[p['id'] for p in found]))
                for passage in found:
                    passages[passage['id']] = passage
        return dict(queries=traces, source_passages=list(passages.values()),
                    original_source_grounding=bool(passages))
