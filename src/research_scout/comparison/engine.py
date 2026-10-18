"""Conservative, reusable comparisons; lexical resemblance never proves implication."""
from __future__ import annotations

import json

from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import (
    AssessmentStatus, DeltaKind, LiteratureDelta, MechanismVariant, Paper, Result, stable_id,
)


class ComparisonEngine:
    def __init__(self, archive: ArchiveProtocol):
        self.archive = archive

    def compare(self, paper_id: str) -> list[LiteratureDelta]:
        paper = self.archive.get(paper_id)
        if not isinstance(paper, Paper):
            raise ValueError("compare expects a paper identity")
        if not paper.version_ids:
            return []
        version_id = paper.version_ids[-1]
        results = [record for record in self.archive.list("result")
                   if record.paper_id == paper.id and record.version_id == version_id]
        comparisons = []
        for result in results:
            related = [record for record in self.archive.list("result") if record.id != result.id
                       and (set(record.problem_ids) & set(result.problem_ids)
                            or set(record.bottleneck_ids) & set(result.bottleneck_ids)
                            or set(record.mechanism_ids) & set(result.mechanism_ids)
                            or record.id in result.previous_result_ids)]
            comparisons.append(self.compare_result(result, related))
        return comparisons

    def compare_result(self, new: Result, previous: list[Result]) -> LiteratureDelta:
        new_date = self._source_date(new)
        # A directional literature delta must not call future work prior art.
        previous = [result for result in previous
                    if not (new_date and self._source_date(result)
                            and self._source_date(result) > new_date)]
        def fingerprint(result):
            return result.model_dump(mode="json", exclude={
                "revision", "created_at", "updated_at",
            })
        identity = json.dumps({"new": fingerprint(new),
                               "previous": [fingerprint(result) for result in sorted(previous, key=lambda r: r.id)]},
                              sort_keys=True, ensure_ascii=False)
        comparison_id = stable_id("comparison", identity)
        try:
            existing = self.archive.get(comparison_id)
        except KeyError:
            existing = None
        if existing and not existing.needs_review:
            return existing
        kinds: set[DeltaKind] = set()
        reasons, obligations = [], []
        if not new_date or any(not self._source_date(result) for result in previous):
            obligations.append("Publication chronology is unknown; verify dates before treating comparisons as prior art")
        for old in previous:
            old_scope = old.scope.model_dump()
            new_scope = new.scope.model_dump()
            same_context = all(old_scope[key] == new_scope[key] for key in (
                "domain", "model", "objective", "quantifiers", "metric",
            ))
            if (same_context and old.scope == new.scope and old.result_type == new.result_type
                    and old.statement == new.statement and old.rate == new.rate):
                kinds.add(DeltaKind.SAME_RESULT)
                reasons.append(f"{old.id}: identical structured statement, type, scope and rate")
            elif (same_context and old.scope.guarantee == new.scope.guarantee
                  and old.result_type == new.result_type and old.rate == new.rate
                  and set(new.scope.assumptions) < set(old.scope.assumptions)):
                kinds.add(DeltaKind.WEAKER_ASSUMPTIONS)
                reasons.append(f"{old.id}: same exact guarantee and rate with a strict subset of explicit assumptions")
                obligations.append("Check the source for hidden assumptions and domain restrictions before promotion")
            else:
                kinds.add(DeltaKind.INCOMPARABLE_RESULTS)
                reasons.append(f"{old.id}: formulations are not exactly equivalent")
                obligations.extend([
                    f"Establish assumption implication between {new.id} and {old.id}",
                    f"Prove guarantee, metric, quantifier and rate comparability for {old.id}",
                ])
            common = set(new.mechanism_ids) & set(old.mechanism_ids)
            if common:
                kinds.add(DeltaKind.SAME_MECHANISM)
                if set(new.problem_ids) - set(old.problem_ids):
                    kinds.add(DeltaKind.NEW_APPLICATION)
                    reasons.append("Existing mechanism reused on a distinct precise problem; not a new mechanism")
            for variant_id in new.variant_ids:
                variant = self.archive.get(variant_id)
                if isinstance(variant, MechanismVariant) and variant.mechanism_id in old.mechanism_ids:
                    kinds.add(DeltaKind.MECHANISM_VARIANT)
                    reasons.append(f"{variant_id}: {variant.technical_difference}")
        if not previous:
            kinds.add(DeltaKind.INSUFFICIENT_EVIDENCE)
            reasons.append("No archived related result; absence is not a novelty certificate")
            obligations.append("Expand literature and citation search before asserting novelty")
        for problem_id in new.problem_ids:
            problem = self.archive.get(problem_id)
            if problem.scope == new.scope:
                kinds.add(DeltaKind.POTENTIAL_RESOLUTION)
                obligations.append(f"Review source support and historical scope for precise problem {problem_id}")
        evidence = sorted(set(new.evidence_ids + [e for old in previous for e in old.evidence_ids]))
        comparison = LiteratureDelta(
            id=comparison_id, title=f"Literature comparison for {new.title}",
            paper_id=new.paper_id, version_id=new.version_id, new_result_id=new.id,
            compared_result_ids=[old.id for old in previous],
            delta_kinds=sorted(kinds, key=str), rationale="; ".join(reasons),
            proof_obligations=sorted(set(obligations)), evidence_ids=evidence,
            assessment_status=AssessmentStatus.PROPOSED, synthetic=new.synthetic,
            provenance="exact structured comparison; no semantic implication inference",
        )
        # A flagged historical comparison remains historical; don't silently clear review.
        if existing:
            return existing
        return self.archive.put(comparison)

    def _source_date(self, result: Result):
        version = self.archive.get(result.version_id)
        paper = self.archive.get(result.paper_id)
        return version.published or paper.published
