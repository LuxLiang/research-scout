"""Conservative comparisons: string resemblance never establishes implication."""
from __future__ import annotations

import hashlib
import json

from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import (
    AssessmentStatus, BreakthroughAssessment, Coverage, Evidence, LiteratureDelta,
    PaperVersion, PreciseProblem, ResolutionAssessment, ResolutionKind, Result, now, stable_id,
)

QUALIFIED = {AssessmentStatus.SUPPORTED_BY_SOURCE, AssessmentStatus.INDEPENDENTLY_REVIEWED}


def _fingerprint(*records) -> str:
    # Ignore transport timestamps; scientific content and review revisions are material.
    payload = [r.model_dump(mode="json", exclude={"created_at", "updated_at"}) for r in records]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]


def superseding_versions(archive: ArchiveProtocol, result: Result) -> list[str]:
    """Supersession is intrinsic source state, independent of cached assessments.

    PaperVersion supersession also captures source enrichment/content changes.
    The ordered Paper version list covers imported versions lacking an explicit
    supersedes link. Historical readers may filter that list by scientific and
    recording dates before this function is called.
    """
    versions = [v for v in archive.list("paper_version")
                if isinstance(v, PaperVersion) and v.paper_id == result.paper_id]
    available = {v.id for v in versions}
    successors = {v.id for v in versions if v.supersedes_version_id == result.version_id}
    paper = archive.get(result.paper_id)
    if result.version_id in paper.version_ids:
        index = paper.version_ids.index(result.version_id)
        successors.update(vid for vid in paper.version_ids[index + 1:] if vid in available)
    return sorted(successors)


def usable_result_evidence(archive: ArchiveProtocol, result: Result) -> tuple[list[str], list[str]]:
    """Check attribution to the exact source; this does not validate a proof."""
    usable, warnings = [], []
    version = archive.get(result.version_id)
    if not isinstance(version, PaperVersion) or version.paper_id != result.paper_id:
        return [], ["Result source version does not belong to the stated paper."]
    successors = superseding_versions(archive, result)
    if successors:
        warnings.append("Source version has been superseded; re-review against "
                        + ", ".join(successors) + " is required.")
    if version.coverage not in {Coverage.FULL_TEXT, Coverage.PARTIAL_TEXT}:
        warnings.append("Source analysis is metadata/abstract only; theorem-level support unavailable.")
    for eid in result.evidence_ids:
        ev = archive.get(eid)
        if not isinstance(ev, Evidence):
            warnings.append(f"{eid} is not an evidence record.")
        elif (ev.paper_id, ev.version_id) != (result.paper_id, result.version_id):
            warnings.append(f"{eid} attributes a different paper/version.")
        elif ev.coverage not in {Coverage.FULL_TEXT, Coverage.PARTIAL_TEXT}:
            warnings.append(f"{eid} is not full/partial text evidence.")
        elif ev.assessment_status not in QUALIFIED:
            warnings.append(f"{eid} attribution has not been supported or reviewed.")
        elif version.coverage in {Coverage.FULL_TEXT, Coverage.PARTIAL_TEXT}:
            usable.append(eid)
    if result.assessment_status not in QUALIFIED:
        warnings.append("Result is an extracted/proposed/challenged claim, not qualified support.")
    return usable, warnings


def assess_resolution(
    archive: ArchiveProtocol, problem_id: str, result_id: str, *, persist: bool = True,
) -> ResolutionAssessment:
    """Compare exact formulation dimensions and explicit conjunctive assumptions.

    Dropping identical conjuncts is safe; no synonym matching or mathematical
    implication is attempted. FULL_RESOLUTION_SUPPORTED means attributed source
    support, never an automatic claim of mathematical correctness.
    """
    problem, result = archive.get(problem_id), archive.get(result_id)
    if not isinstance(problem, PreciseProblem) or not isinstance(result, Result):
        raise TypeError("Resolution requires a PreciseProblem and Result")
    original, achieved = problem.scope, result.scope
    evidence, warnings = usable_result_evidence(archive, result)
    stale = bool(superseding_versions(archive, result))
    obligations = list(warnings)
    dimensions = ("domain", "model", "objective", "metric", "quantifiers")
    mismatches = [name for name in dimensions if getattr(original, name) != getattr(achieved, name)]
    orig_assumptions, new_assumptions = set(original.assumptions), set(achieved.assumptions)
    status = AssessmentStatus.UNCERTAIN
    if problem_id not in result.problem_ids:
        resolution = ResolutionKind.NOT_A_RESOLUTION
        rationale = "Result does not identify this precise problem as an addressed problem."
    elif not original.quantifiers or not achieved.quantifiers:
        resolution = ResolutionKind.INSUFFICIENT_EVIDENCE
        rationale = "Explicit quantifiers are missing from the original or achieved formulation."
        obligations.append("Specify the original and achieved quantified scope before assessing resolution.")
    elif mismatches:
        resolution = ResolutionKind.INCOMPARABLE
        rationale = "Formulations differ in " + ", ".join(mismatches) + "."
        obligations.append("Establish an explicit reduction for the differing formulation dimensions.")
    elif not (orig_assumptions <= new_assumptions or new_assumptions <= orig_assumptions):
        resolution = ResolutionKind.INCOMPARABLE
        rationale = "Assumption sets differ without a known inclusion or implication."
        obligations.append("Prove the required implication between the different assumptions.")
    elif not evidence or warnings:
        resolution = ResolutionKind.CLAIMED_BUT_UNVERIFIED
        rationale = "The result has insufficient qualified evidence to establish resolution scope."
    elif result.result_type == "EMPIRICAL":
        resolution = ResolutionKind.INSUFFICIENT_EVIDENCE
        rationale = "An empirical observation does not establish a general quantified guarantee."
        obligations.append("Specify and validate an empirical objective or supply the required theorem.")
    elif original.guarantee != achieved.guarantee:
        if achieved.unresolved:
            resolution = ResolutionKind.PARTIAL_RESOLUTION
            rationale = "The source reports a scoped result and explicitly retains unresolved settings."
        else:
            resolution = ResolutionKind.INCOMPARABLE
            rationale = "Different guarantee strings have no established logical ordering."
        obligations.append("Prove that the achieved guarantee implies the original target guarantee.")
    elif achieved.unresolved:
        resolution = ResolutionKind.PARTIAL_RESOLUTION
        rationale = "Explicit unresolved settings prevent complete resolution of the original scope."
    elif orig_assumptions < new_assumptions:
        resolution = ResolutionKind.CONDITIONAL_RESOLUTION
        rationale = "The target guarantee is supported only under additional assumptions: " + "; ".join(
            sorted(new_assumptions - orig_assumptions)
        )
        obligations.append("Remove the additional assumptions before closing the original problem.")
    else:
        resolution = ResolutionKind.FULL_RESOLUTION_SUPPORTED
        rationale = "Exact target formulation is supported under identical or fewer explicit conjuncts."
    if evidence and not warnings and resolution not in {
        ResolutionKind.NOT_A_RESOLUTION, ResolutionKind.INCOMPARABLE,
        ResolutionKind.INSUFFICIENT_EVIDENCE,
    }:
        status = AssessmentStatus.SUPPORTED_BY_SOURCE
    rationale += " Source support is evidence attribution, not independent mathematical verification."
    assessment = ResolutionAssessment(
        id=stable_id("resolution", f"{problem_id}:{result_id}:{_fingerprint(problem, result)}"),
        title=f"Resolution scope: {result.title} → {problem.title}",
        problem_id=problem_id, result_id=result_id, resolution=resolution,
        original_scope=original, achieved_scope=achieved, rationale=rationale,
        proof_obligations=obligations, evidence_ids=result.evidence_ids,
        assessment_status=AssessmentStatus.NEEDS_REVIEW if stale else status,
        needs_review=stale, synthetic=problem.synthetic or result.synthetic,
        provenance="scout:exact-scope-comparison",
    )
    if persist:
        try:
            existing = archive.get(assessment.id)
        except KeyError:
            existing = None
        if isinstance(existing, ResolutionAssessment):
            if stale and not existing.needs_review:
                return archive.put(existing.model_copy(update={
                    "needs_review": True, "assessment_status": AssessmentStatus.NEEDS_REVIEW,
                }))
            return existing
        archive.put(assessment)
    return assessment


def flag_version_review(
    archive: ArchiveProtocol, old_version_id: str, new_version_id: str,
) -> list[str]:
    """Invalidate dependent mutable projections; immutable source/events survive.

    Both versions must already exist. Propagate transitively through result,
    comparison, resolution and breakthrough references, preserving revisions.
    """
    old, new = archive.get(old_version_id), archive.get(new_version_id)
    if not isinstance(old, PaperVersion) or not isinstance(new, PaperVersion):
        raise TypeError("Expected paper versions")
    if old.paper_id != new.paper_id or old.id == new.id:
        raise ValueError("Re-review requires different versions of the same paper")
    records = archive.list()
    affected = {old_version_id}
    affected.update(r.id for r in records if isinstance(r, Result) and r.version_id == old_version_id)
    updates = []
    changed = True
    while changed:
        changed = False
        for record in records:
            if isinstance(record, LiteratureDelta):
                dependencies = {record.version_id, record.previous_version_id, record.new_result_id,
                                *record.compared_result_ids}
            elif isinstance(record, ResolutionAssessment):
                dependencies = {record.result_id}
            elif isinstance(record, BreakthroughAssessment):
                dependencies = {record.new_result_id, *record.historical_results}
            else:
                continue
            if dependencies & affected and record.id not in affected:
                affected.add(record.id)
                changed = True
                if record.needs_review:
                    continue
                change = dict(needs_review=True, assessment_status=AssessmentStatus.NEEDS_REVIEW,
                              updated_at=now())
                if isinstance(record, LiteratureDelta):
                    change["invalidated_by_version_id"] = new_version_id
                updates.append(record.model_copy(update=change))
    if updates:
        archive.put_many(updates)
    return [r.id for r in updates]
