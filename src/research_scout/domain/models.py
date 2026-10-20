"""Versioned scientific records. Attribution is distinct from mathematical truth."""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
import hashlib
import re
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"


def now() -> datetime:
    return datetime.now(timezone.utc)


def stable_id(kind: str, identity: str) -> str:
    return f"{kind.lower()}-{hashlib.sha256(identity.encode()).hexdigest()[:20]}"


class AssessmentStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    PROPOSED = "PROPOSED"
    SUPPORTED_BY_SOURCE = "SUPPORTED_BY_SOURCE"
    INDEPENDENTLY_REVIEWED = "INDEPENDENTLY_REVIEWED"
    UNCERTAIN = "UNCERTAIN"
    CHALLENGED = "CHALLENGED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ClaimOrigin(StrEnum):
    AUTHOR = "AUTHOR"
    SYSTEM_INFERENCE = "SYSTEM_INFERENCE"
    HUMAN = "HUMAN"


class Coverage(StrEnum):
    METADATA_ONLY = "METADATA_ONLY"
    ABSTRACT_ONLY = "ABSTRACT_ONLY"
    PARTIAL_TEXT = "PARTIAL_TEXT"
    FULL_TEXT = "FULL_TEXT"


class ProblemStatus(StrEnum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    CONDITIONALLY_RESOLVED = "CONDITIONALLY_RESOLVED"
    RESOLUTION_CLAIMED = "RESOLUTION_CLAIMED"
    RESOLVED_SUPPORTED = "RESOLVED_SUPPORTED"
    CHALLENGED = "CHALLENGED"
    REOPENED = "REOPENED"


class BottleneckStatus(StrEnum):
    ESTABLISHED_BOTTLENECK = "ESTABLISHED_BOTTLENECK"
    HYPOTHESIZED_BOTTLENECK = "HYPOTHESIZED_BOTTLENECK"
    REFUTED_BOTTLENECK = "REFUTED_BOTTLENECK"


class ResolutionKind(StrEnum):
    FULL_RESOLUTION_SUPPORTED = "FULL_RESOLUTION_SUPPORTED"
    PARTIAL_RESOLUTION = "PARTIAL_RESOLUTION"
    CONDITIONAL_RESOLUTION = "CONDITIONAL_RESOLUTION"
    CLAIMED_BUT_UNVERIFIED = "CLAIMED_BUT_UNVERIFIED"
    NOT_A_RESOLUTION = "NOT_A_RESOLUTION"
    INCOMPARABLE = "INCOMPARABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EventType(StrEnum):
    PROBLEM_POSED = "PROBLEM_POSED"
    BOTTLENECK_IDENTIFIED = "BOTTLENECK_IDENTIFIED"
    MECHANISM_INTRODUCED = "MECHANISM_INTRODUCED"
    PARTIAL_PROGRESS = "PARTIAL_PROGRESS"
    NEW_RESULT = "NEW_RESULT"
    ASSUMPTION_RELAXATION = "ASSUMPTION_RELAXATION"
    GUARANTEE_IMPROVEMENT = "GUARANTEE_IMPROVEMENT"
    CLAIMED_RESOLUTION = "CLAIMED_RESOLUTION"
    SUPPORTED_RESOLUTION = "SUPPORTED_RESOLUTION"
    CONDITIONAL_RESOLUTION = "CONDITIONAL_RESOLUTION"
    GENERALIZATION = "GENERALIZATION"
    CHALLENGED = "CHALLENGED"
    COUNTEREXAMPLE_DISCOVERED = "COUNTEREXAMPLE_DISCOVERED"
    REOPENED = "REOPENED"
    SUPERSEDED = "SUPERSEDED"


class RelationType(StrEnum):
    PAPER_STUDIES_PROBLEM = "PAPER_STUDIES_PROBLEM"
    PAPER_INTRODUCES_MECHANISM = "PAPER_INTRODUCES_MECHANISM"
    PAPER_ESTABLISHES_RESULT = "PAPER_ESTABLISHES_RESULT"
    PROBLEM_HAS_SUBPROBLEM = "PROBLEM_HAS_SUBPROBLEM"
    PROBLEM_LIMITED_BY_BOTTLENECK = "PROBLEM_LIMITED_BY_BOTTLENECK"
    MECHANISM_VARIANT_OF = "MECHANISM_VARIANT_OF"
    MECHANISM_ADDRESSES_BOTTLENECK = "MECHANISM_ADDRESSES_BOTTLENECK"
    RESULT_ADDRESSES_PROBLEM = "RESULT_ADDRESSES_PROBLEM"
    RESULT_OVERCOMES_BOTTLENECK = "RESULT_OVERCOMES_BOTTLENECK"
    RESULT_IMPROVES_RESULT = "RESULT_IMPROVES_RESULT"
    RESULT_GENERALIZES_RESULT = "RESULT_GENERALIZES_RESULT"
    RESULT_WEAKENS_ASSUMPTIONS = "RESULT_WEAKENS_ASSUMPTIONS"
    RESULT_CHALLENGES_RESULT = "RESULT_CHALLENGES_RESULT"
    MECHANISM_APPLIED_TO_PROBLEM = "MECHANISM_APPLIED_TO_PROBLEM"
    MECHANISM_TRANSFER_ATTEMPT = "MECHANISM_TRANSFER_ATTEMPT"


class DeltaKind(StrEnum):
    SAME_RESULT = "SAME_RESULT"
    SAME_MECHANISM = "SAME_MECHANISM"
    MECHANISM_VARIANT = "MECHANISM_VARIANT"
    NEW_APPLICATION = "NEW_APPLICATION"
    NEW_PROBLEM_FORMULATION = "NEW_PROBLEM_FORMULATION"
    PARTIAL_PROGRESS = "PARTIAL_PROGRESS"
    STRONGER_GUARANTEE = "STRONGER_GUARANTEE"
    WEAKER_ASSUMPTIONS = "WEAKER_ASSUMPTIONS"
    INCOMPARABLE_RESULTS = "INCOMPARABLE_RESULTS"
    POTENTIAL_RESOLUTION = "POTENTIAL_RESOLUTION"
    POTENTIAL_CONTRADICTION = "POTENTIAL_CONTRADICTION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class TransferMode(StrEnum):
    TECHNIQUE_FIRST = "TECHNIQUE_FIRST"
    PROBLEM_FIRST = "PROBLEM_FIRST"
    FAILURE_FIRST = "FAILURE_FIRST"
    BREAKTHROUGH_FIRST = "BREAKTHROUGH_FIRST"


class OpportunityStatus(StrEnum):
    HYPOTHESIS = "HYPOTHESIS"
    SCREENED = "SCREENED"
    INVESTIGATING = "INVESTIGATING"
    PROPOSAL_READY = "PROPOSAL_READY"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Scope(StrictModel):
    """Exact structured formulation; strings are not a logical implication oracle."""
    domain: str
    model: str
    objective: str
    assumptions: list[str] = Field(default_factory=list)
    quantifiers: list[str] = Field(default_factory=list)
    metric: str
    guarantee: str
    unresolved: list[str] = Field(default_factory=list)

    @field_validator("domain", "model", "objective", "metric", "guarantee")
    @classmethod
    def precise_dimensions(cls, value):
        if not value.strip():
            raise ValueError("scope formulation dimensions cannot be blank")
        return value.strip()

    @field_validator("assumptions", "quantifiers", "unresolved")
    @classmethod
    def nonblank_terms(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError("scope terms cannot be blank")
        return values


class Review(StrictModel):
    reviewer: str
    timestamp: AwareDatetime = Field(default_factory=now)
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)


class Record(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_.:-]{0,159}$")
    kind: str
    revision: int = Field(default=1, ge=1)
    title: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    created_at: AwareDatetime = Field(default_factory=now)
    updated_at: AwareDatetime = Field(default_factory=now)
    synthetic: bool = False
    provenance: str = "user"
    evidence_ids: list[str] = Field(default_factory=list)
    assessment_status: AssessmentStatus = AssessmentStatus.PROPOSED
    review: Review | None = None

    @model_validator(mode="after")
    def reviewed_has_identity(self):
        if self.assessment_status == AssessmentStatus.INDEPENDENTLY_REVIEWED:
            if not self.review or not self.evidence_ids:
                raise ValueError("independent review requires attributable review and evidence")
        return self


class Paper(Record):
    kind: Literal["paper"] = "paper"
    doi: str | None = None
    arxiv_id: str | None = None
    authors: list[str] = Field(default_factory=list)
    venue: str | None = None
    published: date | None = None
    version_ids: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    proof_techniques: list[str] = Field(default_factory=list)
    contributions: list[str] = Field(default_factory=list)
    problem_ids: list[str] = Field(default_factory=list)
    bottleneck_ids: list[str] = Field(default_factory=list)
    mechanism_ids: list[str] = Field(default_factory=list)
    result_ids: list[str] = Field(default_factory=list)
    extraction_status: str = "NOT_EXTRACTED"


class PaperVersion(Record):
    kind: Literal["paper_version"] = "paper_version"
    paper_id: str
    version: str
    source_urls: list[str] = Field(default_factory=list)
    content_hash: str | None = None
    source_path: str | None = None
    text_path: str | None = None
    abstract: str | None = None
    coverage: Coverage = Coverage.METADATA_ONLY
    published: date | None = None
    supersedes_version_id: str | None = None


class Topic(Record):
    kind: Literal["topic"] = "topic"
    description: str = ""


class ProblemFamily(Record):
    kind: Literal["problem_family"] = "problem_family"
    topic_id: str
    description: str = ""


class PreciseProblem(Record):
    kind: Literal["problem"] = "problem"
    family_id: str | None = None
    statement: str
    scope: Scope
    desired_result: str
    bottleneck_ids: list[str] = Field(default_factory=list)
    known_result_ids: list[str] = Field(default_factory=list)
    unresolved_scope: list[str] = Field(default_factory=list)
    structures: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    difficulty_hypotheses: list[str] = Field(default_factory=list)
    # Current status is computed from immutable events, never a mutable "solved" flag.


class Attempt(StrictModel):
    description: str
    outcome: Literal["FAILED", "PARTIAL", "SUCCESS", "UNKNOWN"]
    mechanism_id: str | None = None
    result_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class Bottleneck(Record):
    kind: Literal["bottleneck"] = "bottleneck"
    description: str
    obstruction: str
    insufficiency: str
    status: BottleneckStatus = BottleneckStatus.HYPOTHESIZED_BOTTLENECK
    problem_ids: list[str] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)
    counterexamples: list[str] = Field(default_factory=list)
    addressing_mechanism_ids: list[str] = Field(default_factory=list)
    overcoming_mechanism_ids: list[str] = Field(default_factory=list)
    remaining_settings: list[str] = Field(default_factory=list)
    structures: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def established_requires_evidence(self):
        if self.status == BottleneckStatus.ESTABLISHED_BOTTLENECK and not self.evidence_ids:
            raise ValueError("established bottleneck requires evidence")
        return self


class MechanismFamily(Record):
    kind: Literal["mechanism_family"] = "mechanism_family"
    principle: str


class Mechanism(Record):
    kind: Literal["mechanism"] = "mechanism"
    family_id: str | None = None
    principle: str
    construction: str = ""
    structures: list[str] = Field(default_factory=list)
    proof_role: str = ""
    applicable_models: list[str] = Field(default_factory=list)
    necessary_assumptions: list[str] = Field(default_factory=list)
    bottleneck_ids: list[str] = Field(default_factory=list)
    novelty: str = "Unassessed"
    origins: list[str] = Field(default_factory=list)
    variant_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)
    input_objects: list[str] = Field(default_factory=list)
    output_guarantees: list[str] = Field(default_factory=list)
    reusable_steps: list[str] = Field(default_factory=list)


class MechanismVariant(Record):
    kind: Literal["mechanism_variant"] = "mechanism_variant"
    mechanism_id: str
    technical_difference: str = Field(min_length=1)
    construction: str
    necessary_assumptions: list[str] = Field(default_factory=list)


class Application(Record):
    kind: Literal["application"] = "application"
    mechanism_id: str
    variant_id: str | None = None
    problem_id: str
    result_id: str | None = None
    scope: Scope
    outcome: Literal["SUCCESS", "PARTIAL", "FAILED", "UNASSESSED"] = "UNASSESSED"
    failure_reason: str | None = None


class Result(Record):
    kind: Literal["result"] = "result"
    paper_id: str
    version_id: str
    result_type: Literal["THEOREM", "ALGORITHMIC_GUARANTEE", "EMPIRICAL"]
    statement: str
    scope: Scope
    rate: str | None = None
    mechanism_ids: list[str] = Field(default_factory=list)
    variant_ids: list[str] = Field(default_factory=list)
    problem_ids: list[str] = Field(default_factory=list)
    bottleneck_ids: list[str] = Field(default_factory=list)
    previous_result_ids: list[str] = Field(default_factory=list)
    technical_delta: str = ""
    verification_status: str = "NOT_MATHEMATICALLY_VERIFIED"


class Evidence(Record):
    kind: Literal["evidence"] = "evidence"
    paper_id: str
    version_id: str
    locator: str = Field(min_length=1)
    quotation: str | None = None
    source_hash: str | None = None
    coverage: Coverage

    @field_validator("locator")
    @classmethod
    def meaningful_locator(cls, value):
        if not value.strip():
            raise ValueError("evidence locator cannot be blank")
        return value


class ScientificClaim(Record):
    kind: Literal["claim"] = "claim"
    content: str
    origin: ClaimOrigin
    version_id: str
    subject_ids: list[str] = Field(default_factory=list)
    scope: Scope | None = None


class Relationship(Record):
    kind: Literal["relation"] = "relation"
    source_id: str
    target_id: str
    relation_type: RelationType
    scope: Scope
    assumptions: list[str] = Field(default_factory=list)
    origin: ClaimOrigin = ClaimOrigin.SYSTEM_INFERENCE
    hypothesis: bool = True

    @model_validator(mode="after")
    def attribution(self):
        if not self.evidence_ids:
            raise ValueError("scientific relationships require attributable evidence")
        if not self.hypothesis and self.assessment_status in (
            AssessmentStatus.PROPOSED, AssessmentStatus.UNCERTAIN,
        ):
            raise ValueError("unassessed relationships must remain hypotheses")
        return self


class EvolutionEvent(Record):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["event"] = "event"
    event_type: EventType
    subject_id: str
    related_ids: list[str] = Field(default_factory=list)
    scientific_date: date
    recorded_at: AwareDatetime = Field(default_factory=now)
    paper_id: str
    version_id: str
    scope: Scope
    previous_event_ids: list[str] = Field(default_factory=list)
    resolution: ResolutionKind | None = None
    rationale: str

    @model_validator(mode="after")
    def event_evidence(self):
        if not self.evidence_ids:
            raise ValueError("evolution event requires evidence")
        return self


class LiteratureDelta(Record):
    kind: Literal["comparison"] = "comparison"
    paper_id: str
    version_id: str
    previous_version_id: str | None = None
    new_result_id: str | None = None
    compared_result_ids: list[str] = Field(default_factory=list)
    delta_kinds: list[DeltaKind]
    rationale: str
    proof_obligations: list[str] = Field(default_factory=list)
    needs_review: bool = False
    invalidated_by_version_id: str | None = None


class ResolutionAssessment(Record):
    kind: Literal["resolution_assessment"] = "resolution_assessment"
    problem_id: str
    result_id: str
    resolution: ResolutionKind
    original_scope: Scope
    achieved_scope: Scope
    rationale: str
    proof_obligations: list[str] = Field(default_factory=list)
    needs_review: bool = False


class BreakthroughAssessment(Record):
    kind: Literal["breakthrough"] = "breakthrough"
    problem_id: str
    historical_results: list[str] = Field(default_factory=list)
    previous_mechanisms: list[str] = Field(default_factory=list)
    bottleneck_ids: list[str]
    new_result_id: str
    new_mechanism_ids: list[str]
    technical_delta: str
    resolution_scope: ResolutionKind
    unresolved_questions: list[str] = Field(default_factory=list)
    analogous_problem_ids: list[str] = Field(default_factory=list)
    needs_review: bool = False


class TransferHypothesis(Record):
    kind: Literal["transfer"] = "transfer"
    mode: TransferMode
    source_problem_id: str
    source_bottleneck_id: str | None = None
    source_mechanism_id: str
    breakthrough_id: str | None = None
    target_problem_id: str
    target_bottleneck_id: str | None = None
    maturity: Literal["EXPLORATORY_LEAD", "TRANSFER_HYPOTHESIS", "VALIDATION_PLAN"] = "TRANSFER_HYPOTHESIS"
    match_basis: list[str] = Field(default_factory=list)
    adaptation: str = ""
    bridge_statement: str = ""
    next_action: str = ""
    revisit_when: list[str] = Field(default_factory=list)
    shared_structures: list[str]
    structural_differences: list[str]
    required_assumptions: list[str]
    missing_lemmas: list[str]
    likely_counterexamples: list[str]
    prior_art_ids: list[str] = Field(default_factory=list)
    proposed_result: str
    first_falsification_test: str
    uncertainty: str
    outcome: Literal["PROPOSED", "FAILED", "SUPPORTED"] = "PROPOSED"
    failure_reason: str | None = None
    previous_transfer_id: str | None = None

    @model_validator(mode="after")
    def failed_reason(self):
        if self.outcome == "FAILED" and not self.failure_reason:
            raise ValueError("failed transfers must retain their reason")
        if self.maturity == "EXPLORATORY_LEAD":
            if not self.match_basis or not all(x.strip() for x in self.match_basis) or not self.next_action.strip():
                raise ValueError("exploratory leads require a match basis and next action")
            if self.outcome == "SUPPORTED":
                raise ValueError("exploratory leads cannot be supported transfers")
        if self.maturity == "VALIDATION_PLAN" and (
            not self.adaptation.strip() or not self.bridge_statement.strip()
            or not self.missing_lemmas or not all(x.strip() for x in self.missing_lemmas)
            or not self.first_falsification_test.strip()
        ):
            raise ValueError("validation plans require adaptation, bridge statement, obligations and test")
        return self


OPPORTUNITY_TRANSITIONS = {
    OpportunityStatus.HYPOTHESIS: {OpportunityStatus.SCREENED, OpportunityStatus.BLOCKED, OpportunityStatus.REJECTED, OpportunityStatus.ARCHIVED},
    OpportunityStatus.SCREENED: {OpportunityStatus.INVESTIGATING, OpportunityStatus.BLOCKED, OpportunityStatus.REJECTED, OpportunityStatus.ARCHIVED},
    OpportunityStatus.INVESTIGATING: {OpportunityStatus.PROPOSAL_READY, OpportunityStatus.BLOCKED, OpportunityStatus.REJECTED, OpportunityStatus.ARCHIVED},
    OpportunityStatus.PROPOSAL_READY: {OpportunityStatus.INVESTIGATING, OpportunityStatus.BLOCKED, OpportunityStatus.REJECTED, OpportunityStatus.ARCHIVED},
    OpportunityStatus.BLOCKED: {OpportunityStatus.SCREENED, OpportunityStatus.INVESTIGATING, OpportunityStatus.REJECTED, OpportunityStatus.ARCHIVED},
    OpportunityStatus.REJECTED: {OpportunityStatus.ARCHIVED},
    OpportunityStatus.ARCHIVED: set(),
}
RANKING_DIMENSIONS = {"novelty", "significance", "technical_depth", "feasibility", "falsifiability", "research_fit"}


class RankingDimension(StrictModel):
    score: float | None = Field(default=None, ge=0, le=5)
    rationale: str = "Not assessed"
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def numeric_requires_evidence(self):
        if self.score is not None and (not self.evidence_ids or not self.rationale.strip()):
            raise ValueError("numeric ranking requires attributable evidence and rationale")
        return self


class Opportunity(Record):
    kind: Literal["opportunity"] = "opportunity"
    target_problem_id: str
    bottleneck_ids: list[str]
    mechanism_ids: list[str]
    transfer_id: str | None = None
    paper_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    contribution: str
    closest_result_ids: list[str] = Field(default_factory=list)
    assumptions: list[str]
    proof_obligations: list[str]
    counterexamples: list[str]
    first_validation: str
    significance: str
    novelty_assessment: str
    uncertainty: str
    status: OpportunityStatus = OpportunityStatus.HYPOTHESIS
    rejection_reason: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    ranking: dict[str, RankingDimension] = Field(default_factory=lambda: {
        k: RankingDimension() for k in (
            "novelty", "significance", "technical_depth", "feasibility", "falsifiability", "research_fit"
        )
    })

    @model_validator(mode="after")
    def rejection_retained(self):
        if set(self.ranking) != RANKING_DIMENSIONS:
            raise ValueError("ranking must preserve six separate scientific assessment dimensions")
        if self.status == OpportunityStatus.REJECTED and not self.rejection_reason:
            raise ValueError("rejected opportunities require rejection reason")
        return self


class EntityChange(Record):
    kind: Literal["entity_change"] = "entity_change"
    operation: Literal["MERGE", "SPLIT"]
    source_ids: list[str]
    target_ids: list[str]
    rationale: str


RECORD_TYPES = {c.model_fields['kind'].default: c for c in (
    Paper, PaperVersion, Topic, ProblemFamily, PreciseProblem, Bottleneck,
    MechanismFamily, Mechanism, MechanismVariant, Application, Result, Evidence,
    ScientificClaim, Relationship, EvolutionEvent, LiteratureDelta,
    ResolutionAssessment, BreakthroughAssessment, TransferHypothesis, Opportunity, EntityChange,
)}


def parse_record(data: dict[str, Any]) -> Record:
    kind = data.get("kind")
    if kind not in RECORD_TYPES:
        raise ValueError(f"Unknown record kind: {kind}")
    return RECORD_TYPES[kind].model_validate(data)


def reference_ids(record: Record) -> set[str]:
    """Explicit IDs, including nested review/attempt evidence; never parse prose."""
    found: set[str] = set()
    special = {"historical_results", "previous_mechanisms", "new_mechanism_ids"}
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith('_id') and key not in {'arxiv_id'} and isinstance(item, str):
                    found.add(item)
                elif (key.endswith('_ids') or key in special) and isinstance(item, list):
                    found.update(x for x in item if isinstance(x, str))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(record.model_dump(mode="json"))
    return found


def normalize_identifier(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi.org/", "", value, flags=re.I)
    value = re.sub(r"^doi:\s*", "", value, flags=re.I)
    return value.lower()
