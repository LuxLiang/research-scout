"""Disposable, source-pinned small-to-big retrieval over local paper texts.

Inspired by child/parent retrieval in LlamaIndex and explicit source metadata in
Haystack. These are reading candidates, not canonical Evidence or verification.
Character offsets address the exact decoded text cache, never PDF page numbers.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Iterable

from research_scout.domain.models import Paper, PaperVersion, Record


CHILD_SIZE = 1200
PARENT_SIZE = 4800
INDEX_SCHEMA = 3


def _spans(text: str, start: int, end: int, size: int):
    """Prefer nearby word boundaries without normalizing the source text."""
    while start < end:
        stop = min(start + size, end)
        if stop < end:
            boundaries = list(re.finditer(r"\s+", text[start + size * 4 // 5:stop]))
            if boundaries:
                stop = start + size * 4 // 5 + boundaries[-1].end()
        yield start, stop
        start = stop


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _version_key(version: PaperVersion, paper: Paper | None) -> tuple:
    order = paper.version_ids if paper else []
    # Content hashes describe snapshots, not scientific version numbers. For
    # snapshots of the same revision, the canonical paper ordering is authoritative.
    base_version = version.version.split("+content-", 1)[0]
    natural = tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                    for part in re.findall(r"\d+|\D+", base_version))
    return (natural, order.index(version.id) if version.id in order else -1,
            version.published.isoformat() if version.published else "", version.id)


class SourceIndex:
    """Persistent FTS5 projection; rebuild publishes a complete generation atomically."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def rebuild(self, records: Iterable[Record]) -> dict:
        records = list(records)
        papers = {record.id: record for record in records if isinstance(record, Paper)}
        versions = sorted((record for record in records if isinstance(record, PaperVersion)),
                          key=lambda version: version.id)
        by_paper: dict[str, list[PaperVersion]] = {}
        for version in versions:
            by_paper.setdefault(version.paper_id, []).append(version)
        latest: dict[str, PaperVersion] = {}
        for paper_id, history in by_paper.items():
            superseded = {version.supersedes_version_id for version in history}
            # Consider source-independent canonical history first. Even a missing
            # newest source suppresses older snapshots in default current searches.
            leaves = [version for version in history if version.id not in superseded]
            latest[paper_id] = max(leaves or history,
                                   key=lambda version: _version_key(version, papers.get(paper_id)))

        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp",
                                                dir=self.path.parent)
        os.close(descriptor)
        missing: list[str] = []
        errors: list[dict] = []
        fingerprints: list[dict] = []
        indexed_versions = indexed_chunks = 0
        try:
            with closing(sqlite3.connect(temporary)) as connection, connection:
                connection.executescript("""
                    CREATE TABLE parents (
                        id TEXT PRIMARY KEY, start INTEGER, end INTEGER, text TEXT
                    );
                    CREATE TABLE chunks (
                        id TEXT PRIMARY KEY, paper_id TEXT, version_id TEXT,
                        source_hash TEXT, text_hash TEXT, start INTEGER, end INTEGER,
                        text TEXT, parent_id TEXT, coverage TEXT, source_currentness TEXT
                    );
                    CREATE INDEX chunks_version ON chunks(version_id);
                    CREATE INDEX chunks_paper ON chunks(paper_id);
                    CREATE TABLE latest (paper_id TEXT PRIMARY KEY, version_id TEXT);
                    CREATE TABLE sources (
                        version_id TEXT PRIMARY KEY, source_path TEXT, text_path TEXT,
                        source_hash TEXT, text_hash TEXT
                    );
                    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT);
                    CREATE VIRTUAL TABLE source_fts USING fts5(id UNINDEXED, text);
                """)
                connection.executemany("INSERT INTO latest VALUES (?, ?)",
                                       [(key, value.id) for key, value in sorted(latest.items())])
                for version in versions:
                    fingerprint = {"version": version.model_dump(mode="json")}
                    fingerprints.append(fingerprint)
                    source_hash = version.content_hash
                    currentness = "UNVERIFIABLE"
                    try:
                        if version.source_path:
                            original = Path(version.source_path).read_bytes()
                            source_hash = _digest(original)
                            fingerprint["actual_source_hash"] = source_hash
                            if version.content_hash and source_hash != version.content_hash:
                                raise ValueError("source content hash mismatch")
                            if version.content_hash:
                                currentness = "VERIFIED"
                        if not version.text_path:
                            raise FileNotFoundError("text_path is absent")
                        # read_bytes preserves CRLF and exact Unicode character offsets.
                        payload = Path(version.text_path).read_bytes()
                        fingerprint["actual_text_hash"] = _digest(payload)
                        text = payload.decode("utf-8")
                        if not text.strip():
                            raise ValueError("source text is empty")
                    except (OSError, UnicodeError, ValueError) as exc:
                        error = f"{type(exc).__name__}: {exc}"
                        fingerprint["error"] = error
                        errors.append({"version_id": version.id, "error": error})
                        if isinstance(exc, FileNotFoundError):
                            missing.append(version.id)
                        continue

                    text_hash = fingerprint["actual_text_hash"]
                    connection.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                                       (version.id, version.source_path, version.text_path,
                                        source_hash, text_hash))
                    for parent_start, parent_end in _spans(text, 0, len(text), PARENT_SIZE):
                        parent_id = f"{version.id}:{text_hash}:{parent_start}:{parent_end}"
                        connection.execute("INSERT INTO parents VALUES (?, ?, ?, ?)",
                                           (parent_id, parent_start, parent_end,
                                            text[parent_start:parent_end]))
                        for start, end in _spans(text, parent_start, parent_end, CHILD_SIZE):
                            identifier = f"{version.id}:{text_hash}:{start}:{end}"
                            passage = text[start:end]
                            connection.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                               (identifier, version.paper_id, version.id,
                                                source_hash, text_hash, start, end, passage,
                                                parent_id, version.coverage.value, currentness))
                            connection.execute("INSERT INTO source_fts VALUES (?, ?)",
                                               (identifier, passage))
                            indexed_chunks += 1
                    indexed_versions += 1

                fingerprint = _digest(json.dumps(
                    {"schema": INDEX_SCHEMA, "child_size": CHILD_SIZE, "parent_size": PARENT_SIZE,
                     "papers": [paper.model_dump(mode="json")
                                for paper in sorted(papers.values(), key=lambda paper: paper.id)],
                     "versions": fingerprints}, sort_keys=True, ensure_ascii=False,
                ).encode("utf-8"))
                stats = {"indexed_versions": indexed_versions, "indexed_chunks": indexed_chunks,
                         "missing_versions": missing, "errors": errors, "fingerprint": fingerprint}
                connection.execute("INSERT INTO metadata VALUES ('stats', ?)",
                                   (json.dumps(stats, sort_keys=True),))
            os.replace(temporary, self.path)
            return stats
        finally:
            Path(temporary).unlink(missing_ok=True)

    def search(self, query: str, *, top_k: int = 8, paper_ids: list[str] | None = None,
               version_ids: list[str] | None = None) -> list[dict]:
        """Literal lexical recall; explicit version filters permit historical reading.

        Filters run before ranking/limiting. A missing newest version never causes
        an older version to masquerade as current. Coverage is inherited, including
        abstract-only and metadata-only sources; retrieved text does not upgrade it.
        """
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        terms = list(dict.fromkeys(re.findall(r"\w+", query, flags=re.UNICODE)))
        if not terms or paper_ids == [] or version_ids == [] or not self.path.exists():
            return []
        match = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        clauses = ["source_fts MATCH ?"]
        parameters: list = [match]
        if version_ids is None:
            clauses.append("c.version_id IN (SELECT version_id FROM latest)")
        for column, identifiers in (("paper_id", paper_ids), ("version_id", version_ids)):
            if identifiers is not None:
                clauses.append(f"c.{column} IN ({','.join('?' for _ in identifiers)})")
                parameters.extend(identifiers)
        parameters.append(top_k)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT c.id,c.paper_id,c.version_id,c.source_hash,c.text_hash,c.start,c.end,"
                "c.text,p.start AS parent_start,p.end AS parent_end,p.text AS parent_text,"
                "-bm25(source_fts) AS score,c.coverage,c.source_currentness "
                "FROM source_fts JOIN chunks c ON c.id=source_fts.id "
                "JOIN parents p ON p.id=c.parent_id WHERE " + " AND ".join(clauses)
                + " ORDER BY bm25(source_fts), c.id LIMIT ?", parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, passage_id: str) -> dict:
        """Load an exact cached passage and reject stale source/text artifacts.

        Unlike a canonical Evidence ID, a passage ID is local to a source-text
        fingerprint. It cannot certify correctness or upgrade inherited coverage.
        """
        if not self.path.exists():
            raise KeyError(passage_id)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT c.id,c.paper_id,c.version_id,c.source_hash,c.text_hash,c.start,c.end,"
                "c.text,p.start AS parent_start,p.end AS parent_end,p.text AS parent_text,"
                "0.0 AS score,c.coverage,c.source_currentness "
                "FROM chunks c JOIN parents p ON p.id=c.parent_id WHERE c.id=?",
                (passage_id,),
            ).fetchone()
            if row is None:
                raise KeyError(passage_id)
            source = connection.execute("SELECT * FROM sources WHERE version_id=?",
                                        (row["version_id"],)).fetchone()
        for name in ("source", "text"):
            path = source[name + "_path"]
            if not path and name == "source":
                continue
            try:
                actual = _digest(Path(path).read_bytes())
            except OSError as exc:
                raise ValueError(f"indexed {name} is unreadable; rebuild source index: {exc}") from exc
            if actual != source[name + "_hash"]:
                raise ValueError(f"indexed {name} changed; rebuild source index")
        return dict(row)
