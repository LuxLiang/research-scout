"""Retrieval metric checks and a prominently synthetic local smoke benchmark.

The fixtures test pipeline behavior, not accuracy on the user's literature.
"""
from __future__ import annotations

from research_scout.retrieval.fusion import ResearchRetriever


def _identifiers(values, field: str) -> list[str]:
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError(f"{field} must be a list of nonblank record IDs")
    return list(dict.fromkeys(values))


def evaluate_rankings(cases: list[dict], top_k=10) -> dict:
    """Macro-average hit rate, reciprocal first-hit rank and recall at k.

    A hit means at least one expected ID was retrieved. Recall measures how
    many expected IDs were retrieved. Duplicate IDs never inflate either metric
    or consume distinct-document rank positions. MRR is truncated at ``top_k``.
    """
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    if not cases:
        raise ValueError("retrieval evaluation requires at least one case")
    breakdown = []
    for case in cases:
        query = case.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("evaluation cases require a nonblank query")
        expected = _identifiers(case.get("expected_ids"), "expected_ids")
        if not expected:
            raise ValueError("evaluation cases require nonempty expected_ids")
        ranked = _identifiers(case.get("ranked_ids"), "ranked_ids")[:top_k]
        expected_set = set(expected)
        matched = [identifier for identifier in ranked if identifier in expected_set]
        first_rank = next((rank for rank, identifier in enumerate(ranked, 1)
                           if identifier in expected_set), None)
        breakdown.append({
            "query": query, "expected_ids": expected, "ranked_ids": ranked,
            "matched_ids": matched,
            "missing_ids": [identifier for identifier in expected if identifier not in matched],
            "hit_rate": float(bool(matched)),
            "mrr": 1 / first_rank if first_rank is not None else 0.0,
            "recall_at_k": len(matched) / len(expected),
        })
    return {
        "case_count": len(breakdown), "top_k": top_k,
        **{metric: sum(case[metric] for case in breakdown) / len(breakdown)
           for metric in ("hit_rate", "mrr", "recall_at_k")},
        "cases": breakdown,
    }


def run_retrieval_evaluation() -> dict:
    """Run SYNTHETIC contract checks, including an explicitly configured stub.

    The semantic fixture returns a known alias mapping. It tests adapter wiring
    only and provides no evidence of actual embedding or semantic accuracy.
    Failures are returned in ``errors`` for CLI/report consumers.
    """
    documents = [
        {"id": "synthetic-literal", "kind": "mechanism", "synthetic": True,
         "title": "SYNTHETIC Gaussian smoothing estimate",
         "principle": "A local smoothing construction"},
        {"id": "synthetic-structure", "kind": "problem", "synthetic": True,
         "title": "SYNTHETIC kinetic transport question",
         "structures": ["semigroup-factorization"],
         "desired_result": "A uniform relaxation estimate"},
        {"id": "synthetic-goal", "kind": "problem", "synthetic": True,
         "title": "SYNTHETIC old question with an uninformative title",
         "desired_result": "dimension independent entropy convergence"},
        {"id": "synthetic-distractor", "kind": "problem", "synthetic": True,
         "title": "SYNTHETIC disconnected matrix factorization",
         "structures": ["matrix-factorization"]},
        {"id": "synthetic-semantic", "kind": "mechanism", "synthetic": True,
         "title": "SYNTHETIC transfer operator construction",
         "principle": "A capability found only by the configured test alias"},
    ]
    scenarios = [
        {"name": "literal match", "query": "Gaussian smoothing", "structures": [],
         "expected_ids": ["synthetic-literal"]},
        {"name": "cross-field structure with no lexical overlap", "query": "martingale lifting",
         "structures": ["semigroup-factorization"], "expected_ids": ["synthetic-structure"]},
        {"name": "explicit old-problem goal", "query": "dimension independent entropy convergence",
         "structures": [], "expected_ids": ["synthetic-goal"]},
        {"name": "irrelevant distractor does not replace a goal match",
         "query": "uniform relaxation estimate", "structures": [],
         "expected_ids": ["synthetic-structure"]},
        {"name": "SYNTHETIC configured semantic alias stub", "query": "unseen spectral alias",
         "structures": [], "expected_ids": ["synthetic-semantic"], "semantic_stub": True},
    ]
    cases = []
    errors = []

    def synthetic_alias(query):
        # SYNTHETIC stub, explicitly configured; no embedding is computed.
        return ["synthetic-semantic"] if query == "unseen spectral alias" else []

    for scenario in scenarios:
        semantic = synthetic_alias if scenario.get("semantic_stub") else None
        retriever = ResearchRetriever(documents, semantic=semantic)
        try:
            hits = retriever.search(scenario["query"], structures=scenario["structures"], top_k=3)
            ranked_ids = [hit["id"] for hit in hits]
        except Exception as exc:
            errors.append(f"{scenario['name']}: retrieval failed: {exc}")
            ranked_ids = []
        cases.append({"query": scenario["query"], "expected_ids": scenario["expected_ids"],
                      "ranked_ids": ranked_ids})
    result = evaluate_rankings(cases, top_k=3)
    for scenario, case in zip(scenarios, result["cases"], strict=True):
        case["scenario"] = scenario["name"]
        if case["recall_at_k"] != 1 or case["mrr"] != 1:
            errors.append(f"{scenario['name']}: expected candidate was not ranked first")
    # No seed means no arbitrary graph candidates, including unrelated distractors.
    try:
        if ResearchRetriever(documents).search("nonexistenttoken"):
            errors.append("unmatched query produced unrelated candidates")
    except Exception as exc:
        errors.append(f"unmatched-query check failed: {exc}")
    return {
        **result,
        "fixture_qualification": (
            "SYNTHETIC local smoke benchmark; not empirical literature-corpus performance"
        ),
        "semantic_fixture": "SYNTHETIC explicitly configured alias stub; no genuine embeddings",
        "errors": errors,
    }
