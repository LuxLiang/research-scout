"""Retrieve history, stage extraction, validate attribution, then publish atomically."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from uuid import uuid4

from research_scout.comparison import ComparisonEngine
from research_scout.discovery import SourcePaper
from research_scout.domain.interfaces import ArchiveProtocol, ExtractionProvider
from research_scout.domain.models import (
    Application, AssessmentStatus, Coverage, Evidence, EventType, EvolutionEvent, Mechanism, Paper,
    Record, Relationship, RelationType, Result, ScientificClaim, parse_record, reference_ids, stable_id,
)
from research_scout.ingestion import IngestionOutcome, PaperIngestor
from .providers import ConfigurationError


@dataclass
class ProcessingOutcome:
    ingestion: IngestionOutcome
    records: list[Record] = field(default_factory=list)
    comparisons: list[Record] = field(default_factory=list)
    related_ids: list[str] = field(default_factory=list)
    stage_path: str | None = None

    @property
    def paper(self):
        return self.ingestion.paper

    @property
    def version(self):
        return self.ingestion.version


def _mechanism_key(mechanism: Mechanism) -> tuple:
    """Exact construction, required structures and assumptions define technical identity.

    Applicable models and proof roles describe uses of the construction; a new
    domain or role alone creates an Application, not a new Mechanism. Changing
    the construction or required structure is deliberately not auto-merged.
    """
    return (mechanism.principle, mechanism.construction, tuple(sorted(mechanism.structures)),
            tuple(sorted(mechanism.necessary_assumptions)))


class PaperPipeline:
    def __init__(self, archive: ArchiveProtocol, cache_dir: str | Path,
                 provider: ExtractionProvider | None = None, http_client=None):
        self.archive = archive
        self.ingestor = PaperIngestor(archive, cache_dir, http_client)
        self.provider = provider
        self.cache_dir = self.ingestor.cache_dir

    def process(self, source: str | Path | SourcePaper, extract: bool = True) -> ProcessingOutcome:
        if extract and self.provider is None:
            raise ConfigurationError("No extraction provider configured; request extract=False for metadata/source ingestion")
        ingested = self.ingestor.ingest(source)
        outcome = ProcessingOutcome(ingestion=ingested)
        if not extract:
            return outcome
        stage_path = self.cache_dir / "staging" / f"{ingested.version.id}.json"
        if stage_path.is_file():
            previous = json.loads(stage_path.read_text())
            if previous.get("status") == "PUBLISHED":
                outcome.records = [self.archive.get(record_id) for record_id in previous["record_ids"]
                                   if record_id != ingested.paper.id]
                outcome.stage_path = str(stage_path)
                outcome.comparisons = ComparisonEngine(self.archive).compare(ingested.paper.id)
                return outcome
        version, paper = ingested.version, ingested.paper
        if version.coverage == Coverage.METADATA_ONLY or not version.text_path:
            raise ValueError("No scientific source text available; metadata-only ingestion cannot extract claims")
        text = Path(version.text_path).read_text(encoding="utf-8")
        related = self._retrieve(paper)
        outcome.related_ids = [record.id for record in related]
        provider = self.provider
        if hasattr(provider, "extract_with_context"):
            records = provider.extract_with_context(paper, version, text, related)
        else:
            records = provider.extract(paper, version, text)
        records = [parse_record(record.model_dump(mode="json")) for record in records]
        try:
            records = self._reuse_mechanisms(records)
            self._validate(records, paper.id, version.id, text)
            records = self._add_applications(records, paper.id)
        except (ValueError, KeyError) as exc:
            rejected = stage_path.with_name(f"{version.id}.rejected-{uuid4().hex}.json")
            rejected.write_text(json.dumps({
                "status": "REJECTED", "reason": str(exc),
                "records": [record.model_dump(mode="json") for record in records],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
        labels = list(getattr(provider, "labels", []))
        envelope = getattr(provider, "last_envelope", None)
        if envelope:
            labels.extend(envelope.labels)
        links = {"problem_ids": "problem", "bottleneck_ids": "bottleneck", "mechanism_ids": "mechanism",
                 "result_ids": "result"}
        updates = {key: sorted(set(getattr(paper, key) + [record.id for record in records
                                                       if record.kind == kind]))
                   for key, kind in links.items()}
        # Reused mechanisms already occur in Result/Application references.
        updates["mechanism_ids"] = sorted(set(updates["mechanism_ids"] + [
            mechanism_id for record in records if isinstance(record, Result)
            for mechanism_id in record.mechanism_ids
        ]))
        if envelope:
            for field in ("research_questions", "methods", "proof_techniques", "contributions"):
                updates[field] = sorted(set(getattr(paper, field) + getattr(envelope, field)))
        updates.update(labels=sorted(set(paper.labels + labels)), extraction_status="EXTRACTED")
        updated_paper = paper.model_copy(update=updates)
        events = []
        if version.published or paper.published:
            for result in records:
                if isinstance(result, Result) and result.evidence_ids:
                    events.append(EvolutionEvent(
                        id=stable_id("event", f"extracted-new-result:{result.id}"),
                        title=f"Extracted result: {result.title}", event_type=EventType.NEW_RESULT,
                        subject_id=result.problem_ids[0] if result.problem_ids else result.id,
                        related_ids=[result.id] + result.mechanism_ids + result.bottleneck_ids,
                        scientific_date=version.published or paper.published,
                        paper_id=paper.id, version_id=version.id, scope=result.scope,
                        evidence_ids=result.evidence_ids, assessment_status=AssessmentStatus.PROPOSED,
                        rationale="Source-attributed extracted result; requires scientific review",
                        provenance="extraction pipeline", synthetic=result.synthetic,
                    ))
        batch = records + events + [updated_paper]
        stage = {"status": "VALIDATED", "record_ids": [r.id for r in batch],
                 "records": [record.model_dump(mode="json") for record in batch],
                 "related_ids": outcome.related_ids,
                 "limitations": envelope.limitations if envelope else []}
        self._write_stage(stage_path, stage)
        persisted = self.archive.put_many(batch)
        stage["status"] = "PUBLISHED"
        self._write_stage(stage_path, stage)
        outcome.ingestion.paper = next(record for record in persisted if record.id == paper.id)
        outcome.records = [record for record in persisted if record.id != paper.id]
        outcome.stage_path = str(stage_path)
        outcome.comparisons = ComparisonEngine(self.archive).compare(paper.id)
        return outcome

    @staticmethod
    def _write_stage(path: Path, data: dict):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def _retrieve(self, paper: Paper) -> list[Record]:
        records: dict[str, Record] = {}
        # Multiple exact words avoid a full-title AND query hiding historical context.
        words = [word for word in re.findall(r"[\w-]+", paper.title) if len(word) > 3][:8]
        for query in words + paper.labels[:8]:
            for record in self.archive.search(query):
                records[record.id] = record
                for neighbor in self.archive.traverse(record.id, depth=1):
                    records[neighbor.id] = neighbor
        for record_id in paper.problem_ids + paper.mechanism_ids + paper.bottleneck_ids:
            records[record_id] = self.archive.get(record_id)
            for record in self.archive.traverse(record_id, depth=2):
                records[record.id] = record
        return sorted(records.values(), key=lambda record: record.id)

    def _reuse_mechanisms(self, records: list[Record]) -> list[Record]:
        known = {_mechanism_key(record): record for record in self.archive.list("mechanism")}
        aliases = {}
        retained = []
        for record in records:
            if isinstance(record, Mechanism) and _mechanism_key(record) in known:
                aliases[record.id] = known[_mechanism_key(record)].id
            else:
                retained.append(record)
                if isinstance(record, Mechanism):
                    known[_mechanism_key(record)] = record
        if not aliases:
            return retained

        def rewrite(value, key=""):
            if isinstance(value, dict):
                return {field: rewrite(item, field) for field, item in value.items()}
            if isinstance(value, list):
                if key.endswith("_ids"):
                    return list(dict.fromkeys(aliases.get(item, item) for item in value))
                return [rewrite(item) for item in value]
            if isinstance(value, str) and key.endswith("_id"):
                return aliases.get(value, value)
            return value
        return [parse_record(rewrite(record.model_dump(mode="json"))) for record in retained]

    def _add_applications(self, records: list[Record], paper_id: str) -> list[Record]:
        """Persist extracted associations as qualified hypotheses, never global success claims."""
        additions = []
        applications = {(record.mechanism_id, record.problem_id, record.result_id)
                        for record in records if isinstance(record, Application)}
        relations = {(record.source_id, record.target_id, record.relation_type)
                     for record in records if isinstance(record, Relationship)}
        for result in records:
            if not isinstance(result, Result):
                continue
            pairs = [(paper_id, result.id, RelationType.PAPER_ESTABLISHES_RESULT)]
            pairs.extend((result.id, problem_id, RelationType.RESULT_ADDRESSES_PROBLEM)
                         for problem_id in result.problem_ids)
            pairs.extend((paper_id, problem_id, RelationType.PAPER_STUDIES_PROBLEM)
                         for problem_id in result.problem_ids)
            for mechanism_id in result.mechanism_ids:
                for problem_id in result.problem_ids:
                    key = (mechanism_id, problem_id, result.id)
                    if key not in applications:
                        additions.append(Application(
                            id=stable_id("application", ":".join(key)),
                            title=f"Extracted application of {mechanism_id} to {problem_id}",
                            mechanism_id=mechanism_id, problem_id=problem_id, result_id=result.id,
                            scope=result.scope, evidence_ids=result.evidence_ids,
                            assessment_status=AssessmentStatus.PROPOSED, synthetic=result.synthetic,
                            provenance="source-extracted association, not independently verified",
                        ))
                        applications.add(key)
                    pairs.append((mechanism_id, problem_id, RelationType.MECHANISM_APPLIED_TO_PROBLEM))
            for source_id, target_id, relation_type in pairs:
                key = (source_id, target_id, relation_type)
                if key in relations:
                    continue
                additions.append(Relationship(
                    id=stable_id("relation", f"{result.id}:{source_id}:{target_id}:{relation_type}"),
                    title=f"Extracted {relation_type}", source_id=source_id, target_id=target_id,
                    relation_type=relation_type, scope=result.scope, assumptions=result.scope.assumptions,
                    evidence_ids=result.evidence_ids, hypothesis=True,
                    assessment_status=AssessmentStatus.PROPOSED, synthetic=result.synthetic,
                    provenance="source-extracted association, not independently verified",
                ))
                relations.add(key)
        return records + additions

    def _validate(self, records: list[Record], paper_id: str, version_id: str, text: str):
        version = self.archive.get(version_id)
        existing = {record.id: record for record in self.archive.list()}
        staged = {record.id: record for record in records}
        if len(staged) != len(records):
            raise ValueError("Duplicate IDs in extraction batch")
        combined = existing | staged
        forbidden = {"paper", "paper_version", "comparison", "event", "resolution_assessment",
                     "breakthrough", "transfer", "opportunity", "entity_change"}
        for record in records:
            if record.kind in forbidden:
                raise ValueError(f"Extraction cannot author {record.kind} records")
            if record.assessment_status in {AssessmentStatus.INDEPENDENTLY_REVIEWED,
                                            AssessmentStatus.NEEDS_REVIEW} or record.review:
                raise ValueError("Model extraction cannot author independent review or promote scientific status")
            if record.id in existing:
                before = existing[record.id].model_dump(exclude={"created_at", "updated_at"})
                after = record.model_dump(exclude={"created_at", "updated_at"})
                if before != after:
                    raise ValueError("Extraction cannot overwrite an existing scientific record")
            missing = reference_ids(record) - set(combined)
            if missing:
                raise ValueError(f"Unresolved extraction references: {sorted(missing)}")
            if isinstance(record, Evidence):
                if record.paper_id != paper_id or record.version_id != version_id:
                    raise ValueError("Extraction evidence must pin current paper/version")
                if record.coverage != version.coverage or record.source_hash != version.content_hash:
                    raise ValueError("Evidence coverage/hash must match ingested source")
                locator = re.fullmatch(r"char:(\d+)-(\d+)", record.locator)
                if not locator or not record.quotation:
                    raise ValueError("Extraction evidence needs exact quotation and char:START-END locator")
                start, end = map(int, locator.groups())
                if not (0 <= start < end <= len(text)) or text[start:end] != record.quotation:
                    raise ValueError("Evidence quotation/locator is absent from the source text")
            elif record.kind not in {"topic", "problem_family", "mechanism_family"}:
                if not record.evidence_ids:
                    raise ValueError("Scientific extraction needs attributable evidence")
                evidence = [combined.get(item) for item in record.evidence_ids]
                if any(not isinstance(item, Evidence) for item in evidence):
                    raise ValueError("Scientific evidence references must identify Evidence records")
                if not any(item.version_id == version_id for item in evidence):
                    raise ValueError("New claims need support from the currently ingested version")
            if isinstance(record, (Result, ScientificClaim)) and record.version_id != version_id:
                raise ValueError("Extracted claims/results must pin current paper version")
            if isinstance(record, Result) and record.paper_id != paper_id:
                raise ValueError("Extracted result source identity mismatch")
            if isinstance(record, Result) and record.verification_status != "NOT_MATHEMATICALLY_VERIFIED":
                raise ValueError("Extraction cannot verify theorem correctness")
