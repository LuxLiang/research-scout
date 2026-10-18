"""Atomic snapshot archive.

CURRENT points at a fully fsynced immutable snapshot. Writers hold an advisory
process lock through read/validate/publication. Readers load one complete snapshot.
SQLite never participates in scientific commits: it is a disposable projection.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Callable, Iterable
import uuid

from research_scout.domain.models import (
    AssessmentStatus, BottleneckStatus, Coverage, EventType, EvolutionEvent,
    Paper, Record, RelationType, ResolutionKind, normalize_identifier, parse_record,
    reference_ids, stable_id, OPPORTUNITY_TRANSITIONS,
)


class ArchiveError(ValueError):
    """A proposed canonical update was rejected."""


class IntegrityError(ArchiveError):
    pass


class ConflictError(ArchiveError):
    pass


class DuplicateRecordError(ArchiveError):
    pass


DIRECTORIES = {
    "paper": "papers", "paper_version": "paper_versions", "topic": "topics",
    "problem_family": "problem_families", "problem": "problems",
    "bottleneck": "bottlenecks", "mechanism_family": "mechanism_families",
    "mechanism": "mechanisms", "mechanism_variant": "mechanism_variants",
    "application": "applications", "result": "results", "evidence": "evidence",
    "claim": "claims", "relation": "relations", "event": "events",
    "comparison": "comparisons", "resolution_assessment": "resolution_assessments",
    "breakthrough": "breakthroughs", "transfer": "transfers",
    "opportunity": "opportunities", "entity_change": "entity_changes",
}

# All declared scientific relationship endpoints are checked before publication.
ENDPOINTS = {
    RelationType.PAPER_STUDIES_PROBLEM: ({"paper"}, {"problem"}),
    RelationType.PAPER_INTRODUCES_MECHANISM: ({"paper"}, {"mechanism"}),
    RelationType.PAPER_ESTABLISHES_RESULT: ({"paper"}, {"result"}),
    RelationType.PROBLEM_HAS_SUBPROBLEM: ({"problem"}, {"problem"}),
    RelationType.PROBLEM_LIMITED_BY_BOTTLENECK: ({"problem"}, {"bottleneck"}),
    RelationType.MECHANISM_VARIANT_OF: ({"mechanism_variant"}, {"mechanism"}),
    RelationType.MECHANISM_ADDRESSES_BOTTLENECK: ({"mechanism"}, {"bottleneck"}),
    RelationType.RESULT_ADDRESSES_PROBLEM: ({"result"}, {"problem"}),
    RelationType.RESULT_OVERCOMES_BOTTLENECK: ({"result"}, {"bottleneck"}),
    RelationType.MECHANISM_APPLIED_TO_PROBLEM: ({"mechanism"}, {"problem"}),
    RelationType.MECHANISM_TRANSFER_ATTEMPT: ({"mechanism"}, {"problem"}),
}
for _relation in (
    RelationType.RESULT_IMPROVES_RESULT, RelationType.RESULT_GENERALIZES_RESULT,
    RelationType.RESULT_WEAKENS_ASSUMPTIONS, RelationType.RESULT_CHALLENGES_RESULT,
):
    ENDPOINTS[_relation] = ({"result"}, {"result"})

TYPED_FIELDS = {
    "paper_id": {"paper"}, "paper_ids": {"paper"},
    "version_id": {"paper_version"}, "version_ids": {"paper_version"},
    "previous_version_id": {"paper_version"}, "supersedes_version_id": {"paper_version"},
    "invalidated_by_version_id": {"paper_version"},
    "topic_id": {"topic"}, "problem_id": {"problem"}, "problem_ids": {"problem"},
    "source_problem_id": {"problem"}, "target_problem_id": {"problem"},
    "analogous_problem_ids": {"problem"}, "bottleneck_ids": {"bottleneck"},
    "source_bottleneck_id": {"bottleneck"}, "target_bottleneck_id": {"bottleneck"},
    "mechanism_id": {"mechanism"}, "mechanism_ids": {"mechanism"},
    "source_mechanism_id": {"mechanism"}, "previous_mechanisms": {"mechanism"},
    "new_mechanism_ids": {"mechanism"}, "addressing_mechanism_ids": {"mechanism"},
    "overcoming_mechanism_ids": {"mechanism"}, "variant_ids": {"mechanism_variant"},
    "variant_id": {"mechanism_variant"}, "result_id": {"result"},
    "result_ids": {"result"}, "new_result_id": {"result"},
    "historical_results": {"result"}, "compared_result_ids": {"result"},
    "previous_result_ids": {"result"}, "known_result_ids": {"result"},
    "closest_result_ids": {"result"}, "event_ids": {"event"},
    "previous_event_ids": {"event"}, "evidence_ids": {"evidence"},
    "breakthrough_id": {"breakthrough"}, "transfer_id": {"transfer"},
    "previous_transfer_id": {"transfer"},
}


def _canonical(record: Record) -> str:
    return json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def _content(record: Record) -> dict:
    return record.model_dump(mode="json", exclude={"revision", "created_at", "updated_at"})


def _paper_keys(paper: Paper) -> set[str]:
    keys = set()
    if paper.doi:
        keys.add("doi:" + normalize_identifier(paper.doi))
    if paper.arxiv_id:
        keys.add("arxiv:" + _arxiv(paper.arxiv_id))
    for alias in paper.aliases:
        normalized = normalize_identifier(alias)
        if normalized.startswith("10."):
            keys.add("doi:" + normalized)
        elif "arxiv" in alias.lower():
            keys.add("arxiv:" + _arxiv(alias))
    return keys


def _arxiv(value: str) -> str:
    value = re.sub(r"^https?://arxiv.org/(?:abs|pdf)/", "", value.strip(), flags=re.I)
    value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    return re.sub(r"v\d+$", "", value.removesuffix(".pdf").lower())


class Archive:
    """Local-first archive. Record IDs and aliases remain independent of paths."""

    def __init__(self, root: str | Path, *, index_path: str | Path | None = None):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "snapshots").mkdir(exist_ok=True)
        self.index_path = Path(index_path).expanduser().resolve() if index_path else self.root / "index.sqlite3"
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _lock(self):
        # Exclusive even for reads simplifies recovery and works across instances.
        with (self.root / ".archive.lock").open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _generation(self) -> str | None:
        pointer = self.root / "CURRENT"
        if not pointer.exists():
            return None
        generation = pointer.read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[a-f0-9]{32}", generation):
            raise IntegrityError("invalid canonical CURRENT pointer")
        if not (self.root / "snapshots" / generation).is_dir():
            raise IntegrityError("canonical snapshot missing; refusing projection fallback")
        return generation

    def _load(self) -> dict[str, Record]:
        generation = self._generation()
        if not generation:
            return {}
        records = {}
        for path in sorted((self.root / "snapshots" / generation / "records").glob("*/*.json")):
            record = parse_record(json.loads(path.read_text(encoding="utf-8")))
            if record.id in records:
                raise IntegrityError(f"duplicate canonical ID: {record.id}")
            records[record.id] = record
        return records

    def _aliases(self, records: dict[str, Record]) -> dict[str, str]:
        aliases = {record.id: record.id for record in records.values()}
        for record in records.values():
            for alias in record.aliases:
                key = normalize_identifier(alias)
                if key in aliases and aliases[key] != record.id:
                    raise DuplicateRecordError(f"alias {alias!r} belongs to {aliases[key]}")
                aliases[key] = record.id
        # Historical source IDs still resolve to their source record. An explicit
        # follow_merges lookup provides the consolidated current entity instead.
        return aliases

    def resolve_id(self, identifier: str, *, follow_merges: bool = False) -> str:
        with self._lock():
            records = self._load()
            result = self._resolve(identifier, records)
            if follow_merges:
                seen = set()
                while result not in seen:
                    seen.add(result)
                    changes = [x for x in records.values() if x.kind == "entity_change"
                               and x.operation == "MERGE" and result in x.source_ids]
                    if not changes:
                        break
                    result = max(changes, key=lambda x: x.created_at).target_ids[0]
            return result

    def _resolve(self, identifier: str, records: dict[str, Record]) -> str:
        if identifier in records:
            return identifier
        found = self._aliases(records).get(normalize_identifier(identifier))
        if found:
            return found
        paper = self._find_paper(identifier, records)
        if paper:
            return paper.id
        raise KeyError(identifier)

    def _find_paper(self, identifier: str, records: dict[str, Record]) -> Paper | None:
        normalized = normalize_identifier(identifier)
        keys = {"doi:" + normalized, "arxiv:" + _arxiv(identifier)}
        for record in records.values():
            if isinstance(record, Paper) and (_paper_keys(record) & keys):
                return record
        return None

    def find_paper(self, identifier: str) -> Paper | None:
        with self._lock():
            return self._find_paper(identifier, self._load())

    def get(self, record_id: str) -> Record:
        with self._lock():
            records = self._load()
            return records[self._resolve(record_id, records)]

    def list(self, kind: str | None = None) -> list[Record]:
        if kind is not None and kind not in DIRECTORIES:
            raise ValueError(f"unknown record kind {kind!r}; use singular kinds")
        with self._lock():
            return [record for record in self._load().values() if kind is None or record.kind == kind]

    def put(self, record: Record) -> Record:
        return self.put_many([record])[0]

    def put_many(self, records: Iterable[Record]) -> list[Record]:
        incoming = [parse_record(record.model_dump(mode="json")) for record in records]
        with self._lock():
            current = self._load()
            return self._put_many(incoming, current)

    def _put_many(self, incoming: list[Record], current: dict[str, Record],
                  operation: str = "PUT") -> list[Record]:
        changed = []
        output = []
        proposed = dict(current)
        batch_ids = set()
        for record in incoming:
            if record.id in batch_ids:
                raise DuplicateRecordError(f"duplicate ID in batch: {record.id}")
            batch_ids.add(record.id)
            old = current.get(record.id)
            if old:
                if old.kind != record.kind:
                    raise IntegrityError(f"cannot change entity kind for {record.id}")
                if _content(old) == _content(record):
                    output.append(old)
                    continue
                if record.kind in {"event", "paper_version", "evidence", "entity_change"}:
                    raise IntegrityError(f"{record.kind} records are immutable; append a new record")
                if record.kind == "opportunity":
                    if record.history[:len(old.history)] != old.history:
                        raise IntegrityError("opportunity history is append-only")
                    if record.status != old.status:
                        if record.status not in OPPORTUNITY_TRANSITIONS[old.status]:
                            raise IntegrityError("invalid opportunity lifecycle transition")
                        if not record.history or len(record.history) <= len(old.history):
                            raise IntegrityError("lifecycle transition requires appended reasoning")
                        entry = record.history[-1]
                        if entry.get("from") != old.status or entry.get("to") != record.status or not entry.get("reason", "").strip():
                            raise IntegrityError("lifecycle transition requires matching states and reason")
                    if old.rejection_reason and record.rejection_reason != old.rejection_reason:
                        raise IntegrityError("rejection reasons must be retained")
                if record.kind == "transfer" and old.outcome == "FAILED":
                    if record.outcome != "FAILED" or record.failure_reason != old.failure_reason:
                        raise IntegrityError("failed transfer reasons are retained; append a new hypothesis")
                if record.revision != old.revision:
                    raise ConflictError(f"stale revision of {record.id}: expected {old.revision}")
                record = parse_record({**record.model_dump(mode="json"),
                                       "revision": old.revision + 1,
                                       "created_at": old.created_at,
                                       "updated_at": datetime.now(timezone.utc)})
            elif record.revision != 1:
                raise ConflictError("new records must start at revision 1")
            proposed[record.id] = record
            output.append(record)
            changed.append(record)
        self._validate_records(proposed)
        for record in changed:
            if record.kind == "event" and record.event_type == EventType.SUPPORTED_RESOLUTION:
                self._validate_resolution_event(record, proposed)
        if changed:
            self._publish(proposed, changed, operation)
        return output

    def _validate_records(self, records: dict[str, Record]) -> None:
        self._aliases(records)
        identities = {}
        versions = {}
        for record in records.values():
            missing = reference_ids(record) - records.keys()
            if missing:
                raise IntegrityError(f"{record.id}: missing references {sorted(missing)}")
            self._validate_typed(record.model_dump(mode="json"), records, record.id)
            if isinstance(record, Paper):
                if any(records[x].paper_id != record.id for x in record.version_ids):
                    raise IntegrityError("paper version list contains a version of another paper")
                for identity in _paper_keys(record):
                    if identity in identities and identities[identity] != record.id:
                        raise DuplicateRecordError(f"paper identity {identity} already belongs to "
                                                   f"{identities[identity]}")
                    identities[identity] = record.id
            if record.kind == "paper_version":
                key = (record.paper_id, record.version)
                if key in versions:
                    raise DuplicateRecordError(f"duplicate paper/version {key}")
                versions[key] = record.id
                if record.supersedes_version_id:
                    prior = records[record.supersedes_version_id]
                    if prior.paper_id != record.paper_id or prior.id == record.id:
                        raise IntegrityError("version supersession must reference an older same-paper version")
            if record.kind in {"evidence", "result", "claim", "event", "comparison"}:
                version = records[record.version_id]
                if hasattr(record, "paper_id") and version.paper_id != record.paper_id:
                    raise IntegrityError(f"{record.id}: version belongs to another paper")
            if record.kind == "relation":
                source_kinds, target_kinds = ENDPOINTS[record.relation_type]
                if (records[record.source_id].kind not in source_kinds
                        or records[record.target_id].kind not in target_kinds):
                    raise IntegrityError(f"{record.id}: invalid typed relationship endpoints")
            if record.kind == "problem" and record.family_id:
                self._assert_kind(records, record.family_id, {"problem_family"}, record.id)
            if record.kind == "mechanism" and record.family_id:
                self._assert_kind(records, record.family_id, {"mechanism_family"}, record.id)
            if record.kind == "application" and record.variant_id:
                variant = records[record.variant_id]
                if variant.mechanism_id != record.mechanism_id:
                    raise IntegrityError("application variant belongs to another mechanism")
            self._scientific_gates(record, records)
        self._validate_event_history(records)

    @staticmethod
    def _assert_kind(records, identifier, kinds, owner):
        if records[identifier].kind not in kinds:
            raise IntegrityError(f"{owner}: {identifier} must have kind {sorted(kinds)}")

    def _validate_typed(self, value, records, owner):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in TYPED_FIELDS:
                    for identifier in item if isinstance(item, list) else [item]:
                        if identifier is not None:
                            self._assert_kind(records, identifier, TYPED_FIELDS[key], owner)
                else:
                    self._validate_typed(item, records, owner)
        elif isinstance(value, list):
            for item in value:
                self._validate_typed(item, records, owner)

    def _scientific_gates(self, record, records):
        evidence = [records[identifier] for identifier in record.evidence_ids]
        if record.kind in {"claim", "result", "event", "relation", "resolution_assessment",
                           "breakthrough"} and record.assessment_status in {
            AssessmentStatus.SUPPORTED_BY_SOURCE, AssessmentStatus.INDEPENDENTLY_REVIEWED,
        } and not evidence:
            raise IntegrityError(f"{record.id}: scientific promotion requires source evidence")
        if record.assessment_status == AssessmentStatus.INDEPENDENTLY_REVIEWED:
            review = record.review
            if not review or not review.reviewer.strip() or not review.rationale.strip():
                raise IntegrityError(f"{record.id}: independent review must identify reviewer and rationale")
            if not set(review.evidence_ids).issubset(record.evidence_ids):
                raise IntegrityError(f"{record.id}: review evidence must be attached to record")
            if record.kind in {"claim", "result", "event", "relation", "resolution_assessment",
                               "breakthrough"} and any(
                x.coverage in {Coverage.METADATA_ONLY, Coverage.ABSTRACT_ONLY} for x in evidence
            ):
                raise IntegrityError(f"{record.id}: abstract/metadata evidence cannot support independent "
                                     "scientific review")
        if record.kind in {"claim", "result", "event"}:
            for item in evidence:
                if item.version_id != record.version_id:
                    raise IntegrityError(f"{record.id}: source evidence must pin the same paper version")
        if record.kind == "bottleneck" and record.status == BottleneckStatus.ESTABLISHED_BOTTLENECK:
            if record.assessment_status not in {AssessmentStatus.SUPPORTED_BY_SOURCE,
                                               AssessmentStatus.INDEPENDENTLY_REVIEWED}:
                raise IntegrityError("established bottleneck requires a supported assessment")
        if record.kind == "event" and record.event_type == EventType.SUPPORTED_RESOLUTION:
            supported = {AssessmentStatus.SUPPORTED_BY_SOURCE, AssessmentStatus.INDEPENDENTLY_REVIEWED}
            if (record.resolution != ResolutionKind.FULL_RESOLUTION_SUPPORTED
                    or record.assessment_status not in supported):
                raise IntegrityError("supported resolution requires a supported full-resolution assessment")
        if record.kind == "evidence":
            version = records[record.version_id]
            if record.source_hash and version.content_hash and record.source_hash != version.content_hash:
                raise IntegrityError("evidence content hash does not match its exact source version")
            coverage_rank = {Coverage.METADATA_ONLY: 0, Coverage.ABSTRACT_ONLY: 1,
                             Coverage.PARTIAL_TEXT: 2, Coverage.FULL_TEXT: 3}
            if coverage_rank[record.coverage] > coverage_rank[version.coverage]:
                raise IntegrityError("evidence coverage exceeds source version coverage")

    @staticmethod
    def _covers_original(achieved, original):
        return (bool(original.quantifiers) and bool(achieved.quantifiers)
                and all(getattr(achieved, key) == getattr(original, key) for key in (
            "domain", "model", "objective", "metric", "guarantee", "quantifiers",
        )) and set(achieved.assumptions) <= set(original.assumptions) and not achieved.unresolved)

    def _validate_resolution_event(self, record, records):
        """Check append-time qualification; later corrections retain this history.

        The current timeline re-evaluates the current result revisions. A changed
        scientific assessment must not make an old append-only event unstoreable.
        """
        supported = {AssessmentStatus.SUPPORTED_BY_SOURCE, AssessmentStatus.INDEPENDENTLY_REVIEWED}
        problem = records[record.subject_id]
        candidates = [records[x] for x in record.related_ids if records[x].kind == "result"]
        for identifier in record.related_ids:
            if records[identifier].kind == "resolution_assessment":
                assessment = records[identifier]
                if assessment.problem_id == record.subject_id:
                    candidates.append(records[assessment.result_id])
        def usable(result):
            evidence = [records[x] for x in result.evidence_ids]
            return (result.assessment_status in supported and result.result_type != "EMPIRICAL"
                    and self._covers_original(result.scope, record.scope)
                    and record.subject_id in result.problem_ids and result.version_id == record.version_id
                    and bool(evidence) and all(
                        x.coverage in {Coverage.FULL_TEXT, Coverage.PARTIAL_TEXT}
                        and x.assessment_status in supported for x in evidence))
        event_evidence = [records[x] for x in record.evidence_ids]
        if (problem.kind != "problem" or not self._covers_original(record.scope, problem.scope)
                or not any(usable(x) for x in candidates)
                or any(x.coverage in {Coverage.ABSTRACT_ONLY, Coverage.METADATA_ONLY}
                       or x.assessment_status not in supported for x in event_evidence)):
            raise IntegrityError("supported resolution needs an exact original-scope source-supported "
                                 "result and text evidence")

    def _validate_event_history(self, records):
        visiting = set()
        visited = set()
        def visit(event):
            if event.id in visiting:
                raise IntegrityError("evolution event history contains a cycle")
            if event.id in visited:
                return
            visiting.add(event.id)
            for identifier in event.previous_event_ids:
                prior = records[identifier]
                if prior.subject_id != event.subject_id:
                    raise IntegrityError("previous event must describe the same subject")
                if prior.scientific_date > event.scientific_date:
                    raise IntegrityError("previous event cannot have a later scientific date")
                visit(prior)
            visiting.remove(event.id)
            visited.add(event.id)
        for record in records.values():
            if isinstance(record, EvolutionEvent):
                visit(record)

    @staticmethod
    def _write(path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _fsync_directory(path):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _publish(self, records, changed, operation):
        generation = uuid.uuid4().hex
        staging = self.root / (".staging-" + generation)
        previous = self._generation()
        try:
            if previous:
                shutil.copytree(self.root / "snapshots" / previous, staging)
            else:
                staging.mkdir()
            for record in changed:
                text = _canonical(record)
                # Hashing filenames prevents platform-specific IDs becoming paths.
                filename = hashlib.sha256(record.id.encode()).hexdigest() + ".json"
                self._write(staging / "records" / DIRECTORIES[record.kind] / filename, text)
                self._write(staging / "history" / filename[:-5] / f"{record.revision:08}.json", text)
            audit_path = staging / "audit.json"
            audit = json.loads(audit_path.read_text()) if audit_path.exists() else []
            audit.append({"transaction": generation, "previous": previous, "operation": operation,
                          "timestamp": datetime.now(timezone.utc).isoformat(),
                          "records": [{"id": x.id, "revision": x.revision} for x in changed]})
            self._write(audit_path, json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
            for directory, _, filenames in os.walk(staging, topdown=False):
                for filename in filenames:
                    with (Path(directory) / filename).open("rb") as handle:
                        os.fsync(handle.fileno())
                self._fsync_directory(directory)
            os.replace(staging, self.root / "snapshots" / generation)
            self._fsync_directory(self.root / "snapshots")
            temporary_pointer = self.root / (".CURRENT-" + generation)
            self._write(temporary_pointer, generation + "\n")
            os.replace(temporary_pointer, self.root / "CURRENT")
            self._fsync_directory(self.root)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        # Projection writes are lazy so a successful scientific commit cannot be
        # reported failed due only to an unavailable/corrupt SQLite index.

    def history(self, record_id: str) -> list[Record]:
        with self._lock():
            records = self._load()
            identifier = self._resolve(record_id, records)
            filename = hashlib.sha256(identifier.encode()).hexdigest()
            directory = self.root / "snapshots" / self._generation() / "history" / filename
            return [parse_record(json.loads(x.read_text())) for x in sorted(directory.glob("*.json"))]

    def audit(self) -> list[dict]:
        with self._lock():
            generation = self._generation()
            if not generation:
                return []
            return json.loads((self.root / "snapshots" / generation / "audit.json").read_text())

    def validate(self) -> list[str]:
        with self._lock():
            try:
                self._validate_records(self._load())
                return []
            except (ValueError, KeyError, OSError) as exc:
                return [str(exc)]

    def _rebuild(self, records):
        temporary = self.index_path.parent / (".index-" + uuid.uuid4().hex + ".sqlite3")
        try:
            with sqlite3.connect(temporary) as db:
                db.executescript("""
                    CREATE TABLE meta (generation TEXT);
                    CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL);
                    CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED, title, body);
                    CREATE TABLE edges (source TEXT, target TEXT, relation TEXT);
                """)
                db.execute("INSERT INTO meta VALUES (?)", (self._generation(),))
                for record in records.values():
                    data = _canonical(record)
                    db.execute("INSERT INTO records VALUES (?, ?, ?)", (record.id, record.kind, data))
                    db.execute("INSERT INTO search VALUES (?, ?, ?)", (record.id, record.title, data))
                    for identifier in reference_ids(record):
                        db.execute("INSERT INTO edges VALUES (?, ?, ?)",
                                   (record.id, identifier, record.kind))
                db.commit()
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary, self.index_path)
            self._fsync_directory(self.index_path.parent)
        finally:
            temporary.unlink(missing_ok=True)
        return len(records)

    def rebuild(self) -> int:
        with self._lock():
            records = self._load()
            self._validate_records(records)
            return self._rebuild(records)

    def _ensure_index(self, records):
        try:
            with sqlite3.connect(self.index_path) as db:
                if db.execute("SELECT generation FROM meta").fetchone() != (self._generation(),):
                    self._rebuild(records)
                else:
                    # quick_check detects truncated/corrupted pages beyond metadata.
                    if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                        self._rebuild(records)
        except sqlite3.DatabaseError:
            self._rebuild(records)

    def search(self, query: str, labels: list[str] | None = None) -> list[Record]:
        with self._lock():
            records = self._load()
            self._ensure_index(records)
            result_ids = []
            if query.strip():
                try:
                    exact = self._resolve(query, records)
                    result_ids.append(exact)
                except KeyError:
                    pass
                tokens = re.findall(r"\w+", query, flags=re.UNICODE)
                if tokens:
                    expression = " OR ".join('"' + x.replace('"', '""') + '"' for x in tokens)
                    with sqlite3.connect(self.index_path) as db:
                        result_ids.extend(row[0] for row in db.execute(
                            "SELECT id FROM search WHERE search MATCH ? ORDER BY bm25(search)",
                            (expression,),
                        ))
            else:
                result_ids.extend(records)
            seen = set()
            result = []
            for identifier in result_ids:
                if identifier not in seen and (not labels or set(labels).issubset(records[identifier].labels)):
                    seen.add(identifier)
                    result.append(records[identifier])
            return result

    def traverse(self, entity_id: str, depth: int = 1) -> list[Record]:
        """Undirected reference/relationship traversal; excludes the starting record."""
        if depth < 0:
            raise ValueError("depth must be nonnegative")
        with self._lock():
            records = self._load()
            identifier = self._resolve(entity_id, records)
            adjacent = {x: set() for x in records}
            for record in records.values():
                for other in reference_ids(record):
                    adjacent[record.id].add(other)
                    adjacent[other].add(record.id)
                if record.kind == "relation":
                    adjacent[record.source_id].add(record.target_id)
                    adjacent[record.target_id].add(record.source_id)
            queue = deque([(identifier, 0)])
            seen = {identifier}
            result = []
            while queue:
                current, distance = queue.popleft()
                if distance == depth:
                    continue
                for other in sorted(adjacent[current]):
                    if other not in seen:
                        seen.add(other)
                        result.append(records[other])
                        queue.append((other, distance + 1))
            return result

    def merge(self, source_ids: list[str], target_id: str, rationale: str) -> Record:
        """Record consolidation without rewriting historical references or deleting sources."""
        from research_scout.domain.models import EntityChange
        if not rationale.strip() or not source_ids or target_id in source_ids:
            raise IntegrityError("merge requires distinct sources, target, and rationale")
        with self._lock():
            records = self._load()
            sources = [self._resolve(x, records) for x in source_ids]
            target = self._resolve(target_id, records)
            if target in sources or any(records[x].kind != records[target].kind for x in sources):
                raise IntegrityError("merge requires distinct entities of the same kind")
            if records[target].kind in {"event", "paper_version", "evidence", "entity_change"}:
                raise IntegrityError("source-version and historical records cannot be merged")
            # Reject cycles in the explicit consolidation graph.
            edges = {}
            for item in records.values():
                if item.kind == "entity_change" and item.operation == "MERGE":
                    edges.update({source: item.target_ids[0] for source in item.source_ids})
            for source in sources:
                node = target
                seen = {source}
                while node in edges:
                    if node in seen:
                        raise IntegrityError("merge cycle")
                    seen.add(node)
                    node = edges[node]
                if node == source:
                    raise IntegrityError("merge cycle")
                if source in edges and edges[source] != target:
                    raise IntegrityError("entity already merged; merge its current target instead")
            identity = json.dumps([sorted(sources), target, rationale])
            change = EntityChange(id=stable_id("change", identity), title="Entity consolidation",
                                  operation="MERGE", source_ids=sources, target_ids=[target],
                                  rationale=rationale)
            return self._put_many([change], records, "MERGE")[0]

    def split(self, source_id: str, targets: list[Record], rationale: str) -> Record:
        """Append split targets and a mapping. Ambiguous historical references stay historical."""
        from research_scout.domain.models import EntityChange
        if len(targets) < 2 or not rationale.strip():
            raise IntegrityError("split requires at least two target entities and rationale")
        with self._lock():
            records = self._load()
            source = records[self._resolve(source_id, records)]
            if source.kind in {"event", "paper_version", "evidence", "entity_change"}:
                raise IntegrityError("historical source records cannot be split")
            if any(x.kind != source.kind or x.id == source.id for x in targets):
                raise IntegrityError("split targets must be distinct entities of the source kind")
            change = EntityChange(id=stable_id("change", json.dumps([
                source.id, sorted(x.id for x in targets), rationale,
            ])), title="Entity split", operation="SPLIT", source_ids=[source.id],
                target_ids=[x.id for x in targets], rationale=rationale)
            self._put_many([*targets, change], records, "SPLIT")
            return change

    def migrate(self, transform: Callable[[dict], dict], *, target_version: str = "1.0") -> int:
        """Validate and atomically publish a schema-preserving migration.

        Future schema upgrades install new domain parsers first. This version can
        migrate legacy field values into the current 1.0 schema; immutable source
        and history records may not change. Invalid migrations publish nothing.
        """
        if target_version != "1.0":
            raise IntegrityError("install a parser for the requested schema before migrating")
        with self._lock():
            records = self._load()
            transformed = []
            for record in records.values():
                data = transform(record.model_dump(mode="json"))
                if data.get("id") != record.id or data.get("kind") != record.kind:
                    raise IntegrityError("migration may not change identity or entity kind")
                transformed.append(parse_record(data))
            changed = sum(_content(x) != _content(records[x.id]) for x in transformed)
            self._put_many(transformed, records, "MIGRATION")
            return changed
