"""Conservative prior-art retrieval; absence from an archive never proves novelty."""
from __future__ import annotations

from typing import Protocol

from pydantic import Field

from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import (
    AssessmentStatus, PreciseProblem, Result, StrictModel, TransferHypothesis,
)


class ExternalPriorArt(StrictModel):
    title: str
    url: str
    relevance: str
    source: str


class PriorArtAdapter(Protocol):
    def search(self, hypothesis: TransferHypothesis) -> list[ExternalPriorArt]: ...


class NoveltyReport(StrictModel):
    transfer_id: str
    comparable_result_ids: list[str] = Field(default_factory=list)
    related_result_ids: list[str] = Field(default_factory=list)
    external_matches: list[ExternalPriorArt] = Field(default_factory=list)
    external_searched: bool = False
    external_error: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    assessment: str
    uncertainty: str = (
        "Archive coverage and external retrieval may be incomplete. Absence of matches is not "
        "evidence of novelty; semantic resemblance does not establish result equivalence."
    )


class NoveltyAudit:
    def __init__(self, archive: ArchiveProtocol, adapter: PriorArtAdapter | None = None):
        self.archive, self.adapter = archive, adapter

    def audit(self, transfer: str | TransferHypothesis) -> NoveltyReport:
        hypothesis = self.archive.get(transfer) if isinstance(transfer, str) else transfer
        if not isinstance(hypothesis, TransferHypothesis):
            raise TypeError("Novelty audit requires a TransferHypothesis")
        target = self.archive.get(hypothesis.target_problem_id)
        if not isinstance(target, PreciseProblem):
            raise TypeError("Transfer target must be a precise problem")
        comparable, related, evidence = [], [], []
        for result in self.archive.list("result"):
            if not isinstance(result, Result):
                continue
            # Exact structured equality only: no text-based assumption implication.
            exact = result.scope == target.scope
            relevant = (target.id in result.problem_ids
                        or hypothesis.source_mechanism_id in result.mechanism_ids
                        or bool({hypothesis.source_bottleneck_id, hypothesis.target_bottleneck_id}
                                & set(result.bottleneck_ids)))
            if exact:
                comparable.append(result.id)
            elif relevant:
                related.append(result.id)
            if exact or relevant:
                evidence.extend(result.evidence_ids)
        matches, error = [], None
        if self.adapter:
            try:
                matches = [ExternalPriorArt.model_validate(x) for x in self.adapter.search(hypothesis)]
            except Exception as exc:
                # A failed expansion is visibly incomplete, never an empty successful search.
                error = f"{type(exc).__name__}: {exc}"
        if comparable:
            assessment = (
                "Exact target-scope results already exist in the archive: "
                + ", ".join(sorted(comparable))
                + ". Check statements, verification status and technical construction before "
                "claiming a new result or mechanism."
            )
        else:
            assessment = (
                "No exact target-scope result was retrieved from this archive. Novelty remains "
                "UNDETERMINED; related results require detailed statement and proof comparison."
            )
        stale = [r.id for r in self.archive.list("result") if r.id in comparable + related
                 and r.assessment_status in {AssessmentStatus.NEEDS_REVIEW, AssessmentStatus.CHALLENGED}]
        if stale:
            assessment += " Prior-art records needing review: " + ", ".join(sorted(stale)) + "."
        if error:
            assessment += " External prior-art retrieval failed; the audit is incomplete."
        elif matches:
            assessment += " External matches are retrieval leads requiring source verification."
        return NoveltyReport(
            transfer_id=hypothesis.id, comparable_result_ids=sorted(comparable),
            related_result_ids=sorted(related), external_matches=matches,
            external_searched=self.adapter is not None, external_error=error,
            evidence_ids=sorted(set(evidence)), assessment=assessment,
        )
