"""Synthetic persistence tests exercise scientific gates, crash recovery and history."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path

import pytest

from research_scout.domain.models import (
    AssessmentStatus as A, ClaimOrigin, Coverage, Evidence, EvolutionEvent,
    EventType, Paper, PaperVersion, PreciseProblem, Relationship, RelationType,
    ResolutionKind, Result, Review, ScientificClaim, Scope, Topic,
)
from research_scout.retrieval import HybridRetriever
from research_scout.storage import Archive, ConflictError, DuplicateRecordError, IntegrityError
from research_scout.taxonomy import Taxonomy


@pytest.fixture
def archive(tmp_path):
    return Archive(tmp_path / "knowledge")


def scope():
    return Scope(domain="SYNTHETIC mathematics", model="finite system", objective="decay",
                 assumptions=["positive curvature"], quantifiers=["all initial states"],
                 metric="distance", guarantee="exponential convergence")


def history():
    return [
        Paper(id="p", title="SYNTHETIC paper", doi="10.1234/synthetic", arxiv_id="2601.12345",
              version_ids=["v1"], synthetic=True),
        PaperVersion(id="v1", title="SYNTHETIC v1", paper_id="p", version="1",
                     content_hash="abc", coverage=Coverage.FULL_TEXT, synthetic=True),
        Evidence(id="e", title="SYNTHETIC source", paper_id="p", version_id="v1",
                 locator="Synthetic Theorem 1", quotation="synthetic convergence claim",
                 coverage=Coverage.FULL_TEXT, source_hash="abc", synthetic=True,
                 assessment_status=A.SUPPORTED_BY_SOURCE),
        PreciseProblem(id="problem", title="SYNTHETIC convergence problem", statement="Control distance",
                       scope=scope(), desired_result="exponential convergence", synthetic=True),
        Result(id="result", title="SYNTHETIC theorem", paper_id="p", version_id="v1",
               result_type="THEOREM", statement="Distance decays exponentially.", scope=scope(),
               problem_ids=["problem"], evidence_ids=["e"], assessment_status=A.SUPPORTED_BY_SOURCE,
               synthetic=True),
    ]


def test_roundtrip_batch_circular_references_and_noop(archive):
    records = history()
    archive.put_many(records)
    assert archive.get("p").model_dump() == records[0].model_dump()
    assert archive.validate() == []
    generation = (archive.root / "CURRENT").read_text()
    archive.put_many(records)
    assert (archive.root / "CURRENT").read_text() == generation
    assert len(archive.audit()) == 1
    assert archive.rebuild() == len(records)


def test_missing_reference_batch_publishes_nothing(archive):
    good = Topic(id="good", title="good")
    bad = PaperVersion(id="bad", title="bad", paper_id="missing", version="1")
    with pytest.raises(IntegrityError, match="missing references"):
        archive.put_many([good, bad])
    assert archive.list() == []
    assert not (archive.root / "CURRENT").exists()


def test_revisions_preserve_old_records_and_reject_lost_update(archive):
    original = archive.put(Topic(id="topic", title="Original"))
    updated = archive.put(original.model_copy(update={"title": "Revised"}))
    assert updated.revision == 2
    assert [x.title for x in archive.history("topic")] == ["Original", "Revised"]
    with pytest.raises(ConflictError, match="stale revision"):
        archive.put(original.model_copy(update={"title": "Overwrite newer edit"}))
    assert archive.get("topic").title == "Revised"
    assert [x["records"][0]["revision"] for x in archive.audit()] == [1, 2]


def test_deduplicate_identifiers_aliases_and_arxiv_versions(archive):
    archive.put_many(history())
    assert archive.find_paper("https://doi.org/10.1234/SYNTHETIC").id == "p"
    assert archive.find_paper("https://arxiv.org/abs/2601.12345v9").id == "p"
    assert archive.get("doi:10.1234/synthetic").id == "p"
    with pytest.raises(DuplicateRecordError):
        archive.put(Paper(id="duplicate", title="Duplicate", arxiv_id="2601.12345v2"))
    archive.put(Topic(id="topic", title="Topic", aliases=["optimization"]))
    assert archive.get("Optimization").id == "topic"
    with pytest.raises(DuplicateRecordError):
        archive.put(Topic(id="other", title="Other", aliases=["optimization"]))


def test_typed_endpoint_and_foreign_version_rejected(archive):
    archive.put_many(history())
    wrong = Relationship(id="wrong", title="wrong", source_id="p", target_id="problem",
                         relation_type=RelationType.RESULT_ADDRESSES_PROBLEM, scope=scope(),
                         evidence_ids=["e"])
    with pytest.raises(IntegrityError, match="typed relationship"):
        archive.put(wrong)
    with pytest.raises(IntegrityError, match="another paper"):
        archive.put_many([Paper(id="p2", title="other paper"), Evidence(
            id="bad-e", title="bad evidence", paper_id="p2", version_id="v1",
            locator="Synthetic theorem", coverage=Coverage.FULL_TEXT)])


def test_evidence_cannot_promote_abstract_or_metadata_to_independent_review(archive):
    archive.put_many(history())
    abstract = Evidence(id="abstract", title="abstract", paper_id="p", version_id="v1",
                        locator="Abstract", coverage=Coverage.ABSTRACT_ONLY)
    claim = ScientificClaim(id="claim", title="claim", content="Synthetic theorem claim",
                            origin=ClaimOrigin.AUTHOR, version_id="v1", evidence_ids=["abstract"],
                            assessment_status=A.INDEPENDENTLY_REVIEWED,
                            review=Review(reviewer="reviewer", rationale="checked attribution",
                                          evidence_ids=["abstract"]))
    with pytest.raises(IntegrityError, match="abstract/metadata"):
        archive.put_many([abstract, claim])
    assert "abstract" not in {x.id for x in archive.list()}
    promoted = archive.get("result").model_copy(update={
        "assessment_status": A.INDEPENDENTLY_REVIEWED,
        "review": Review(reviewer="reviewer", rationale="Checked supplied source", evidence_ids=["e"]),
    })
    assert archive.put(promoted).assessment_status == A.INDEPENDENTLY_REVIEWED


def test_evidence_source_hash_and_coverage_fail_closed(archive):
    records = history()
    records[2] = records[2].model_copy(update={"source_hash": "other-content"})
    with pytest.raises(IntegrityError, match="content hash"):
        archive.put_many(records)
    records = history()
    records[1] = records[1].model_copy(update={"coverage": Coverage.ABSTRACT_ONLY})
    with pytest.raises(IntegrityError, match="coverage exceeds"):
        archive.put_many(records)


def test_events_versions_and_evidence_are_immutable(archive):
    archive.put_many(history())
    event = EvolutionEvent(id="event", title="Problem posed", event_type=EventType.PROBLEM_POSED,
        subject_id="problem", scientific_date=date(2023, 1, 1), paper_id="p", version_id="v1",
        scope=scope(), rationale="Synthetic problem introduction", evidence_ids=["e"])
    archive.put(event)
    for identifier, updates in [("event", {"rationale": "silently rewritten history"}),
                                ("v1", {"abstract": "replacement theorem"}),
                                ("e", {"locator": "Invented theorem 999"})]:
        with pytest.raises(IntegrityError, match="immutable"):
            archive.put(archive.get(identifier).model_copy(update=updates))
    archive.put(PaperVersion(id="v2", title="Revised source", paper_id="p", version="2",
                             supersedes_version_id="v1"))
    assert archive.get("v1").version == "1"


def test_supported_resolution_cannot_hide_stronger_assumptions(archive):
    records = history()
    stronger = scope().model_copy(update={"assumptions": ["positive curvature", "quadratic potential"]})
    records[4] = records[4].model_copy(update={"scope": stronger})
    archive.put_many(records)
    event = EvolutionEvent(id="resolved", title="Unsupported global resolution",
        event_type=EventType.SUPPORTED_RESOLUTION, subject_id="problem", related_ids=["result"],
        scientific_date=date(2026, 1, 1), paper_id="p", version_id="v1", scope=scope(),
        rationale="Synthetic adversarial test", evidence_ids=["e"],
        resolution=ResolutionKind.FULL_RESOLUTION_SUPPORTED, assessment_status=A.SUPPORTED_BY_SOURCE)
    with pytest.raises(IntegrityError, match="exact original-scope"):
        archive.put(event)
    result = archive.get("result")
    archive.put(result.model_copy(update={"scope": scope()}))
    assert archive.put(event).id == "resolved"
    # A later correction must retain the historical resolution event, and permit
    # current timelines to downgrade its assessment using the corrected result.
    result = archive.get("result")
    archive.put(result.model_copy(update={"scope": stronger, "assessment_status": A.CHALLENGED}))
    assert archive.get("resolved").id == "resolved"
    assert archive.validate() == []


def test_event_cycle_rejected(archive):
    archive.put_many(history())
    def event(identifier, previous):
        return EvolutionEvent(id=identifier, title=identifier, event_type=EventType.NEW_RESULT,
            subject_id="problem", related_ids=["result"], scientific_date=date(2026, 1, 1),
            paper_id="p", version_id="v1", scope=scope(), rationale="Synthetic circular history",
            evidence_ids=["e"], previous_event_ids=[previous])
    with pytest.raises(IntegrityError, match="cycle"):
        archive.put_many([event("one", "two"), event("two", "one")])


def test_graph_fts_and_corrupt_index_recovery(archive):
    archive.put_many(history())
    relation = Relationship(id="rel", title="Attributable scoped connection", source_id="result",
        target_id="problem", relation_type=RelationType.RESULT_ADDRESSES_PROBLEM,
        scope=scope(), evidence_ids=["e"])
    archive.put(relation)
    before = {x.id for x in archive.traverse("problem", 2)}
    assert {"result", "rel", "p", "v1", "e"}.issubset(before)
    assert archive.search("convergence")
    archive.index_path.write_bytes(b"corrupt sqlite projection")
    assert archive.search("convergence")
    assert {x.id for x in archive.traverse("problem", 2)} == before
    archive.index_path.unlink()
    assert archive.rebuild() == 6
    assert archive.search('"; DROP TABLE records; --') == []
    assert archive.validate() == []


def test_empty_archive_and_configurable_projection(tmp_path):
    archive = Archive(tmp_path / "knowledge", index_path=tmp_path / "cache" / "search.sqlite")
    assert archive.search("") == []
    assert archive.rebuild() == 0
    archive.put(Topic(id="topic", title="Indexed topic", labels=["math"]))
    assert archive.search("Indexed", labels=["math"])[0].id == "topic"
    assert archive.search("Indexed", labels=["biology"]) == []
    assert archive.index_path.exists()


def test_merge_and_split_keep_historical_references(archive):
    archive.put_many([Topic(id="a", title="First", aliases=["old name"]),
                      Topic(id="b", title="Canonical")])
    merge = archive.merge(["a"], "b", "Human-reviewed duplicate concept")
    assert archive.get("old name").id == "a"  # Historical identity still available.
    assert archive.resolve_id("old name", follow_merges=True) == "b"
    assert archive.get(merge.id).source_ids == ["a"]
    with pytest.raises(IntegrityError, match="cycle"):
        archive.merge(["b"], "a", "Would form a cycle")
    split = archive.split("b", [Topic(id="b1", title="First precise concept"),
                                Topic(id="b2", title="Second precise concept")],
                          "Original concept conflated two formulations")
    assert archive.get("b").title == "Canonical"
    assert archive.get(split.id).target_ids == ["b1", "b2"]
    assert len(archive.list("entity_change")) == 2
    assert archive.validate() == []


def test_migration_is_atomic_and_identity_preserving(archive):
    archive.put_many([Topic(id="a", title="a"), Topic(id="b", title="b")])
    def rename(data):
        return {**data, "title": data["title"].upper()}
    assert archive.migrate(rename) == 2
    assert archive.get("a").revision == 2
    assert archive.history("a")[0].title == "a"
    pointer = (archive.root / "CURRENT").read_text()
    with pytest.raises(IntegrityError, match="identity"):
        archive.migrate(lambda data: {**data, "id": "replaced"})
    assert (archive.root / "CURRENT").read_text() == pointer


def test_failed_pointer_publication_preserves_complete_previous_snapshot(archive, monkeypatch):
    import research_scout.storage.archive as module
    archive.put(Topic(id="original", title="Committed"))
    pointer = (archive.root / "CURRENT").read_text()
    replace = module.os.replace
    def fail_pointer(source, target):
        if Path(target).name == "CURRENT":
            raise OSError("synthetic simulated power loss before pointer publication")
        return replace(source, target)
    monkeypatch.setattr(module.os, "replace", fail_pointer)
    with pytest.raises(OSError, match="power loss"):
        archive.put(Topic(id="new", title="Uncommitted"))
    assert (archive.root / "CURRENT").read_text() == pointer
    assert [x.id for x in archive.list()] == ["original"]
    assert len(archive.audit()) == 1


def test_concurrent_writers_do_not_lose_other_transactions(archive):
    def write(index):
        separate_instance = Archive(archive.root)
        separate_instance.put(Topic(id=f"topic-{index}", title=f"Concurrent topic {index}"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(12)))
    assert len(archive.list()) == 12
    assert len(archive.audit()) == 12
    assert archive.validate() == []


def test_canonical_json_human_readable_and_projection_disposable(archive):
    archive.put(Topic(id="topic", title="中文科学知识"))
    generation = (archive.root / "CURRENT").read_text().strip()
    files = list((archive.root / "snapshots" / generation / "records" / "topics").glob("*.json"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "中文科学知识" in content and '\n  "id"' in content
    assert json.loads(content)["id"] == "topic"
    archive.rebuild()
    archive.index_path.unlink()
    assert Archive(archive.root).get("topic").title == "中文科学知识"


def test_taxonomy_and_hybrid_graph_candidates(archive):
    archive.put_many(history())
    taxonomy = Taxonomy(labels={"probability", "optimization"}, aliases={"sampling": "probability"})
    record = taxonomy.classify(archive.get("problem"), ["Sampling", "optimization"])
    archive.put(record)
    assert archive.get("problem").labels == ["optimization", "probability"]
    with pytest.raises(ValueError, match="cycle"):
        Taxonomy(aliases={"a": "b", "b": "a"})
    with pytest.raises(ValueError, match="unknown"):
        taxonomy.normalize(["unsupported label"])
    hits = HybridRetriever(archive).search("10.1234/synthetic", kinds=["result"], depth=1)
    assert [hit.record.id for hit in hits] == ["result"]
    assert any("graph connection" in reason for reason in hits[0].reasons)
