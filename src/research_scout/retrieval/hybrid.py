from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import Record


@dataclass
class SearchHit:
    record: Record
    reasons: list[str] = field(default_factory=list)


class HybridRetriever:
    """Deterministic graph expansion; optional semantic/citation adapters are explicit.

    Retrieval is candidate discovery. A shared label, structure, or embedding
    never qualifies a logical comparison or a scientific relationship.
    """

    def __init__(self, archive: ArchiveProtocol, *,
                 semantic: Callable[[str], Iterable[str]] | None = None,
                 external: Callable[[str], Iterable[str]] | None = None):
        self.archive = archive
        self.semantic = semantic
        self.external = external

    def search(self, query: str, *, labels: list[str] | None = None,
               kinds: list[str] | None = None, depth: int = 1,
               include_external: bool = False) -> list[SearchHit]:
        hits: dict[str, SearchHit] = {}

        def add(record, reason):
            if kinds and record.kind not in kinds:
                return
            if labels and not set(labels).issubset(record.labels):
                return
            hit = hits.setdefault(record.id, SearchHit(record))
            if reason not in hit.reasons:
                hit.reasons.append(reason)

        # Filter the final candidates, allowing lexical hits in a mechanism to
        # retrieve a connected paper carrying different classification labels.
        lexical = self.archive.search(query)
        for record in lexical:
            add(record, "exact identity or full-text match")
            if depth:
                for neighbor in self.archive.traverse(record.id, depth):
                    add(neighbor, f"graph connection to {record.id}")
        if self.semantic is not None:
            for identifier in self.semantic(query):
                add(self.archive.get(identifier), "configured semantic candidate")
        if include_external:
            if self.external is None:
                raise ValueError("external literature expansion requires an explicit adapter")
            for identifier in self.external(query):
                add(self.archive.get(identifier), "configured external citation candidate")
        return list(hits.values())

    def analogous(self, entity_id: str, *, kinds: list[str] | None = None) -> list[SearchHit]:
        source = self.archive.get(entity_id)
        structures = set(getattr(source, "structures", []))
        if not structures:
            return []
        result = []
        for candidate in self.archive.list():
            if candidate.id == source.id or (kinds and candidate.kind not in kinds):
                continue
            overlap = structures & set(getattr(candidate, "structures", []))
            if overlap:
                result.append(SearchHit(candidate, ["candidate shared structure: " + ", ".join(sorted(overlap))]))
        return result
