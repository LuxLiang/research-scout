"""Local candidate retrieval with independently ranked, attributable channels.

Uses the rank-fusion pattern found in LlamaIndex QueryFusionRetriever and
Haystack DocumentJoiner, implemented here without framework dependencies.
Scores order reading candidates; they are not scientific confidence estimates.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from contextlib import closing
import math
import re
import sqlite3

from research_scout.domain.models import Record


# Deliberately index scientific content rather than serialized JSON, identifiers,
# evidence references, provenance, timestamps, hashes or source paths.
_TEXT_FIELDS = {
    "title", "aliases", "labels", "statement", "desired_result", "description",
    "obstruction", "insufficiency", "principle", "construction", "proof_role",
    "applicable_models", "necessary_assumptions", "limitations", "input_objects",
    "output_guarantees", "reusable_steps", "research_questions", "methods",
    "proof_techniques", "contributions", "rate", "technical_delta", "open_questions",
    "unresolved_scope", "difficulty_hypotheses", "structures", "content", "abstract",
    "quotation", "adaptation", "bridge_statement", "match_basis", "next_action",
    "shared_structures", "structural_differences", "required_assumptions",
    "missing_lemmas", "likely_counterexamples", "proposed_result",
    "first_falsification_test", "uncertainty", "failure_reason", "revisit_when",
}
_SCOPE_FIELDS = {"domain", "model", "objective", "assumptions", "quantifiers",
                 "metric", "guarantee", "unresolved"}
_SPECIAL_REFERENCES = {"historical_results", "previous_mechanisms"}


def _strings(value) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _text(record: dict) -> str:
    parts = [term for key in sorted(_TEXT_FIELDS) for term in _strings(record.get(key))]
    scope = record.get("scope")
    if isinstance(scope, dict):
        parts.extend(term for key in sorted(_SCOPE_FIELDS) for term in _strings(scope.get(key)))
    return "\n".join(parts)


def _references(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_id") and key != "arxiv_id" and isinstance(item, str):
                found.add(item)
            elif key.endswith("_ids") or key in _SPECIAL_REFERENCES:
                found.update(_strings(item))
            else:
                found.update(_references(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_references(item))
    return found


def reciprocal_rank_fusion(
    rankings: dict[str, list[str]], *, weights: dict[str, float] | None = None, k=60,
) -> list[dict]:
    """Sum weight/(k + one-based rank), with one vote per ID per channel.

    Duplicate entries do not consume ranking positions. Missing weights default
    to one; zero disables a channel. Equal scores break by stable identifier.
    """
    if isinstance(k, bool) or not isinstance(k, (int, float)) or not math.isfinite(k) or k <= 0:
        raise ValueError("fusion k must be finite and greater than zero")
    weights = weights or {}
    if set(weights) - set(rankings):
        raise ValueError("fusion weights refer to unknown channels")
    for weight in weights.values():
        if (isinstance(weight, bool) or not isinstance(weight, (int, float))
                or not math.isfinite(weight) or weight < 0):
            raise ValueError("fusion weights must be finite nonnegative numbers")
    hits: dict[str, dict] = {}
    for channel in sorted(rankings):
        weight = weights.get(channel, 1.0)
        seen: set[str] = set()
        for identifier in rankings[channel]:
            if not isinstance(identifier, str) or not identifier:
                raise ValueError("ranked identifiers must be nonempty strings")
            if identifier in seen:
                continue
            seen.add(identifier)
            if weight == 0:
                continue
            rank = len(seen)
            hit = hits.setdefault(identifier, {"id": identifier, "score": 0.0, "reasons": []})
            hit["score"] += weight / (k + rank)
            hit["reasons"].append(f"{channel}: rank {rank}")
    return sorted(hits.values(), key=lambda hit: (-hit["score"], hit["id"]))


class ResearchRetriever:
    """BM25 + explicit structure + bounded one-hop graph candidate retrieval.

    Semantic retrieval and reranking are opt-in callables. A semantic adapter
    returns known canonical IDs, in rank order. A reranker receives candidate
    dictionaries with scientific ``text`` and must return an exact permutation
    of their IDs. Adapter failures and invalid outputs fail explicitly.
    """

    def __init__(
        self, records: Iterable[Record | dict], *,
        semantic: Callable[[str], Iterable[str]] | None = None,
        reranker: Callable[[str, list[dict]], Iterable[str]] | None = None,
    ):
        self.records: dict[str, dict] = {}
        for record in records:
            data = record.model_dump(mode="json") if isinstance(record, Record) else dict(record)
            identifier = data.get("id")
            if not isinstance(identifier, str) or not identifier or not data.get("kind"):
                raise ValueError("retrieval records require nonempty id and kind")
            if identifier in self.records:
                raise ValueError(f"duplicate retrieval record: {identifier}")
            self.records[identifier] = data
        self.texts = {identifier: _text(data) for identifier, data in self.records.items()}
        self.semantic = semantic
        self.reranker = reranker
        self.neighbors: dict[str, set[str]] = defaultdict(set)
        for identifier, data in self.records.items():
            for target in _references(data) & self.records.keys():
                if identifier != target:
                    self.neighbors[identifier].add(target)
                    self.neighbors[target].add(identifier)
            # An explicit relation is one graph edge, not two hops via its record.
            if data["kind"] == "relation":
                source, target = data.get("source_id"), data.get("target_id")
                if source in self.records and target in self.records and source != target:
                    self.neighbors[source].add(target)
                    self.neighbors[target].add(source)

    def _lexical(self, query: str, eligible: set[str], budget: int) -> list[str]:
        tokens = list(dict.fromkeys(re.findall(r"[^\W_]+", query, re.UNICODE)))
        if not tokens or not eligible:
            return []
        # Only user tokens are quoted into the FTS expression; SQL is parameterized.
        expression = " OR ".join(f'"{token}"' for token in tokens)
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE VIRTUAL TABLE candidates USING fts5(id UNINDEXED, text)")
            connection.executemany("INSERT INTO candidates VALUES (?, ?)",
                                   ((identifier, self.texts[identifier])
                                    for identifier in sorted(eligible)))
            return [row[0] for row in connection.execute(
                "SELECT id FROM candidates WHERE candidates MATCH ? "
                "ORDER BY bm25(candidates), id LIMIT ?", (expression, budget),
            )]

    def search(
        self, query: str, *, structures: list[str] | None = None,
        top_k=20, kinds: list[str] | None = None,
    ) -> list[dict]:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        eligible = {identifier for identifier, data in self.records.items()
                    if not kinds or data["kind"] in kinds}
        budget = max(20, top_k * 4)
        rankings = {"lexical": self._lexical(query, eligible, budget)}
        requested = {value.strip().casefold() for value in structures or [] if value.strip()}
        overlaps = {
            identifier: requested & {value.strip().casefold()
                                    for value in self.records[identifier].get("structures", [])}
            for identifier in eligible
        }
        rankings["structure"] = sorted(
            (identifier for identifier in eligible if overlaps[identifier]),
            key=lambda identifier: (-len(overlaps[identifier]), identifier),
        )[:budget]
        if self.semantic is not None:
            try:
                raw = self.semantic(query)
                if isinstance(raw, (str, bytes)):
                    raise ValueError("expected an iterable of IDs, not a string")
                identifiers = list(raw)
                if any(not isinstance(identifier, str) or identifier not in self.records
                       for identifier in identifiers):
                    raise ValueError("semantic adapter returned unknown record IDs")
            except Exception as exc:
                raise ValueError(f"semantic adapter failed: {exc}") from exc
            rankings["semantic"] = list(dict.fromkeys(
                identifier for identifier in identifiers if identifier in eligible
            ))[:budget]
        # Expand only independently recalled seeds, never a graph-generated hit.
        seeds = reciprocal_rank_fusion(rankings)[:budget]
        connected: dict[str, list[str]] = defaultdict(list)
        seed_ids = {hit["id"] for hit in seeds}
        for seed in seeds:
            for identifier in sorted(self.neighbors[seed["id"]] & eligible - seed_ids):
                connected[identifier].append(seed["id"])
        rankings["graph"] = sorted(connected, key=lambda identifier: (
            -len(connected[identifier]), identifier,
        ))[:budget]
        # A connection alone is weaker than independent content/structure recall.
        hits = reciprocal_rank_fusion(rankings, weights={"graph": 0.5})
        for hit in hits:
            identifier = hit["id"]
            if overlaps[identifier]:
                hit["reasons"].append("shared structures: " + ", ".join(sorted(overlaps[identifier])))
            if identifier in rankings["graph"]:
                hit["reasons"].append("one-hop connections: " + ", ".join(connected[identifier][:5]))
        if self.reranker is not None and hits:
            candidates = [{**hit, "reasons": list(hit["reasons"]), "text": self.texts[hit["id"]]}
                          for hit in hits[:budget]]
            expected = {hit["id"] for hit in candidates}
            try:
                raw = self.reranker(query, candidates)
                if isinstance(raw, (str, bytes)):
                    raise ValueError("expected an iterable of IDs, not a string")
                order = list(raw)
                if (any(not isinstance(identifier, str) for identifier in order)
                        or len(order) != len(expected) or set(order) != expected):
                    raise ValueError("reranker must return every candidate ID exactly once")
            except Exception as exc:
                raise ValueError(f"reranker adapter failed: {exc}") from exc
            by_id = {hit["id"]: hit for hit in hits}
            hits = [by_id[identifier] for identifier in order]
            for rank, hit in enumerate(hits, 1):
                hit["reasons"].append(f"configured reranker: rank {rank}")
        return hits[:top_k]
