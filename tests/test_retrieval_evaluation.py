"""SYNTHETIC metric fixtures; no empirical research-corpus claims."""
import pytest

from research_scout.retrieval.evaluation import evaluate_rankings, run_retrieval_evaluation


def test_metrics_distinguish_any_hit_recall_and_first_hit_rank():
    result = evaluate_rankings([
        {"query": "partial", "expected_ids": ["a", "b"], "ranked_ids": ["x", "a"]},
        {"query": "miss", "expected_ids": ["c"], "ranked_ids": ["x", "y"]},
        {"query": "complete", "expected_ids": ["d", "e"], "ranked_ids": ["d", "e"]},
    ], top_k=2)
    assert result["case_count"] == 3
    assert result["hit_rate"] == pytest.approx(2 / 3)
    assert result["mrr"] == pytest.approx((0.5 + 0 + 1) / 3)
    assert result["recall_at_k"] == pytest.approx((0.5 + 0 + 1) / 3)
    assert result["cases"][0]["missing_ids"] == ["b"]
    assert result["cases"][1]["matched_ids"] == []


def test_duplicate_rankings_and_expectations_do_not_inflate_scores():
    result = evaluate_rankings([
        {"query": "duplicates", "expected_ids": ["a", "a", "b"],
         "ranked_ids": ["a", "a", "a", "x", "b"]},
    ], top_k=2)
    assert result["hit_rate"] == 1
    assert result["recall_at_k"] == 0.5
    assert result["cases"][0]["ranked_ids"] == ["a", "x"]
    assert result["cases"][0]["expected_ids"] == ["a", "b"]


def test_relevant_document_outside_top_k_is_a_false_negative():
    case = {"query": "cutoff", "expected_ids": ["target"], "ranked_ids": ["x", "target"]}
    result = evaluate_rankings([case], top_k=1)
    assert result["hit_rate"] == result["mrr"] == result["recall_at_k"] == 0
    assert result["cases"][0]["missing_ids"] == ["target"]


def test_empty_retrieval_is_measured_as_a_miss():
    result = evaluate_rankings([{"query": "absent", "expected_ids": ["a"], "ranked_ids": []}])
    assert result["hit_rate"] == result["mrr"] == result["recall_at_k"] == 0


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5, "2"])
def test_invalid_cutoff_is_rejected(top_k):
    with pytest.raises(ValueError, match="top_k"):
        evaluate_rankings([{"query": "q", "expected_ids": ["a"], "ranked_ids": []}], top_k)


@pytest.mark.parametrize("case", [
    {"query": "q", "expected_ids": [], "ranked_ids": []},
    {"query": "q", "expected_ids": [""], "ranked_ids": []},
    {"query": "q", "expected_ids": ["a"], "ranked_ids": [None]},
    {"query": "", "expected_ids": ["a"], "ranked_ids": []},
])
def test_undefined_or_malformed_cases_fail_explicitly(case):
    with pytest.raises(ValueError):
        evaluate_rankings([case])
    with pytest.raises(ValueError, match="at least one"):
        evaluate_rankings([])


def test_synthetic_smoke_benchmark_reports_its_limits():
    result = run_retrieval_evaluation()
    assert result["case_count"] == 5
    assert result["hit_rate"] == result["mrr"] == result["recall_at_k"] == 1
    assert result["errors"] == []
    assert "SYNTHETIC" in result["fixture_qualification"]
    assert "not empirical" in result["fixture_qualification"]
    assert "stub" in result["semantic_fixture"]
    assert "no genuine embeddings" in result["semantic_fixture"]


def test_benchmark_exposes_regressions_instead_of_reporting_success(monkeypatch):
    monkeypatch.setattr("research_scout.retrieval.evaluation.ResearchRetriever.search",
                        lambda *args, **kwargs: [])
    result = run_retrieval_evaluation()
    assert result["hit_rate"] == result["mrr"] == result["recall_at_k"] == 0
    assert len(result["errors"]) == 5


def test_benchmark_records_retrieval_errors(monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic unavailable component")

    monkeypatch.setattr("research_scout.retrieval.evaluation.ResearchRetriever.search", unavailable)
    result = run_retrieval_evaluation()
    assert result["hit_rate"] == 0
    assert any("synthetic unavailable component" in error for error in result["errors"])
