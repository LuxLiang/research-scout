"""Replay retained events into a precise, qualified problem state."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from research_scout.domain.interfaces import ArchiveProtocol
from research_scout.domain.models import (
    Coverage, Evidence, EvolutionEvent, EventType, PaperVersion, PreciseProblem, ProblemStatus,
    ResolutionAssessment, ResolutionKind, Result, StrictModel,
)
from .resolution import QUALIFIED, assess_resolution, superseding_versions


class TimelineSnapshot(StrictModel):
    problem_id: str
    status: ProblemStatus = ProblemStatus.OPEN
    events: list[EvolutionEvent] = Field(default_factory=list)
    assessments: list[ResolutionAssessment] = Field(default_factory=list)
    unresolved_scope: list[str] = Field(default_factory=list)
    requires_review: bool = False
    first_posed: date | None = None
    qualification: str = "Source support is attribution, not mathematical proof verification."


class _HistoricalReader:
    """Read retained revisions when the archive offers its optional history API.

    Source records can be imported retrospectively, so revision 1 is the source
    snapshot pinned by a historical event even when imported after that event.
    Subsequent corrections are applied only at their recording timestamp.
    """
    def __init__(self, archive, cutoff=None, scientific_date=None):
        self.archive, self.cutoff = archive, cutoff
        self.scientific_date = scientific_date

    def get(self, record_id):
        record = self.archive.get(record_id)
        history = getattr(self.archive, "history", None)
        if history is None or self.cutoff is None:
            return record
        revisions = history(record.id)
        before = [r for r in revisions if r.updated_at <= self.cutoff]
        return (before[-1] if before else revisions[0]) if revisions else record

    def list(self, kind=None):
        records = [self.get(r.id) for r in self.archive.list(kind)]
        visible = []
        for record in records:
            if isinstance(record, PaperVersion):
                if self.cutoff is not None and record.created_at > self.cutoff:
                    paper = self.get(record.paper_id)
                    if not paper.version_ids or paper.version_ids[0] != record.id:
                        continue
                if (self.scientific_date is not None and record.published is not None
                        and record.published > self.scientific_date):
                    continue
            visible.append(record)
        return visible


class EventStore:
    def __init__(self, archive: ArchiveProtocol):
        self.archive = archive

    def append(self, event: EvolutionEvent) -> EvolutionEvent:
        """Idempotent append; an ID can never be reused for changed history."""
        try:
            previous = self.archive.get(event.id)
        except KeyError:
            previous = None
        if previous is not None:
            if previous.model_dump() != event.model_dump():
                raise ValueError(f"Evolution event {event.id} is immutable")
            return previous
        for previous_id in event.previous_event_ids:
            previous_event = self.archive.get(previous_id)
            if not isinstance(previous_event, EvolutionEvent):
                raise ValueError("Event history references must point to events")
            if previous_event.recorded_at > event.recorded_at:
                raise ValueError("An event cannot reference history recorded in the future")
        self.archive.put(event)
        return event

    def list(
        self, subject_id: str, *, as_of: date | None = None,
        recorded_before: datetime | None = None,
    ) -> list[EvolutionEvent]:
        events = [e for e in self.archive.list("event")
                  if isinstance(e, EvolutionEvent) and e.subject_id == subject_id
                  and (as_of is None or e.scientific_date <= as_of)
                  and (recorded_before is None or e.recorded_at <= recorded_before)]
        return sorted(events, key=lambda e: (e.scientific_date, e.recorded_at, e.id))


def _full_scope(event: EvolutionEvent, problem: PreciseProblem) -> bool:
    a, b = event.scope, problem.scope
    return (all(getattr(a, x) == getattr(b, x) for x in (
        "domain", "model", "objective", "metric", "guarantee", "quantifiers",
    )) and set(a.assumptions) <= set(b.assumptions) and not a.unresolved)


def _challenge_scope(event: EvolutionEvent, problem: PreciseProblem) -> bool:
    """An admissible subclass counterexample can refute a universal claim."""
    a, b = event.scope, problem.scope
    same_formulation = all(getattr(a, x) == getattr(b, x) for x in (
        "domain", "model", "objective", "metric", "guarantee", "quantifiers",
    ))
    if event.event_type == EventType.COUNTEREXAMPLE_DISCOVERED:
        return same_formulation and set(b.assumptions) <= set(a.assumptions)
    return _full_scope(event, problem)


def _qualified_event(archive, event: EvolutionEvent) -> bool:
    if event.assessment_status not in QUALIFIED:
        return False
    evidence = [archive.get(eid) for eid in event.evidence_ids]
    return bool(evidence) and all(
        isinstance(e, Evidence) and e.assessment_status in QUALIFIED
        and e.coverage in {Coverage.PARTIAL_TEXT, Coverage.FULL_TEXT}
        and e.version_id == event.version_id and e.paper_id == event.paper_id
        for e in evidence
    )


class ProblemEvolutionTimeline:
    def __init__(self, archive: ArchiveProtocol, problem_id: str):
        self.archive, self.problem_id = archive, problem_id

    def build(
        self, *, as_of: date | None = None, recorded_before: datetime | None = None,
    ) -> TimelineSnapshot:
        archive = (_HistoricalReader(self.archive, recorded_before, as_of)
                   if recorded_before is not None or as_of is not None else self.archive)
        problem = archive.get(self.problem_id)
        if not isinstance(problem, PreciseProblem):
            raise TypeError("Timelines require a PreciseProblem, never a topic or family")
        events = EventStore(archive).list(
            problem.id, as_of=as_of, recorded_before=recorded_before,
        )
        snapshot = TimelineSnapshot(
            problem_id=problem.id, events=events,
            unresolved_scope=problem.unresolved_scope or problem.scope.unresolved,
        )
        superseded = {
            eid for e in events if e.event_type == EventType.SUPERSEDED
            for eid in e.previous_event_ids
        }
        active_resolution_events: set[str] = set()
        for event in events:
            if event.event_type == EventType.PROBLEM_POSED and snapshot.first_posed is None:
                snapshot.first_posed = event.scientific_date
            if event.id in superseded:
                continue
            if event.event_type in {EventType.CHALLENGED, EventType.COUNTEREXAMPLE_DISCOVERED,
                                    EventType.REOPENED}:
                target_active = bool(set(event.previous_event_ids) & active_resolution_events)
                if (_challenge_scope(event, problem) and _qualified_event(archive, event)
                        and (target_active or not event.previous_event_ids)):
                    snapshot.status = (ProblemStatus.REOPENED
                                       if event.event_type == EventType.REOPENED
                                       else ProblemStatus.CHALLENGED)
                    active_resolution_events.clear()
                    snapshot.unresolved_scope = (problem.unresolved_scope or problem.scope.unresolved
                                                 or [problem.statement])
                continue
            if event.event_type == EventType.PARTIAL_PROGRESS:
                if snapshot.status in {ProblemStatus.OPEN, ProblemStatus.RESOLUTION_CLAIMED}:
                    snapshot.status = ProblemStatus.PARTIAL
                continue
            if event.event_type not in {
                EventType.CLAIMED_RESOLUTION, EventType.SUPPORTED_RESOLUTION,
                EventType.CONDITIONAL_RESOLUTION,
            }:
                continue
            related = [archive.get(rid) for rid in event.related_ids]
            assessments = [r for r in related if isinstance(r, ResolutionAssessment)
                           and r.problem_id == problem.id]
            result_ids = [r.id for r in related if isinstance(r, Result)]
            result_ids.extend(a.result_id for a in assessments)
            assessments.extend(
                a for a in archive.list("resolution_assessment")
                if isinstance(a, ResolutionAssessment) and a.problem_id == problem.id
                and a.result_id in result_ids and a.id not in {x.id for x in assessments}
            )
            def assessment_stale(assessment):
                if not assessment.needs_review:
                    return False
                source_result = archive.get(assessment.result_id)
                if (superseding_versions(self.archive, source_result)
                        and not superseding_versions(archive, source_result)):
                    # A correction outside this historical view cannot invalidate
                    # the earlier scientific/recording state through a cached flag.
                    return False
                return recorded_before is None or assessment.updated_at <= recorded_before
            stale = any(assessment_stale(a) for a in assessments)
            snapshot.requires_review |= stale
            evaluated = []
            for rid in dict.fromkeys(result_ids):
                result = archive.get(rid)
                if result.version_id != event.version_id or result.paper_id != event.paper_id:
                    continue
                resolution = assess_resolution(archive, problem.id, rid, persist=False)
                evaluated.append(resolution)
                snapshot.assessments.append(resolution)
                stale |= resolution.needs_review
                snapshot.requires_review |= resolution.needs_review
            if not evaluated:
                snapshot.status = (snapshot.status if active_resolution_events
                                   else ProblemStatus.RESOLUTION_CLAIMED)
                continue
            full = any(a.resolution == ResolutionKind.FULL_RESOLUTION_SUPPORTED for a in evaluated)
            conditional = any(a.resolution == ResolutionKind.CONDITIONAL_RESOLUTION for a in evaluated)
            partial = any(a.resolution == ResolutionKind.PARTIAL_RESOLUTION for a in evaluated)
            qualified_event = _qualified_event(archive, event)
            if (full and not stale and qualified_event and _full_scope(event, problem)
                    and event.event_type == EventType.SUPPORTED_RESOLUTION):
                snapshot.status = ProblemStatus.RESOLVED_SUPPORTED
                active_resolution_events.add(event.id)
                snapshot.unresolved_scope = []
            elif not active_resolution_events:
                if conditional and qualified_event and not stale:
                    snapshot.status = ProblemStatus.CONDITIONALLY_RESOLVED
                elif partial and qualified_event and not stale:
                    snapshot.status = ProblemStatus.PARTIAL
                else:
                    snapshot.status = ProblemStatus.RESOLUTION_CLAIMED
                if not snapshot.unresolved_scope:
                    snapshot.unresolved_scope = [problem.statement]
        return snapshot

    def replay(self, **kwargs) -> TimelineSnapshot:
        return self.build(**kwargs)

    def bottleneck_history(self, bottleneck_id: str) -> list[EvolutionEvent]:
        """Retrieve attributable problem events connected to an obstruction."""
        return [e for e in EventStore(self.archive).list(self.problem_id)
                if bottleneck_id in e.related_ids]
