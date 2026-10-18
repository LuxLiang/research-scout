"""Retrieve actual technical changes; never manufacture missing lemmas."""
from __future__ import annotations

from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import (
    AssessmentStatus, Bottleneck, BreakthroughAssessment, Mechanism, PaperVersion,
    PreciseProblem, ProblemStatus, ResolutionKind, Result, stable_id,
)
from research_scout.evolution import ProblemEvolutionTimeline, assess_resolution
from research_scout.evolution.resolution import _fingerprint


class BreakthroughDiscovery:
    def __init__(self, archive: ArchiveProtocol):
        self.archive = archive

    def analyze(
        self, result_id: str, problem_id: str | None = None, *, persist: bool = True,
    ) -> BreakthroughAssessment:
        result = self.archive.get(result_id)
        if not isinstance(result, Result):
            raise TypeError("Breakthrough discovery requires a Result")
        if problem_id is None:
            if len(result.problem_ids) != 1:
                raise ValueError("Specify problem_id for results with zero or multiple problems")
            problem_id = result.problem_ids[0]
        problem = self.archive.get(problem_id)
        if not isinstance(problem, PreciseProblem):
            raise TypeError("Breakthrough discovery requires a PreciseProblem")
        resolution = assess_resolution(self.archive, problem.id, result.id, persist=persist)
        bottleneck_ids = list(dict.fromkeys(problem.bottleneck_ids + result.bottleneck_ids))
        bottlenecks = [self.archive.get(bid) for bid in bottleneck_ids]
        bottlenecks = [b for b in bottlenecks if isinstance(b, Bottleneck)]
        historical_ids = set(problem.known_result_ids + result.previous_result_ids)
        previous_mechanisms: set[str] = set()
        questions = list(resolution.proof_obligations)
        attempts = []
        for bottleneck in bottlenecks:
            for attempt in bottleneck.attempts:
                attempts.append(attempt)
                if attempt.result_id:
                    historical_ids.add(attempt.result_id)
        new_version = self.archive.get(result.version_id)
        for record in self.archive.list("result"):
            if not isinstance(record, Result) or record.id == result.id:
                continue
            if problem.id not in record.problem_ids:
                continue
            version = self.archive.get(record.version_id)
            if (isinstance(version, PaperVersion) and isinstance(new_version, PaperVersion)
                    and version.published and new_version.published
                    and version.published < new_version.published):
                historical_ids.add(record.id)
        historical_ids.discard(result.id)
        history = []
        for rid in sorted(historical_ids):
            historical = self.archive.get(rid)
            if not isinstance(historical, Result):
                continue
            version = self.archive.get(historical.version_id)
            historical_date = version.published or self.archive.get(historical.paper_id).published
            new_date = new_version.published or self.archive.get(result.paper_id).published
            if historical_date and new_date and historical_date > new_date:
                questions.append(f"Excluded {historical.id} from prior history: its source is later than the new result.")
                continue
            if not historical_date or not new_date:
                questions.append(f"Publication chronology for {historical.id} is unknown; verify before treating it as prior work.")
            history.append(historical)
        retained_ids = {r.id for r in history}
        for attempt in attempts:
            if attempt.result_id and attempt.result_id not in retained_ids:
                continue
            if attempt.mechanism_id:
                previous_mechanisms.add(attempt.mechanism_id)
            if attempt.outcome in {"FAILED", "PARTIAL"}:
                reason = attempt.reason or "No failure reason has been attributed."
                questions.append(f"Historical {attempt.outcome.lower()} attempt: "
                                 f"{attempt.description}. {reason}")
        for record in history:
            previous_mechanisms.update(record.mechanism_ids)
        mechanisms = [self.archive.get(mid) for mid in result.mechanism_ids]
        mechanisms = [m for m in mechanisms if isinstance(m, Mechanism)]
        delta = result.technical_delta.strip()
        if not delta:
            delta = "Technical change is not documented in the attributable result record."
            questions.append("Identify the exact failed proof step and new construction from source text.")
        for mechanism in mechanisms:
            if mechanism.necessary_assumptions:
                questions.append(f"Enabling assumptions for {mechanism.id}: "
                                 + "; ".join(mechanism.necessary_assumptions))
            questions.extend(f"Mechanism limitation: {item}" for item in mechanism.limitations)
        for bottleneck in bottlenecks:
            if bottleneck.id not in result.bottleneck_ids:
                questions.append(f"No explicit result attribution establishes overcoming {bottleneck.id}.")
            questions.extend(f"Remaining bottleneck setting: {setting}"
                             for setting in bottleneck.remaining_settings)
        structures = set(problem.structures)
        for bottleneck in bottlenecks:
            structures.update(bottleneck.structures)
        for mechanism in mechanisms:
            structures.update(mechanism.structures)
        analogous = []
        for candidate in self.archive.list("problem"):
            if not isinstance(candidate, PreciseProblem) or candidate.id == problem.id:
                continue
            candidate_bottlenecks = [self.archive.get(bid) for bid in candidate.bottleneck_ids]
            shared_bottleneck = bool(set(candidate.bottleneck_ids) & set(bottleneck_ids))
            candidate_structures = set(candidate.structures)
            for obstruction in candidate_bottlenecks:
                if isinstance(obstruction, Bottleneck):
                    candidate_structures.update(obstruction.structures)
            if not shared_bottleneck and not structures.intersection(candidate_structures):
                continue
            status = ProblemEvolutionTimeline(self.archive, candidate.id).build().status
            if status != ProblemStatus.RESOLVED_SUPPORTED:
                analogous.append(candidate.id)
        qualified = (bool(result.technical_delta.strip()) and bool(mechanisms)
                     and bool(set(result.bottleneck_ids) & set(problem.bottleneck_ids))
                     and resolution.resolution in {
                         ResolutionKind.FULL_RESOLUTION_SUPPORTED,
                         ResolutionKind.CONDITIONAL_RESOLUTION,
                         ResolutionKind.PARTIAL_RESOLUTION,
                     } and resolution.assessment_status == AssessmentStatus.SUPPORTED_BY_SOURCE)
        questions.append("Analog retrieval proposes candidates; transfer validity requires separate proof obligations.")
        evidence = list(dict.fromkeys(result.evidence_ids + [eid for r in history for eid in r.evidence_ids]))
        assessment = BreakthroughAssessment(
            id=stable_id("breakthrough", f"{problem.id}:{result.id}:"
                         f"{_fingerprint(problem, result, *history, *bottlenecks, *mechanisms)}"),
            title=f"Qualified breakthrough candidate: {result.title}",
            problem_id=problem.id, historical_results=[r.id for r in history],
            previous_mechanisms=sorted(previous_mechanisms), bottleneck_ids=bottleneck_ids,
            new_result_id=result.id, new_mechanism_ids=result.mechanism_ids,
            technical_delta=delta, resolution_scope=resolution.resolution,
            evidence_ids=evidence, unresolved_questions=list(dict.fromkeys(questions)),
            analogous_problem_ids=sorted(analogous),
            assessment_status=(AssessmentStatus.NEEDS_REVIEW if resolution.needs_review
                               else AssessmentStatus.SUPPORTED_BY_SOURCE if qualified
                               else AssessmentStatus.UNCERTAIN),
            needs_review=resolution.needs_review,
            synthetic=result.synthetic or problem.synthetic,
            provenance="scout:historical-breakthrough-retrieval",
        )
        if persist:
            try:
                existing = self.archive.get(assessment.id)
            except KeyError:
                existing = None
            if isinstance(existing, BreakthroughAssessment):
                if assessment.needs_review and not existing.needs_review:
                    return self.archive.put(existing.model_copy(update={
                        "needs_review": True, "assessment_status": AssessmentStatus.NEEDS_REVIEW,
                    }))
                return existing
            self.archive.put(assessment)
        return assessment
