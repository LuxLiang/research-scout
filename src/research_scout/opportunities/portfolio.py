"""Persistent opportunities retain failed reasoning and separate assessment dimensions."""
from __future__ import annotations

from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import (
    AssessmentStatus, EvolutionEvent, Opportunity, OpportunityStatus, PreciseProblem,
    RankingDimension, Result, TransferHypothesis, now, stable_id, OPPORTUNITY_TRANSITIONS,
)
from research_scout.novelty import NoveltyAudit

DIMENSIONS = ("novelty", "significance", "technical_depth", "feasibility", "falsifiability", "research_fit")
TRANSITIONS = OPPORTUNITY_TRANSITIONS


def _status(value: OpportunityStatus | str) -> OpportunityStatus:
    return OpportunityStatus(str(value).replace("-", "_").upper())


class OpportunityPortfolio:
    def __init__(self, archive: ArchiveProtocol, novelty: NoveltyAudit | None = None):
        self.archive = archive
        self.novelty = novelty or NoveltyAudit(archive)

    def _get(self, identifier: str) -> Opportunity:
        record = self.archive.get(identifier)
        if not isinstance(record, Opportunity):
            raise TypeError("Expected Opportunity ID")
        return record

    def from_transfer(self, transfer_id: str) -> Opportunity:
        transfer = self.archive.get(transfer_id)
        if not isinstance(transfer, TransferHypothesis):
            raise TypeError("Opportunity creation requires a TransferHypothesis")
        if transfer.maturity == "EXPLORATORY_LEAD":
            raise ValueError("Exploratory leads need a concrete transfer hypothesis before opportunity creation")
        identifier = stable_id("opportunity", transfer.id)
        try:
            return self._get(identifier)
        except KeyError:
            pass
        problem = self.archive.get(transfer.target_problem_id)
        if not isinstance(problem, PreciseProblem):
            raise TypeError("Opportunity target must be a precise problem")
        audit = self.novelty.audit(transfer)
        result_ids = sorted(set(transfer.prior_art_ids + audit.comparable_result_ids + audit.related_result_ids))
        results = [self.archive.get(i) for i in result_ids]
        results = [r for r in results if isinstance(r, Result)]
        paper_ids = {r.paper_id for r in results}
        for evidence_id in transfer.evidence_ids:
            paper_ids.add(self.archive.get(evidence_id).paper_id)
        events = [e for e in self.archive.list("event") if isinstance(e, EvolutionEvent)
                  and (e.subject_id in {transfer.source_problem_id, transfer.target_problem_id}
                       or bool(set(e.related_ids) & {transfer.source_problem_id,
                                                    transfer.source_bottleneck_id,
                                                    transfer.source_mechanism_id}))]
        status = OpportunityStatus.BLOCKED if transfer.outcome == "FAILED" else OpportunityStatus.HYPOTHESIS
        reason = (f"Retained transfer failure: {transfer.failure_reason}" if transfer.outcome == "FAILED"
                  else "Created from an unproved structural transfer hypothesis")
        opportunity = Opportunity(
            id=identifier, title=f"Investigate {problem.title} via {transfer.source_mechanism_id}",
            target_problem_id=problem.id,
            bottleneck_ids=[transfer.target_bottleneck_id] if transfer.target_bottleneck_id else [],
            mechanism_ids=[transfer.source_mechanism_id], transfer_id=transfer.id,
            paper_ids=sorted(paper_ids), event_ids=[e.id for e in sorted(events, key=lambda e: (e.scientific_date, e.id))],
            contribution=transfer.proposed_result, closest_result_ids=result_ids,
            assumptions=transfer.required_assumptions, proof_obligations=transfer.missing_lemmas,
            counterexamples=transfer.likely_counterexamples, first_validation=transfer.first_falsification_test,
            significance=(f"Potential progress on {problem.statement}. "
                          "Significance and the difficulty of this problem require domain review."),
            novelty_assessment=audit.assessment + " " + audit.uncertainty,
            uncertainty=transfer.uncertainty, status=status,
            history=[{"timestamp": now().isoformat(), "from": None, "to": status.value,
                      "reason": reason}], evidence_ids=sorted(set(transfer.evidence_ids + audit.evidence_ids)),
            assessment_status=AssessmentStatus.PROPOSED, synthetic=transfer.synthetic,
            provenance="scout:transfer-opportunity",
        )
        return self.archive.put(opportunity)

    def list(self, status: OpportunityStatus | str | None = None) -> list[Opportunity]:
        selected = _status(status) if status else None
        return sorted([r for r in self.archive.list("opportunity")
                       if isinstance(r, Opportunity) and (selected is None or r.status == selected)],
                      key=lambda r: r.id)

    def transition(
        self, opportunity_id: str, status: OpportunityStatus | str, reason: str, *,
        evidence_ids: list[str] | None = None, reviewer: str | None = None,
    ) -> Opportunity:
        if not reason.strip():
            raise ValueError("Every lifecycle transition requires a retained reason")
        opportunity = self._get(opportunity_id)
        target = _status(status)
        if target not in TRANSITIONS[opportunity.status]:
            raise ValueError(f"Invalid opportunity transition: {opportunity.status} → {target}")
        if target == OpportunityStatus.PROPOSAL_READY:
            if not opportunity.proof_obligations or not opportunity.first_validation.strip():
                raise ValueError("Proposal readiness requires explicit proof obligations and a first validation plan")
            if opportunity.transfer_id:
                transfer = self.archive.get(opportunity.transfer_id)
                if transfer.outcome == "FAILED":
                    raise ValueError("A failed transfer requires a new, failure-addressing hypothesis")
        entry = {"timestamp": now().isoformat(), "from": opportunity.status.value,
                 "to": target.value, "reason": reason, "reviewer": reviewer,
                 "evidence_ids": evidence_ids or []}
        update = {"status": target, "history": opportunity.history + [entry],
                  "evidence_ids": sorted(set(opportunity.evidence_ids + (evidence_ids or [])))}
        if target == OpportunityStatus.REJECTED:
            update["rejection_reason"] = reason
        return self.archive.put(opportunity.model_copy(update=update))

    def assess_dimension(
        self, opportunity_id: str, dimension: str, score: float | None, rationale: str, *,
        evidence_ids: list[str] | None = None, reviewer: str | None = None,
    ) -> Opportunity:
        if dimension not in DIMENSIONS:
            raise ValueError(f"Unknown ranking dimension; choose one of {DIMENSIONS}")
        if not rationale.strip():
            raise ValueError("Assessment requires a substantive rationale")
        if score is not None and not evidence_ids:
            raise ValueError("A numeric ranking requires attributable evidence; otherwise leave it unassessed")
        opportunity = self._get(opportunity_id)
        assessment = RankingDimension(score=score, rationale=rationale, evidence_ids=evidence_ids or [])
        ranking = dict(opportunity.ranking)
        ranking[dimension] = assessment
        history = opportunity.history + [{"timestamp": now().isoformat(), "action": "ASSESS_DIMENSION",
                                           "dimension": dimension, "assessment": assessment.model_dump(),
                                           "reviewer": reviewer}]
        return self.archive.put(opportunity.model_copy(update={"ranking": ranking, "history": history}))

    def rank(
        self, dimension: str = "feasibility", *, status: OpportunityStatus | str | None = None,
    ) -> list[Opportunity]:
        """Order by one explicit dimension. Never invent an aggregate scientific score."""
        if dimension not in DIMENSIONS:
            raise ValueError(f"Unknown ranking dimension; choose one of {DIMENSIONS}")
        def order(opportunity):
            value = opportunity.ranking.get(dimension, RankingDimension()).score
            return (value is None, -(value if value is not None else 0), opportunity.id)
        return sorted(self.list(status), key=order)

    def refresh_novelty(self, opportunity_id: str) -> Opportunity:
        opportunity = self._get(opportunity_id)
        if not opportunity.transfer_id:
            raise ValueError("Novelty refresh requires a linked transfer hypothesis")
        audit = self.novelty.audit(opportunity.transfer_id)
        history = opportunity.history + [{"timestamp": now().isoformat(), "action": "NOVELTY_AUDIT",
                                           "assessment": audit.model_dump()}]
        return self.archive.put(opportunity.model_copy(update={
            "novelty_assessment": audit.assessment + " " + audit.uncertainty,
            "closest_result_ids": sorted(set(audit.comparable_result_ids + audit.related_result_ids)),
            "history": history,
        }))
