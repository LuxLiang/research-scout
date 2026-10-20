"""Incremental paper-to-discovery controller; scientific output remains qualified."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from research_scout.breakthrough import BreakthroughDiscovery
from research_scout.domain.models import Mechanism, Result
from research_scout.extraction import PaperPipeline, ProcessingOutcome
from research_scout.opportunities import OpportunityPortfolio
from research_scout.transfer import TransferDiscovery


@dataclass
class DiscoveryOutcome:
    processing: ProcessingOutcome
    breakthrough_ids: list[str] = field(default_factory=list)
    transfer_ids: list[str] = field(default_factory=list)
    opportunity_ids: list[str] = field(default_factory=list)
    analysis_errors: list[str] = field(default_factory=list)


class ScoutController:
    def __init__(self, archive, cache_dir: str | Path, provider=None, http_client=None):
        self.archive = archive
        self.pipeline = PaperPipeline(archive,cache_dir,provider,http_client)

    def process(self, source, extract=True, *, discover=True) -> DiscoveryOutcome:
        outcome=DiscoveryOutcome(self.pipeline.process(source,extract=extract))
        if not extract or not discover:
            return outcome
        for result in outcome.processing.records:
            if not isinstance(result,Result):
                continue
            for problem_id in result.problem_ids:
                try:
                    breakthrough=BreakthroughDiscovery(self.archive).analyze(result.id,problem_id)
                    outcome.breakthrough_ids.append(breakthrough.id)
                    for target in breakthrough.analogous_problem_ids:
                        for mechanism_id in breakthrough.new_mechanism_ids:
                            transfer=TransferDiscovery(self.archive).propose(mechanism_id,target,
                                mode='BREAKTHROUGH_FIRST',breakthrough_id=breakthrough.id)
                            outcome.transfer_ids.append(transfer.id)
                            if transfer.maturity != 'EXPLORATORY_LEAD':
                                opportunity=OpportunityPortfolio(self.archive).from_transfer(transfer.id)
                                outcome.opportunity_ids.append(opportunity.id)
                except (ValueError,TypeError,KeyError) as exc:
                    # Extraction has already been validated and committed. Report downstream
                    # incompleteness explicitly; never replace it with invented discoveries.
                    outcome.analysis_errors.append(f'{result.id}/{problem_id}: {exc}')
        # A useful technique need not first qualify as a historical breakthrough.
        mechanisms = {r.id for r in outcome.processing.records if isinstance(r, Mechanism)}
        mechanisms.update(m for r in outcome.processing.records if isinstance(r, Result)
                          for m in r.mechanism_ids)
        retained_pairs = {(self.archive.get(t).source_mechanism_id,
                           self.archive.get(t).target_problem_id) for t in outcome.transfer_ids}
        for mechanism_id in sorted(mechanisms):
            try:
                transfers = TransferDiscovery(self.archive).discover('TECHNIQUE_FIRST', mechanism_id)
                for transfer in transfers:
                    pair = (transfer.source_mechanism_id, transfer.target_problem_id)
                    if pair in retained_pairs:
                        continue
                    retained_pairs.add(pair)
                    outcome.transfer_ids.append(transfer.id)
                    if transfer.maturity != 'EXPLORATORY_LEAD':
                        opportunity = OpportunityPortfolio(self.archive).from_transfer(transfer.id)
                        outcome.opportunity_ids.append(opportunity.id)
            except (ValueError, TypeError, KeyError) as exc:
                outcome.analysis_errors.append(f'{mechanism_id}/technique-first: {exc}')
        for name in ('breakthrough_ids','transfer_ids','opportunity_ids'):
            setattr(outcome,name,list(dict.fromkeys(getattr(outcome,name))))
        return outcome
