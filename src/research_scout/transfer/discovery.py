"""Bottleneck-grounded discovery with explicit, unproved transfer obligations."""
from __future__ import annotations

import hashlib
import json

from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import (
    AssessmentStatus, Attempt, Bottleneck, BottleneckStatus, BreakthroughAssessment,
    Mechanism, Opportunity, OpportunityStatus, PreciseProblem, ProblemStatus, Result,
    TransferHypothesis, TransferMode, now, stable_id,
)
from research_scout.evolution import ProblemEvolutionTimeline
from research_scout.novelty import NoveltyAudit


def _mode(value: TransferMode | str) -> TransferMode:
    return TransferMode(str(value).replace("-", "_").upper())


def _fingerprint(*records) -> str:
    value = [(r.id, r.revision) for r in records if r is not None]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


class IneligibleTransferError(ValueError):
    """A retrieval lead lacks the explicit scientific context needed for a candidate."""


class TransferDiscovery:
    def __init__(self, archive: ArchiveProtocol):
        self.archive = archive

    def _get(self, identifier, cls):
        record = self.archive.get(identifier)
        if not isinstance(record, cls):
            raise TypeError(f"{identifier} must be a {cls.__name__}")
        return record

    def _bottlenecks(self, problem: PreciseProblem) -> list[Bottleneck]:
        ids = set(problem.bottleneck_ids)
        ids.update(b.id for b in self.archive.list("bottleneck") if problem.id in b.problem_ids)
        return [self._get(i, Bottleneck) for i in sorted(ids)
                if self._get(i, Bottleneck).status != BottleneckStatus.REFUTED_BOTTLENECK]

    def _structure(self, problem: PreciseProblem) -> set[str]:
        return set(problem.structures).union(*(set(b.structures) for b in self._bottlenecks(problem)))

    def _unresolved(self, problem: PreciseProblem) -> bool:
        snapshot = ProblemEvolutionTimeline(self.archive, problem.id).build()
        return snapshot.status != ProblemStatus.RESOLVED_SUPPORTED or snapshot.requires_review

    def propose(
        self, mechanism_id: str, target_problem_id: str, *,
        mode: TransferMode | str = TransferMode.TECHNIQUE_FIRST,
        breakthrough_id: str | None = None, previous_transfer_id: str | None = None,
        persist: bool = True,
    ) -> TransferHypothesis:
        mode = _mode(mode)
        mechanism = self._get(mechanism_id, Mechanism)
        target = self._get(target_problem_id, PreciseProblem)
        if not previous_transfer_id:
            failures = [t for t in self.archive.list("transfer")
                        if t.source_mechanism_id == mechanism.id
                        and t.target_problem_id == target.id and t.mode == mode
                        and t.outcome == "FAILED"
                        and (breakthrough_id is None or t.breakthrough_id == breakthrough_id)]
            if failures:
                return max(failures, key=lambda t: t.updated_at)
        breakthroughs = [b for b in self.archive.list("breakthrough")
                        if mechanism.id in b.new_mechanism_ids]
        breakthrough = (self._get(breakthrough_id, BreakthroughAssessment) if breakthrough_id
                        else max(breakthroughs, key=lambda b: b.created_at, default=None))
        if breakthrough and mechanism.id not in breakthrough.new_mechanism_ids:
            raise ValueError("Breakthrough does not attribute this mechanism")
        if mode == TransferMode.BREAKTHROUGH_FIRST and breakthrough is None:
            raise ValueError("Breakthrough-first discovery requires an archived breakthrough assessment")
        previous = (self._get(previous_transfer_id, TransferHypothesis)
                    if previous_transfer_id else None)
        if mode == TransferMode.FAILURE_FIRST and (previous is None or previous.outcome != "FAILED"):
            raise ValueError("Failure-first discovery requires a retained failed transfer")
        if previous and previous.target_problem_id != target.id:
            raise ValueError("A failure retry must preserve the target problem")
        sources = [r for r in self.archive.list("result") if mechanism.id in r.mechanism_ids
                   and any(i != target.id for i in r.problem_ids)]
        if breakthrough:
            result = self._get(breakthrough.new_result_id, Result)
            source = self._get(breakthrough.problem_id, PreciseProblem)
        elif sources:
            result = max(sources, key=lambda r: (r.created_at, r.id))
            source = self._get(next(i for i in result.problem_ids if i != target.id), PreciseProblem)
        else:
            # Applications preserve the source context even when no theorem is archived.
            applications = [a for a in self.archive.list("application")
                            if a.mechanism_id == mechanism.id and a.problem_id != target.id]
            if not applications:
                raise IneligibleTransferError("Mechanism needs an archived source result or application")
            app = sorted(applications, key=lambda a: a.id)[0]
            source = self._get(app.problem_id, PreciseProblem)
            result = self._get(app.result_id, Result) if app.result_id else None
        if source.id == target.id:
            raise IneligibleTransferError("Source and target must be distinct precise problems")
        source_bottlenecks = self._bottlenecks(source)
        target_bottlenecks = self._bottlenecks(target)
        if not source_bottlenecks or not target_bottlenecks:
            raise IneligibleTransferError("Both source and target require explicit unresolved bottlenecks")
        relevant = set(mechanism.bottleneck_ids) | (set(result.bottleneck_ids) if result else set())
        source_b = max(source_bottlenecks, key=lambda b: (b.id in relevant, b.id))
        target_b = max(target_bottlenecks, key=lambda b: (
            len(set(b.structures) & (set(source_b.structures) | set(mechanism.structures))), b.id))
        shared = sorted((self._structure(source) | set(mechanism.structures))
                        & self._structure(target))
        if not shared and source_b.id != target_b.id:
            raise IneligibleTransferError("No explicit shared structure or bottleneck supports this candidate")
        if source_b.id == target_b.id and not shared:
            shared = [f"shared registered obstruction: {source_b.id}"]
        differences = []
        for name in ("domain", "model", "objective", "metric", "guarantee", "quantifiers"):
            left, right = getattr(source.scope, name), getattr(target.scope, name)
            if left != right:
                differences.append(f"{name}: source {left!r}; target {right!r}")
        source_only = sorted(set(source.scope.assumptions) - set(target.scope.assumptions))
        target_only = sorted(set(target.scope.assumptions) - set(source.scope.assumptions))
        if source_only:
            differences.append("Source assumptions not established at target: " + "; ".join(source_only))
        if target_only:
            differences.append("Target assumptions not present at source: " + "; ".join(target_only))
        if source_b.obstruction != target_b.obstruction:
            differences.append(f"Obstruction changes from {source_b.obstruction!r} to {target_b.obstruction!r}")
        if not differences:
            differences.append("Exact formulations coincide; mechanism-level novelty still needs source comparison.")
        assumptions = list(dict.fromkeys(target.scope.assumptions + mechanism.necessary_assumptions))
        missing = [
            f"Construct {mechanism.construction or mechanism.principle} on target model {target.scope.model}.",
            f"Prove that the adapted construction controls obstruction: {target_b.obstruction}.",
            f"Derive {target.scope.guarantee} in {target.scope.metric} for quantifiers: "
            + "; ".join(target.scope.quantifiers or ["target quantifiers require specification"]),
        ]
        missing.extend(f"Establish target validity of necessary assumption: {a}."
                       for a in mechanism.necessary_assumptions if a not in target.scope.assumptions)
        missing.extend(f"Close unresolved target setting: {x}."
                       for x in target.unresolved_scope + target_b.remaining_settings)
        counterexamples = list(dict.fromkeys(source_b.counterexamples + target_b.counterexamples
                                            + mechanism.limitations))
        counterexamples.append(
            f"Search for an admissible {target.scope.model} instance where {target_b.obstruction} "
            "persists despite the proposed construction."
        )
        if previous:
            missing.append(f"Resolve retained failure {previous.id}: {previous.failure_reason}")
            counterexamples.extend(previous.likely_counterexamples)
        evidence = sorted(set(source.evidence_ids + target.evidence_ids + mechanism.evidence_ids
                              + source_b.evidence_ids + target_b.evidence_ids
                              + (result.evidence_ids if result else [])
                              + (breakthrough.evidence_ids if breakthrough else [])
                              + (previous.evidence_ids if previous else [])))
        fingerprint = _fingerprint(source, target, mechanism, source_b, target_b, result,
                                   breakthrough, previous)
        hypothesis = TransferHypothesis(
            id=stable_id("transfer", f"{mode}:{mechanism.id}:{target.id}:{fingerprint}"),
            title=f"Transfer candidate: {mechanism.title} → {target.title}", mode=mode,
            source_problem_id=source.id, source_bottleneck_id=source_b.id,
            source_mechanism_id=mechanism.id, breakthrough_id=breakthrough.id if breakthrough else None,
            target_problem_id=target.id, target_bottleneck_id=target_b.id,
            shared_structures=shared, structural_differences=differences,
            required_assumptions=assumptions, missing_lemmas=list(dict.fromkeys(missing)),
            likely_counterexamples=list(dict.fromkeys(counterexamples)),
            proposed_result=(f"Conjectured target guarantee: {target.desired_result}. "
                             f"Adapt {mechanism.title} to address {target_b.description}; "
                             "all listed assumptions and lemmas remain obligations."),
            first_falsification_test=(
                f"In the smallest admissible {target.scope.model} example, compute the proposed "
                f"construction and test whether it controls {target_b.obstruction} in "
                f"{target.scope.metric}. Vary each target assumption separately; a violating "
                "admissible instance falsifies the claim, while passing does not prove it."
                + (f" First reproduce and address the retained failure: {previous.failure_reason}."
                   if previous else "")
            ),
            uncertainty=("Structural retrieval is a hypothesis, not a valid transfer or a proof. "
                         "Necessary assumptions have not been logically derived from target assumptions. "
                         + (f"Historical technical change: {breakthrough.technical_delta} "
                            if breakthrough else "Historical breakthrough attribution is unavailable. ")
                         + ("Breakthrough needs re-review. " if breakthrough and breakthrough.needs_review else "")
                         + (f"Prior failed attempt: {previous.failure_reason}. " if previous else "")
                         + "Novelty and mathematical correctness require independent review."),
            previous_transfer_id=previous.id if previous else None,
            evidence_ids=evidence, assessment_status=AssessmentStatus.PROPOSED,
            synthetic=source.synthetic or target.synthetic or mechanism.synthetic,
            provenance="scout:structure-and-history-transfer",
        )
        audit = NoveltyAudit(self.archive).audit(hypothesis)
        hypothesis.prior_art_ids = sorted(set(audit.comparable_result_ids + audit.related_result_ids))
        if persist:
            try:
                existing = self.archive.get(hypothesis.id)
                if isinstance(existing, TransferHypothesis):
                    return existing  # Never overwrite a failed or reviewed attempt on rediscovery.
            except KeyError:
                pass
            return self.archive.put(hypothesis)
        return hypothesis

    def discover(self, mode: TransferMode | str, seed_id: str) -> list[TransferHypothesis]:
        mode = _mode(mode)
        candidates = []
        if mode == TransferMode.TECHNIQUE_FIRST:
            mechanism = self._get(seed_id, Mechanism)
            pairs = [(mechanism.id, p.id, None, None) for p in self.archive.list("problem")
                     if self._unresolved(p)]
        elif mode == TransferMode.PROBLEM_FIRST:
            target = self._get(seed_id, PreciseProblem)
            pairs = [(m.id, target.id, None, None) for m in self.archive.list("mechanism")]
        elif mode == TransferMode.BREAKTHROUGH_FIRST:
            breakthrough = self._get(seed_id, BreakthroughAssessment)
            target_ids = set(breakthrough.analogous_problem_ids)
            # Also search fresh additions using the same explicit structure gate in propose.
            target_ids.update(p.id for p in self.archive.list("problem")
                              if p.id != breakthrough.problem_id and self._unresolved(p))
            pairs = [(m, p, breakthrough.id, None) for m in breakthrough.new_mechanism_ids
                     for p in sorted(target_ids) if self._unresolved(self._get(p, PreciseProblem))]
        else:
            failed = self._get(seed_id, TransferHypothesis)
            if failed.outcome != "FAILED":
                raise ValueError("Failure-first seed must be a retained failed transfer")
            pairs = [(m.id, failed.target_problem_id, None, failed.id)
                     for m in self.archive.list("mechanism")]
        for mechanism, problem, breakthrough, previous in pairs:
            try:
                candidates.append(self.propose(mechanism, problem, mode=mode,
                                              breakthrough_id=breakthrough,
                                              previous_transfer_id=previous))
            except IneligibleTransferError:
                # A candidate lacking source history, bottlenecks or structure is excluded.
                continue
        return sorted(candidates, key=lambda t: t.id)

    def record_failure(
        self, transfer_id: str, reason: str, *, counterexamples: list[str] | None = None,
        evidence_ids: list[str] | None = None,
    ) -> TransferHypothesis:
        if not reason.strip():
            raise ValueError("Failure reason must be nonempty")
        transfer = self._get(transfer_id, TransferHypothesis)
        if transfer.outcome == "FAILED":
            if transfer.failure_reason == reason and set(counterexamples or []).issubset(transfer.likely_counterexamples):
                return transfer
            raise ValueError("Retain the original failure; record a new transfer for a new attempt")
        evidence_ids = evidence_ids or []
        failure = transfer.model_copy(update={
            "outcome": "FAILED", "failure_reason": reason,
            "likely_counterexamples": list(dict.fromkeys(transfer.likely_counterexamples + (counterexamples or []))),
            "evidence_ids": sorted(set(transfer.evidence_ids + evidence_ids)),
            "assessment_status": AssessmentStatus.CHALLENGED,
            "uncertainty": (transfer.uncertainty + " Reported failure: " + reason
                            + ". Counterexample admissibility under the target assumptions "
                            "requires review; an example outside that scope does not refute "
                            "the scoped target guarantee."),
        })
        mechanism = self._get(transfer.source_mechanism_id, Mechanism)
        bottleneck = self._get(transfer.target_bottleneck_id, Bottleneck)
        attempt = Attempt(description=f"Transfer {transfer.id} to {transfer.target_problem_id}",
                          outcome="FAILED", mechanism_id=mechanism.id, reason=reason,
                          evidence_ids=evidence_ids)
        updated_mechanism = mechanism.model_copy(update={"attempts": mechanism.attempts + [attempt]})
        updated_bottleneck = bottleneck.model_copy(update={"attempts": bottleneck.attempts + [attempt]})
        blocked = []
        for opportunity in self.archive.list("opportunity"):
            if (not isinstance(opportunity, Opportunity) or opportunity.transfer_id != transfer.id
                    or opportunity.status in {OpportunityStatus.REJECTED, OpportunityStatus.ARCHIVED}):
                continue
            history = opportunity.history + [{
                "timestamp": now().isoformat(), "from": opportunity.status.value,
                "to": OpportunityStatus.BLOCKED.value, "reason": f"Transfer failed: {reason}",
                "evidence_ids": evidence_ids,
            }]
            blocked.append(opportunity.model_copy(update={
                "status": OpportunityStatus.BLOCKED, "history": history,
                "counterexamples": list(dict.fromkeys(opportunity.counterexamples + (counterexamples or []))),
            }))
        records = self.archive.put_many([failure, updated_mechanism, updated_bottleneck, *blocked])
        return records[0]
