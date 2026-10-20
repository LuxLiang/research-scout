"""Synthetic retrieval fixtures; no scientific relationships are asserted."""
import math

import pytest

from research_scout.domain.models import Mechanism
from research_scout.retrieval.fusion import ResearchRetriever, reciprocal_rank_fusion


def record(identifier, title, kind="problem", **fields):
    return {"id": identifier, "kind": kind, "title": title, **fields, "synthetic": True}


def test_fusion_combines_complementary_channels_without_duplicate_votes():
    rankings = {"lexical": ["local", "local", "bridge"], "structure": ["bridge", "other"]}
    hits = reciprocal_rank_fusion(rankings, k=10)
    assert hits[0]["id"] == "bridge"
    assert hits[0]["score"] == pytest.approx(1 / 12 + 1 / 11)
    assert hits[0]["reasons"] == ["lexical: rank 2", "structure: rank 1"]
    assert reciprocal_rank_fusion({"lexical": ["local", "bridge"]}, k=10)[1]["score"] == 1 / 12


def test_fusion_weights_zero_channel_and_deterministic_ties():
    hits = reciprocal_rank_fusion({"b": ["z"], "a": ["a"]})
    assert [hit["id"] for hit in hits] == ["a", "z"]
    assert reciprocal_rank_fusion({"b": ["z"], "a": ["a"]}, weights={"a": 0}) == [
        {"id": "z", "score": 1 / 61, "reasons": ["b: rank 1"]},
    ]
    hits = reciprocal_rank_fusion({"b": ["z"], "a": ["a"]}, weights={"b": 2})
    assert hits[0]["id"] == "z"


@pytest.mark.parametrize("weight", [-1, math.nan, math.inf, "1", True])
def test_fusion_rejects_invalid_weights(weight):
    with pytest.raises(ValueError, match="weights"):
        reciprocal_rank_fusion({"lexical": ["a"]}, weights={"lexical": weight})


@pytest.mark.parametrize("k", [0, -1, math.nan, math.inf, "60", True])
def test_fusion_rejects_invalid_rank_constant(k):
    with pytest.raises(ValueError, match="fusion k"):
        reciprocal_rank_fusion({}, k=k)


def test_cross_field_structure_recall_does_not_require_lexical_overlap():
    retriever = ResearchRetriever([
        record("local", "Gaussian smoothing of noise"),
        record("remote", "A transport question in kinetic dynamics", structures=["Semigroup"]),
        record("unrelated", "An unrelated problem"),
    ])
    hits = retriever.search("Gaussian smoothing", structures=[" semigroup "])
    assert {hit["id"] for hit in hits} == {"local", "remote"}
    remote = next(hit for hit in hits if hit["id"] == "remote")
    assert "structure: rank 1" in remote["reasons"]
    assert "shared structures: semigroup" in remote["reasons"]


def test_lexical_uses_scientific_text_and_parameterized_query():
    retriever = ResearchRetriever([
        record("hiddenuniquename", "Ordinary theorem", evidence_ids=["secretreference"],
               provenance="privateprovenance", locator="secretlocator"),
        record("explicit", "Different title", scope={"guarantee": "Gaussian contraction"}),
    ])
    for query in ["hiddenuniquename", "secretreference", "privateprovenance", "secretlocator"]:
        assert retriever.search(query) == []
    assert retriever.search("Gaussian")[0]["id"] == "explicit"
    assert retriever.search('" OR * NOT (') == []


def test_accepts_canonical_record_and_can_search_capability_fields():
    mechanism = Mechanism(id="m", title="Synthetic tool", principle="Construction",
                          output_guarantees=["hypocoercive regularization"], synthetic=True)
    assert ResearchRetriever([mechanism]).search("hypocoercive")[0]["id"] == "m"


def test_kind_filters_precede_channel_budgets():
    records = [record(f"paper-{n}", "Gaussian", kind="paper") for n in range(100)]
    records.append(record("target", "A Gaussian estimate for kinetic equations"))
    retriever = ResearchRetriever(records, semantic=lambda query: [item["id"] for item in records])
    hits = retriever.search("Gaussian", kinds=["problem"], top_k=1)
    assert len(hits) == 1
    assert hits[0]["id"] == "target"
    assert "semantic: rank 1" in hits[0]["reasons"]


def test_graph_expansion_is_one_hop_and_requires_a_seed():
    retriever = ResearchRetriever([
        record("seed", "Gaussian estimate", mechanism_ids=["neighbor"]),
        record("neighbor", "Other technique", problem_ids=["two-hop"]),
        record("two-hop", "Transport question"),
        record("disconnected", "Other problem"),
    ])
    assert retriever.search("absent") == []
    hits = retriever.search("Gaussian")
    assert {hit["id"] for hit in hits} == {"seed", "neighbor"}
    neighbor = next(hit for hit in hits if hit["id"] == "neighbor")
    assert "one-hop connections: seed" in neighbor["reasons"]


def test_explicit_relationship_edge_reaches_other_endpoint():
    retriever = ResearchRetriever([
        record("source", "Gaussian technique", kind="mechanism"),
        record("target", "Kinetic question"),
        record("relation", "Candidate application", kind="relation",
               source_id="source", target_id="target"),
    ])
    assert "target" in {hit["id"] for hit in retriever.search("Gaussian")}


@pytest.mark.parametrize("adapter", [lambda query: ["unknown"], lambda query: "known",
                                     lambda query: [None], lambda query: 3])
def test_invalid_semantic_outputs_fail_explicitly(adapter):
    retriever = ResearchRetriever([record("known", "Gaussian")], semantic=adapter)
    with pytest.raises(ValueError, match="semantic adapter failed"):
        retriever.search("Gaussian")


def test_semantic_adapter_exceptions_do_not_fallback():
    def unavailable(query):
        raise RuntimeError("service unavailable")

    retriever = ResearchRetriever([record("known", "Gaussian")], semantic=unavailable)
    with pytest.raises(ValueError, match="service unavailable"):
        retriever.search("Gaussian")


def test_reranker_receives_text_and_changes_order_without_inventing_scores():
    observed = []

    def reverse(query, candidates):
        observed.extend(candidates)
        return [item["id"] for item in reversed(candidates)]

    retriever = ResearchRetriever([record("a", "Gaussian"), record("b", "Gaussian")],
                                 reranker=reverse)
    hits = retriever.search("Gaussian")
    assert [hit["id"] for hit in hits] == ["b", "a"]
    assert all("Gaussian" in item["text"] for item in observed)
    assert hits[0]["score"] == next(item["score"] for item in observed if item["id"] == "b")
    assert "configured reranker: rank 1" in hits[0]["reasons"]
    assert set(hits[0]) == {"id", "score", "reasons"}


@pytest.mark.parametrize("order", [["a", "a"], ["a"], ["a", "unknown"], "ab", [None, "a"]])
def test_reranker_rejects_missing_duplicate_and_unknown_ids(order):
    retriever = ResearchRetriever([record("a", "Gaussian"), record("b", "Gaussian")],
                                 reranker=lambda query, candidates: order)
    with pytest.raises(ValueError, match="reranker adapter failed"):
        retriever.search("Gaussian")


def test_duplicate_record_ids_are_an_explicit_error():
    with pytest.raises(ValueError, match="duplicate retrieval record"):
        ResearchRetriever([record("a", "First"), record("a", "Second")])
