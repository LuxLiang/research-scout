"""SYNTHETIC source-cache fixtures; retrieval does not certify scientific evidence."""
from datetime import date
from hashlib import sha256

import pytest

from research_scout.domain.models import Coverage, Paper, PaperVersion
from research_scout.retrieval.sources import SourceIndex


def source(tmp_path, identifier="v1", *, paper_id="p", text="SYNTHETIC Gaussian smoothing",
           version="1", published=None, coverage=Coverage.PARTIAL_TEXT):
    original = tmp_path / f"{identifier}.pdf"
    original.write_bytes(b"SYNTHETIC SOURCE " + identifier.encode())
    extracted = tmp_path / f"{identifier}.txt"
    extracted.write_bytes(text.encode("utf-8"))
    return PaperVersion(
        id=identifier, paper_id=paper_id, version=version, title="SYNTHETIC source",
        source_path=str(original), text_path=str(extracted),
        content_hash=sha256(original.read_bytes()).hexdigest(),
        published=published, coverage=coverage, synthetic=True,
    )


def test_exact_unicode_offsets_and_parent_expansion_survive_reopening(tmp_path):
    text = "SYNTHETIC\r\n" + "中🙂é " * 350 + "\r\nGaussian theorem\r\n" + "尾🙂 " * 1900
    version = source(tmp_path, text=text, coverage=Coverage.ABSTRACT_ONLY)
    index = SourceIndex(tmp_path / "index.sqlite")
    stats = index.rebuild([version])
    assert stats["indexed_versions"] == 1
    assert stats["indexed_chunks"] > 4
    assert stats["errors"] == stats["missing_versions"] == []
    hit, = SourceIndex(index.path).search("Gaussian")
    assert hit["text"] == text[hit["start"]:hit["end"]]
    assert hit["parent_text"] == text[hit["parent_start"]:hit["parent_end"]]
    assert len(hit["parent_text"]) > len(hit["text"])
    assert hit["parent_start"] <= hit["start"] < hit["end"] <= hit["parent_end"]
    assert hit["coverage"] == "ABSTRACT_ONLY"
    assert hit["source_currentness"] == "VERIFIED"
    assert hit["source_hash"] == version.content_hash
    assert hit["text_hash"] == sha256(text.encode()).hexdigest()
    assert hit["score"] > 0


def test_latest_default_historical_opt_in_and_prelimit_filters(tmp_path):
    old = source(tmp_path, "old", version="9", published=date(2025, 1, 1))
    new = source(tmp_path, "new", version="10", published=date(2026, 1, 1))
    other = source(tmp_path, "other", paper_id="other", text="SYNTHETIC Gaussian")
    paper = Paper(id="p", title="SYNTHETIC paper", version_ids=[old.id, new.id], synthetic=True)
    index = SourceIndex(tmp_path / "index.sqlite")
    index.rebuild([paper, old, other, new])
    assert {hit["version_id"] for hit in index.search("Gaussian")} == {"new", "other"}
    assert index.search("Gaussian", top_k=1, paper_ids=["p"])[0]["version_id"] == "new"
    assert index.search("Gaussian", version_ids=["old"])[0]["version_id"] == "old"
    assert index.search("Gaussian", version_ids=["old"], paper_ids=["other"]) == []
    assert index.search("Gaussian", version_ids=[]) == []
    assert index.search("Gaussian", paper_ids=[]) == []


def test_version_natural_order_with_missing_dates(tmp_path):
    v9 = source(tmp_path, "v9", version="v9")
    v10 = source(tmp_path, "v10", version="v10")
    index = SourceIndex(tmp_path / "index.sqlite")
    index.rebuild([v10, v9])
    assert index.search("Gaussian")[0]["version_id"] == "v10"


def test_same_revision_snapshots_follow_canonical_order_not_content_hash(tmp_path):
    metadata = source(tmp_path, "metadata", version="v1")
    old = source(tmp_path, "old", version="v1+content-ffffffffffff",
                 published=date(2026, 2, 1))
    newest = source(tmp_path, "newest", version="v1+content-000000000000",
                    published=date(2026, 1, 1))
    paper = Paper(id="p", title="SYNTHETIC", version_ids=[metadata.id, old.id, newest.id],
                  synthetic=True)
    index = SourceIndex(tmp_path / "index.sqlite")
    index.rebuild([newest, paper, old, metadata])
    assert index.search("Gaussian")[0]["version_id"] == newest.id
    assert index.search("Gaussian", version_ids=[old.id])[0]["version_id"] == old.id


def test_supersession_leaf_wins_even_with_misleading_version_order(tmp_path):
    old = source(tmp_path, "old", version="v9")
    newest = source(tmp_path, "newest", version="v1").model_copy(
        update={"supersedes_version_id": old.id})
    index = SourceIndex(tmp_path / "index.sqlite")
    index.rebuild([newest, old])
    assert index.search("Gaussian")[0]["version_id"] == newest.id
    from pathlib import Path
    Path(newest.text_path).unlink()
    stats = index.rebuild([old, newest])
    assert stats["missing_versions"] == [newest.id]
    assert index.search("Gaussian") == []
    assert index.search("Gaussian", version_ids=[old.id])[0]["version_id"] == old.id


def test_bad_sources_are_reported_and_missing_latest_never_falls_back(tmp_path):
    old = source(tmp_path, "v1", version="1")
    newest = source(tmp_path, "v2", version="2")
    missing_text = source(tmp_path, "missing-text", paper_id="missing")
    changed = source(tmp_path, "changed", paper_id="changed")
    invalid = source(tmp_path, "invalid", paper_id="invalid")
    empty = source(tmp_path, "empty", paper_id="empty", text="\n  ")
    from pathlib import Path
    Path(newest.source_path).unlink()
    Path(missing_text.text_path).unlink()
    Path(changed.source_path).write_bytes(b"changed")
    Path(invalid.text_path).write_bytes(b"\xff")
    index = SourceIndex(tmp_path / "index.sqlite")
    stats = index.rebuild([old, newest, missing_text, changed, invalid, empty])
    assert stats["indexed_versions"] == 1
    assert stats["missing_versions"] == ["missing-text", "v2"]
    assert len(stats["errors"]) == 5
    assert any("hash mismatch" in item["error"] for item in stats["errors"])
    assert any("UnicodeDecodeError" in item["error"] for item in stats["errors"])
    assert any("empty" in item["error"] for item in stats["errors"])
    assert index.search("Gaussian") == []
    assert index.search("Gaussian", version_ids=["v1"])[0]["version_id"] == "v1"


def test_unreadable_and_absent_text_path_are_explicit(tmp_path, monkeypatch):
    from pathlib import Path
    unreadable = source(tmp_path, "unreadable")
    absent = source(tmp_path, "absent").model_copy(update={"text_path": None})
    original = Path.read_bytes

    def read(path):
        if str(path) == unreadable.text_path:
            raise PermissionError("SYNTHETIC unreadable text")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    stats = SourceIndex(tmp_path / "index.sqlite").rebuild([unreadable, absent])
    assert stats["indexed_versions"] == 0
    assert stats["missing_versions"] == ["absent"]
    assert any("PermissionError" in item["error"] for item in stats["errors"])


def test_text_without_original_keeps_unknown_currentness_and_coverage(tmp_path):
    version = source(tmp_path).model_copy(update={"source_path": None,
                                                 "coverage": Coverage.METADATA_ONLY})
    index = SourceIndex(tmp_path / "index.sqlite")
    index.rebuild([version])
    hit, = index.search("Gaussian")
    assert hit["source_currentness"] == "UNVERIFIABLE"
    assert hit["source_hash"] == version.content_hash
    assert hit["coverage"] == "METADATA_ONLY"


def test_deterministic_rebuild_detects_text_metadata_changes_and_deletions(tmp_path):
    from pathlib import Path
    version = source(tmp_path)
    paper = Paper(id="p", title="SYNTHETIC", version_ids=[version.id], synthetic=True)
    index = SourceIndex(tmp_path / "index.sqlite")
    original = index.rebuild([paper, version])
    hit_id = index.search("Gaussian")[0]["id"]
    assert index.rebuild([version, paper]) == original
    Path(version.text_path).write_text("SYNTHETIC martingale", encoding="utf-8")
    changed = index.rebuild([paper, version])
    assert changed["fingerprint"] != original["fingerprint"]
    assert index.search("Gaussian") == []
    assert index.search("martingale")[0]["id"] != hit_id
    assert index.rebuild([paper.model_copy(update={"title": "SYNTHETIC revised"}), version])[
        "fingerprint"] != changed["fingerprint"]
    empty = index.rebuild([])
    assert empty["indexed_chunks"] == empty["indexed_versions"] == 0
    assert index.search("martingale") == []


def test_failed_publication_preserves_previous_generation(tmp_path, monkeypatch):
    import research_scout.retrieval.sources as module
    version = source(tmp_path)
    index = SourceIndex(tmp_path / "index.sqlite")
    index.rebuild([version])
    previous = index.path.read_bytes()

    def reject(*args):
        raise OSError("SYNTHETIC failed publication")

    monkeypatch.setattr(module.os, "replace", reject)
    with pytest.raises(OSError, match="failed publication"):
        index.rebuild([])
    assert index.path.read_bytes() == previous
    assert index.search("Gaussian")
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("top_k", [0, -1, True, 1.5, "2", None])
def test_invalid_top_k_fails_even_on_empty_index(tmp_path, top_k):
    with pytest.raises(ValueError, match="positive integer"):
        SourceIndex(tmp_path / "index.sqlite").search("Gaussian", top_k=top_k)


def test_queries_are_literal_safe_and_deterministic(tmp_path):
    index = SourceIndex(tmp_path / "index.sqlite")
    versions = [source(tmp_path, "v-b", paper_id="b"), source(tmp_path, "v-a", paper_id="a")]
    index.rebuild(versions)
    assert index.search(" \n") == index.search('"*(){}:') == []
    hits = index.search('Gaussian ") OR * --')
    assert [hit["version_id"] for hit in hits] == ["v-a", "v-b"]
    assert index.search('Gaussian ") OR * --') == hits
    assert index.search("Gaussian", paper_ids=["a') OR 1=1 --"]) == []
    with pytest.raises(ValueError, match="string"):
        index.search(None)


def test_word_boundaries_are_preserved_in_child_and_parent_chunks(tmp_path):
    text = "x " * 597 + "Gaussian " + "x " * 1797 + "martingale " + "x " * 100
    index = SourceIndex(tmp_path / "index.sqlite")
    index.rebuild([source(tmp_path, text=text)])
    assert index.search("Gaussian")
    assert index.search("martingale")


def test_get_pins_ids_and_validates_current_files(tmp_path):
    from pathlib import Path
    version = source(tmp_path)
    index = SourceIndex(tmp_path / "index.sqlite")
    index.rebuild([version])
    hit = index.search("Gaussian")[0]
    assert index.get(hit["id"]) == dict(hit, score=0.0)
    with pytest.raises(KeyError):
        index.get("unknown-id")
    with pytest.raises(KeyError):
        SourceIndex(tmp_path / "absent.sqlite").get(hit["id"])
    Path(version.text_path).write_text("SYNTHETIC changed", encoding="utf-8")
    with pytest.raises(ValueError, match="text changed"):
        index.get(hit["id"])
    index.rebuild([version])
    current = index.search("changed")[0]
    with pytest.raises(KeyError):
        index.get(hit["id"])
    Path(version.source_path).write_bytes(b"SYNTHETIC modified PDF")
    with pytest.raises(ValueError, match="source changed"):
        index.get(current["id"])
    Path(version.source_path).unlink()
    with pytest.raises(ValueError, match="source is unreadable"):
        index.get(current["id"])
