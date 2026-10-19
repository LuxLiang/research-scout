"""Research-review persistence gates; all scientific examples are SYNTHETIC."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from research_scout.cli import app
from research_scout.configuration import WorkspaceConfig
from research_scout.integration import export_proposal
from research_scout.opportunities.reviews import ResearchReview, ResearchReviewService
from research_scout.storage import Archive
from research_scout.workflows.demo import run_demo


@pytest.fixture
def setup_review(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "config.json").write_text(WorkspaceConfig().model_dump_json())
    archive = Archive(workspace / "knowledge")
    opportunity_id = run_demo(archive)["opportunity_id"]
    artifact = workspace / "notes" / "proof.md"
    artifact.parent.mkdir()
    artifact.write_text("SYNTHETIC conditional derivation; not independently verified.\n")
    payload = {
        "opportunity_id": opportunity_id,
        "reviewer": "synthetic-test-reviewer",
        "summary": "SYNTHETIC source review narrows a research question.",
        "decision": "CONTINUE_NARROWED",
        "revised_question": "SYNTHETIC: prove a uniform bound under stated moments.",
        "findings": [{
            "kind": "CONDITIONAL_DERIVATION",
            "claim": "SYNTHETIC conditional local estimate.",
            "scope": "Artificial finite-dimensional test dynamics only.",
            "assumptions": ["SYNTHETIC bounded test moments"],
            "metric": "SYNTHETIC weighted distance",
            "limitation": "No independent proof review or novelty determination.",
        }],
        "remaining_work": ["Independently check the synthetic argument."],
        "artifacts": [{
            "path": "notes/proof.md",
            "sha256": sha256(artifact.read_bytes()).hexdigest(),
            "role": "PROOF_NOTES",
        }],
        "source_evidence_ids": ["evidence-a-problem"],
    }
    return archive, workspace, artifact, payload


def test_review_appends_without_changing_scientific_status(setup_review):
    archive, workspace, _, payload = setup_review
    before = archive.get(payload["opportunity_id"])
    service = ResearchReviewService(archive, workspace)
    after = service.record(ResearchReview.model_validate(payload))
    assert after.revision == before.revision + 1
    assert after.history[:-1] == before.history
    assert after.history[-1]["action"] == "RESEARCH_REVIEW"
    assert after.history[-1]["review_fingerprint"]
    assert after.status == before.status
    assert after.ranking == before.ranking
    assert after.assessment_status == before.assessment_status
    assert after.novelty_assessment == before.novelty_assessment
    reviews = service.reviews(after.id)
    assert len(reviews) == 1
    assert reviews[0]["decision"] == "CONTINUE_NARROWED"
    assert reviews[0]["novelty"] == "UNDETERMINED"
    assert reviews[0]["origin"] == "SYSTEM_INFERENCE"
    assert reviews[0]["findings"][0]["verification"] == "NOT_INDEPENDENTLY_VERIFIED"
    assert archive.validate() == []


def test_repeat_is_idempotent_and_review_fingerprint_is_stable(setup_review):
    archive, workspace, _, payload = setup_review
    service = ResearchReviewService(archive, workspace)
    review = ResearchReview.model_validate(payload)
    first = service.record(review)
    history = archive.history(first.id)
    repeated = service.record(review)
    assert repeated == first
    assert repeated.history[-1]["review_fingerprint"] == first.history[-1]["review_fingerprint"]
    assert archive.history(first.id) == history
    assert len(service.reviews(first.id)) == 1


def test_distinct_review_preserves_old_payload_and_status(setup_review):
    archive, workspace, artifact, payload = setup_review
    service = ResearchReviewService(archive, workspace)
    first = service.record(ResearchReview.model_validate(payload))
    old_reviews = deepcopy(service.reviews(first.id))
    old_revisions = archive.history(first.id)
    artifact.write_text("SYNTHETIC revised derivation with a narrower conclusion.\n")
    revised = deepcopy(payload)
    revised["decision"] = "DOWNRANK"
    revised["summary"] = "SYNTHETIC exact baseline weakens the proposed contribution."
    revised["artifacts"][0]["sha256"] = sha256(artifact.read_bytes()).hexdigest()
    second = service.record(ResearchReview.model_validate(revised))
    assert second.history[:-1] == first.history
    assert second.status == first.status
    assert second.ranking == first.ranking
    assert service.reviews(second.id)[:1] == old_reviews
    assert service.reviews(second.id)[1]["decision"] == "DOWNRANK"
    assert archive.history(second.id)[:-1] == old_revisions
    assert second.history[-1]["review_fingerprint"] != first.history[-1]["review_fingerprint"]


@pytest.mark.parametrize("case", ["forged_hash", "escape", "absolute", "symlink", "missing", "directory"])
def test_artifact_rejection_is_atomic(setup_review, tmp_path, case):
    archive, workspace, artifact, payload = setup_review
    before = archive.get(payload["opportunity_id"])
    before_records = archive.list()
    extra = deepcopy(payload["artifacts"][0])
    second_artifact = workspace / "notes" / "second.md"
    second_artifact.write_bytes(artifact.read_bytes())
    extra["path"] = "notes/second.md"
    if case == "forged_hash":
        extra["sha256"] = "0" * 64
    elif case in {"escape", "symlink"}:
        outside = tmp_path / "outside.md"
        outside.write_bytes(artifact.read_bytes())
        if case == "escape":
            extra["path"] = "../outside.md"
        else:
            (workspace / "linked.md").symlink_to(outside)
            extra["path"] = "linked.md"
    elif case == "absolute":
        extra["path"] = str(artifact)
    elif case == "missing":
        extra["path"] = "missing.md"
    else:
        extra["path"] = "notes"
    # The first valid artifact must not cause publication before the bad second one.
    payload["artifacts"].append(extra)
    with pytest.raises((ValueError, OSError)):
        ResearchReviewService(archive, workspace).record(ResearchReview.model_validate(payload))
    assert archive.get(before.id) == before
    assert archive.list() == before_records
    assert ResearchReviewService(archive, workspace).reviews(before.id) == []


@pytest.mark.parametrize("identifier", ["paper-a", "result-b", "no-such-evidence"])
def test_source_references_must_resolve_to_evidence(setup_review, identifier):
    archive, workspace, _, payload = setup_review
    before = archive.get(payload["opportunity_id"])
    payload["source_evidence_ids"] = [identifier]
    with pytest.raises((ValueError, TypeError, KeyError)):
        ResearchReviewService(archive, workspace).record(ResearchReview.model_validate(payload))
    assert archive.get(before.id) == before


@pytest.mark.parametrize("identifier", ["paper-a", "no-such-opportunity"])
def test_review_target_must_be_existing_opportunity(setup_review, identifier):
    archive, workspace, _, payload = setup_review
    before = archive.list()
    payload["opportunity_id"] = identifier
    with pytest.raises((ValueError, TypeError, KeyError)):
        ResearchReviewService(archive, workspace).record(ResearchReview.model_validate(payload))
    assert archive.list() == before


@pytest.mark.parametrize("promotion", ["novelty", "origin", "verification", "unknown"])
def test_review_cannot_promote_own_claims_or_add_untyped_fields(setup_review, promotion):
    _, _, _, payload = setup_review
    if promotion == "verification":
        payload["findings"][0]["verification"] = "INDEPENDENTLY_VERIFIED"
    elif promotion == "novelty":
        payload["novelty"] = "CONFIRMED_NOVEL"
    elif promotion == "origin":
        payload["origin"] = "AUTHOR"
    else:
        payload["scientifically_verified"] = True
    with pytest.raises(ValidationError):
        ResearchReview.model_validate(payload)


def test_hash_is_content_bound_not_just_a_well_formed_digest(setup_review):
    archive, workspace, artifact, payload = setup_review
    before = archive.get(payload["opportunity_id"])
    artifact.write_text("SYNTHETIC artifact edited after the review was prepared.\n")
    with pytest.raises(ValueError):
        ResearchReviewService(archive, workspace).record(ResearchReview.model_validate(payload))
    assert archive.get(before.id) == before


def test_model_copy_cannot_bypass_scientific_review_gates(setup_review):
    archive, workspace, _, payload = setup_review
    before = archive.get(payload['opportunity_id'])
    forged = ResearchReview.model_validate(payload).model_copy(update={'novelty': 'CONFIRMED_NOVEL'})
    with pytest.raises(ValidationError):
        ResearchReviewService(archive, workspace).record(forged)
    assert archive.get(before.id) == before


def test_cli_record_read_and_repeat_are_offline_and_idempotent(setup_review):
    archive, workspace, _, payload = setup_review
    source = workspace / "review.json"
    source.write_text(json.dumps(payload))
    runner = CliRunner()
    prefix = ["--workspace", str(workspace)]
    recorded = runner.invoke(app, prefix + ["review-opportunity", str(source)])
    assert recorded.exit_code == 0, (recorded.stdout, recorded.exception)
    first = json.loads(recorded.stdout)
    repeated = runner.invoke(app, prefix + ["review-opportunity", str(source)])
    assert repeated.exit_code == 0, (repeated.stdout, repeated.exception)
    assert json.loads(repeated.stdout) == first
    listed = runner.invoke(app, prefix + ["opportunity-reviews", payload["opportunity_id"]])
    assert listed.exit_code == 0, (listed.stdout, listed.exception)
    reviews = json.loads(listed.stdout)
    assert len(reviews) == 1
    assert reviews[0]["summary"] == payload["summary"]
    assert reviews[0]["artifacts"] == payload["artifacts"]
    assert archive.get(payload["opportunity_id"]).revision == first["revision"]


def test_harness_export_contains_retained_review_and_preserves_status(setup_review):
    archive, workspace, _, payload = setup_review
    before = archive.get(payload["opportunity_id"])
    service = ResearchReviewService(archive, workspace)
    reviewed = service.record(ResearchReview.model_validate(payload))
    destination = workspace / "proposal.md"
    export_proposal(archive, reviewed.id, destination)
    exported = destination.read_text()
    for text in [payload["summary"], payload["decision"], payload["revised_question"],
                 payload["findings"][0]["claim"], payload["findings"][0]["limitation"],
                 payload["artifacts"][0]["path"], payload["artifacts"][0]["sha256"],
                 "NOT_INDEPENDENTLY_VERIFIED", "UNDETERMINED"]:
        assert text in exported
    assert archive.get(reviewed.id).status == before.status
    assert archive.get(reviewed.id) == reviewed


@pytest.mark.parametrize("tamper", ["summary", "opportunity_id", "review_fingerprint"])
def test_read_rejects_tampered_retained_review(setup_review, tamper):
    archive, workspace, _, payload = setup_review
    service = ResearchReviewService(archive, workspace)
    reviewed = service.record(ResearchReview.model_validate(payload))
    history = deepcopy(reviewed.history)
    if tamper == "review_fingerprint":
        history[-1]["review_fingerprint"] = "research-review-" + "0" * 64
    else:
        history[-1]["review"][tamper] = "SYNTHETIC forged content"
    corrupted = reviewed.model_copy(update={"history": history})

    class TamperedArchive:
        """Simulate imported corrupt storage without mutating the real archive."""

        def get(self, identifier):
            assert identifier == reviewed.id
            return corrupted

    with pytest.raises(ValueError):
        ResearchReviewService(TamperedArchive(), workspace).reviews(reviewed.id)
    assert archive.get(reviewed.id) == reviewed
