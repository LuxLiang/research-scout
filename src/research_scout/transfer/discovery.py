"""Technology-triggered exploration with explicit, unproved transfer obligations."""
from __future__ import annotations

import hashlib
import json
import re

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

    @staticmethod
    def _substantive(value: str) -> str:
        """Normalize explicit phrases; placeholders are not scientific match evidence."""
        phrase = " ".join(re.findall(r"[\w]+", value.casefold()))
        if phrase in {"unknown", "unspecified", "unavailable", "not specified", "not known",
                      "to be determined", "none", "general", "tbd", "n a"}:
            return ""
        return phrase if len(phrase.split()) >= 2 else ""

    def _match_basis(self, mechanism: Mechanism, source: PreciseProblem,
                     target: PreciseProblem, shared: list[str]) -> list[str]:
        basis = [f"Explicit shared structure: {value}" for value in shared]
        # Two specific equal scope dimensions are retrieval evidence only. A shared
        # domain/title, generic model, or a single common metric cannot admit a pair.
        equal = [name for name in ("objective", "metric", "model")
                 if self._substantive(getattr(source.scope, name))
                 and self._substantive(getattr(source.scope, name))
                 == self._substantive(getattr(target.scope, name))]
        if len(equal) >= 2:
            basis.extend(f"Explicit scope match ({name}): {getattr(target.scope, name)}"
                         for name in equal)
        role = self._substantive(mechanism.proof_role)
        target_phrases = [target.statement, target.desired_result, target.scope.objective,
                          *target.unresolved_scope]
        if role and len(role.split()) >= 3 and any(
            role in self._substantive(value) for value in target_phrases
        ):
            basis.append(f"Archived proof role occurs in target formulation: {mechanism.proof_role}")
        return basis

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
        relevant = set(mechanism.bottleneck_ids) | (set(result.bottleneck_ids) if result else set())
        source_b = max(source_bottlenecks, key=lambda b: (b.id in relevant, b.id), default=None)
        target_b = max(target_bottlenecks, key=lambda b: (
            len(set(b.structures) & (set(source_b.structures if source_b else [])
                                    | set(mechanism.structures))), b.id), default=None)
        shared = sorted((self._structure(source) | set(mechanism.structures))
                        & self._structure(target))
        if source_b and target_b and source_b.id == target_b.id and not shared:
            shared = [f"shared registered obstruction: {source_b.id}"]
        match_basis = self._match_basis(mechanism, source, target, shared)
        if not match_basis:
            raise IneligibleTransferError(
                "No explicit shared structure, substantive scope match or proof role supports this candidate")
        # Goal/proof-role resemblance alone remains a lead even when unrelated
        # bottleneck records happen to exist on both sides.
        exploratory = not source_b or not target_b or not shared
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
        if source_b and target_b and source_b.obstruction != target_b.obstruction:
            differences.append(f"Obstruction changes from {source_b.obstruction!r} to {target_b.obstruction!r}")
        if not differences:
            differences.append("Exact formulations coincide; mechanism-level novelty still needs source comparison.")
        assumptions = list(dict.fromkeys(target.scope.assumptions + mechanism.necessary_assumptions))
        missing = [
            f"Construct {mechanism.construction or mechanism.principle} on target model {target.scope.model}.",
            (f"Prove that the adapted construction controls obstruction: {target_b.obstruction}."
             if target_b else "Identify a target proof step or construction where the retrieved capability could apply."),
            f"Derive {target.scope.guarantee} in {target.scope.metric} for quantifiers: "
            + "; ".join(target.scope.quantifiers or ["target quantifiers require specification"]),
        ]
        missing.extend(f"Establish target validity of necessary assumption: {a}."
                       for a in mechanism.necessary_assumptions if a not in target.scope.assumptions)
        missing.extend(f"Close unresolved target setting: {x}."
                       for x in target.unresolved_scope + (target_b.remaining_settings if target_b else []))
        if exploratory:
            # The application route is unknown. Do not present generic templates
            # as missing mathematical lemmas or an executable validation plan.
            missing = []
        counterexamples = list(dict.fromkeys((source_b.counterexamples if source_b else [])
                                            + (target_b.counterexamples if target_b else [])
                                            + mechanism.limitations))
        counterexamples.append(
            f"Search for an admissible {target.scope.model} instance where "
            f"{target_b.obstruction if target_b else target.desired_result} "
            "persists despite the proposed construction."
        )
        if previous:
            missing.append(f"Resolve retained failure {previous.id}: {previous.failure_reason}")
            missing.extend(f"Revisit condition requiring review: {condition}."
                           for condition in previous.revisit_when)
            counterexamples.extend(previous.likely_counterexamples)
        evidence = sorted(set(source.evidence_ids + target.evidence_ids + mechanism.evidence_ids
                              + (source_b.evidence_ids if source_b else [])
                              + (target_b.evidence_ids if target_b else [])
                              + (result.evidence_ids if result else [])
                              + (breakthrough.evidence_ids if breakthrough else [])
                              + (previous.evidence_ids if previous else [])))
        fingerprint = _fingerprint(source, target, mechanism, source_b, target_b, result,
                                   breakthrough, previous)
        hypothesis = TransferHypothesis(
            id=stable_id("transfer", f"{mode}:{mechanism.id}:{target.id}:{fingerprint}"),
            title=f"Transfer candidate: {mechanism.title} → {target.title}", mode=mode,
            source_problem_id=source.id, source_bottleneck_id=source_b.id if source_b else None,
            source_mechanism_id=mechanism.id, breakthrough_id=breakthrough.id if breakthrough else None,
            target_problem_id=target.id, target_bottleneck_id=target_b.id if target_b else None,
            maturity="EXPLORATORY_LEAD" if exploratory else "TRANSFER_HYPOTHESIS",
            match_basis=match_basis, revisit_when=previous.revisit_when if previous else [],
            next_action=("Inspect the target argument and locate a possible use of the archived capability; "
                         "formulate a bridge statement before proposing a validation plan."
                         + (f" Review retained failure first: {previous.failure_reason}." if previous else "")
                         if exploratory else "Formulate and check the missing target bridge lemmas."),
            shared_structures=shared, structural_differences=differences,
            required_assumptions=assumptions, missing_lemmas=list(dict.fromkeys(missing)),
            likely_counterexamples=list(dict.fromkeys(counterexamples)),
            proposed_result=(f"Conjectured target guarantee: {target.desired_result}. "
                             f"Investigate {mechanism.title} for "
                             f"{target_b.description if target_b else target.desired_result}; "
                             "all listed assumptions and lemmas remain obligations."),
            first_falsification_test="" if exploratory else (
                f"In the smallest admissible {target.scope.model} example, compute the proposed "
                f"construction and test its relevance to "
                f"{target_b.obstruction if target_b else target.desired_result} in "
                f"{target.scope.metric}. Vary each target assumption separately; a violating "
                "admissible instance falsifies the claim, while passing does not prove it."
                + (f" First reproduce and address the retained failure: {previous.failure_reason}."
                   if previous else "")
            ),
            uncertainty=(("Exploratory lead: the bottleneck and a concrete application path are not established. "
                          if exploratory else "")
                         + "Structural retrieval is a hypothesis, not a valid transfer or a proof. "
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
                # A pair lacking source history or a substantive archived match is excluded.
                continue
        return sorted(candidates, key=lambda t: t.id)

    def record_failure(
        self, transfer_id: str, reason: str, *, counterexamples: list[str] | None = None,
        evidence_ids: list[str] | None = None, revisit_when: list[str] | None = None,
    ) -> TransferHypothesis:
        if not reason.strip():
            raise ValueError("Failure reason must be nonempty")
        transfer = self._get(transfer_id, TransferHypothesis)
        if transfer.outcome == "FAILED":
            if (transfer.failure_reason == reason
                    and set(counterexamples or []).issubset(transfer.likely_counterexamples)
                    and set(revisit_when or []).issubset(transfer.revisit_when)
                    and set(evidence_ids or []).issubset(transfer.evidence_ids)):
                return transfer
            raise ValueError("Retain the original failure; record a new transfer for a new attempt")
        evidence_ids = evidence_ids or []
        failure = transfer.model_copy(update={
            "outcome": "FAILED", "failure_reason": reason,
            "revisit_when": list(dict.fromkeys(transfer.revisit_when + (revisit_when or []))),
            "likely_counterexamples": list(dict.fromkeys(transfer.likely_counterexamples + (counterexamples or []))),
            "evidence_ids": sorted(set(transfer.evidence_ids + evidence_ids)),
            "assessment_status": AssessmentStatus.CHALLENGED,
            "uncertainty": (transfer.uncertainty + " Reported failure: " + reason
                            + ". Counterexample admissibility under the target assumptions "
                            "requires review; an example outside that scope does not refute "
                            "the scoped target guarantee."),
        })
        mechanism = self._get(transfer.source_mechanism_id, Mechanism)
        bottleneck = (self._get(transfer.target_bottleneck_id, Bottleneck)
                      if transfer.target_bottleneck_id else None)
        attempt = Attempt(description=f"Transfer {transfer.id} to {transfer.target_problem_id}",
                          outcome="FAILED", mechanism_id=mechanism.id, reason=reason,
                          evidence_ids=evidence_ids)
        updated_mechanism = mechanism.model_copy(update={"attempts": mechanism.attempts + [attempt]})
        updated_bottlenecks = ([bottleneck.model_copy(update={"attempts": bottleneck.attempts + [attempt]})]
                               if bottleneck else [])
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
        records = self.archive.put_many([failure, updated_mechanism, *updated_bottlenecks, *blocked])
        return records[0]
