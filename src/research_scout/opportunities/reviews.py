"""Source-pinned research work appended to an opportunity, never theorem promotion."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, field_validator

from research_scout.domain.models import Evidence, Opportunity, StrictModel, now


class ResearchArtifact(StrictModel):
    path: str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    role: Literal['PROOF_NOTES', 'SOURCE_REVIEW', 'EXPERIMENT_SCRIPT',
                  'EXPERIMENT_DATA', 'FIGURE', 'REPORT']

    @field_validator('path')
    @classmethod
    def relative_path(cls, value):
        path = PurePosixPath(value)
        if (not value.strip() or path.is_absolute() or '..' in path.parts
                or '\\' in value or path == PurePosixPath('.')):
            raise ValueError('Artifact path must be relative to the workspace without traversal')
        return value


class ResearchFinding(StrictModel):
    kind: Literal['CONDITIONAL_DERIVATION', 'NUMERICAL_DIAGNOSTIC',
                  'COUNTEREXAMPLE_DERIVATION', 'PRIOR_ART_REVIEW']
    claim: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    metric: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    verification: Literal['NOT_INDEPENDENTLY_VERIFIED'] = 'NOT_INDEPENDENTLY_VERIFIED'

    @field_validator('claim', 'scope', 'metric', 'limitation')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Finding details must be substantive')
        return value

    @field_validator('assumptions')
    @classmethod
    def nonblank_assumptions(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError('Assumptions cannot be blank')
        return values


class ResearchReview(StrictModel):
    opportunity_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    decision: Literal['CONTINUE_NARROWED', 'DOWNRANK', 'DEFER']
    revised_question: str = Field(min_length=1)
    findings: list[ResearchFinding] = Field(min_length=1)
    remaining_work: list[str] = Field(min_length=1)
    artifacts: list[ResearchArtifact] = Field(min_length=1)
    source_evidence_ids: list[str] = Field(default_factory=list)
    novelty: Literal['UNDETERMINED'] = 'UNDETERMINED'
    origin: Literal['SYSTEM_INFERENCE'] = 'SYSTEM_INFERENCE'

    @field_validator('opportunity_id', 'reviewer', 'summary', 'revised_question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Review details cannot be blank')
        return value

    @field_validator('remaining_work', 'source_evidence_ids')
    @classmethod
    def substantive_list(cls, values):
        if any(not value.strip() for value in values):
            raise ValueError('Review list entries cannot be blank')
        return values


def review_id(review: ResearchReview) -> str:
    payload = json.dumps(review.model_dump(mode='json'), sort_keys=True,
                         ensure_ascii=False, separators=(',', ':'))
    return 'research-review-' + hashlib.sha256(payload.encode()).hexdigest()


class ResearchReviewService:
    def __init__(self, archive, workspace):
        self.archive = archive
        self.workspace = Path(workspace).resolve()

    def _opportunity(self, identifier):
        record = self.archive.get(identifier)
        if not isinstance(record, Opportunity):
            raise ValueError('Research review requires an Opportunity ID')
        return record

    def reviews(self, opportunity_id) -> list[dict]:
        output = []
        for entry in self._opportunity(opportunity_id).history:
            if entry.get('action') != 'RESEARCH_REVIEW':
                continue
            review = ResearchReview.model_validate(entry['review'])
            if (review.opportunity_id != opportunity_id
                    or review_id(review) != entry['review_fingerprint']):
                raise ValueError('Research review identity does not match retained payload')
            output.append(review.model_dump(mode='json'))
        return output

    def record(self, review: ResearchReview) -> Opportunity:
        # model_copy/model_construct can bypass Pydantic validation. Reparse the
        # full payload before any publication, including nested findings/files.
        review = ResearchReview.model_validate(
            review.model_dump(mode='json') if isinstance(review, ResearchReview) else review)
        opportunity = self._opportunity(review.opportunity_id)
        # Validate every external reference before publishing any history.
        evidence = [self.archive.get(identifier) for identifier in review.source_evidence_ids]
        if any(not isinstance(item, Evidence) for item in evidence):
            raise ValueError('source_evidence_ids must identify Evidence records')
        if not opportunity.synthetic and any(item.synthetic for item in evidence):
            raise ValueError('Synthetic evidence cannot support a genuine research review')
        paths = set()
        for artifact in review.artifacts:
            path = (self.workspace / artifact.path).resolve()
            if not path.is_relative_to(self.workspace):
                raise ValueError('Artifact escapes workspace through a symlink')
            if path in paths:
                raise ValueError('Duplicate artifact path')
            paths.add(path)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
                raise ValueError(f'Artifact missing or hash mismatch: {artifact.path}')
        identifier = review_id(review)
        # Validate retained reviews too; raw imported malformed history must fail visibly.
        self.reviews(opportunity.id)
        if any(entry.get('review_fingerprint') == identifier for entry in opportunity.history):
            return opportunity
        entry = {'timestamp': now().isoformat(), 'action': 'RESEARCH_REVIEW',
                 'review_fingerprint': identifier, 'reviewer': review.reviewer,
                 'review': review.model_dump(mode='json')}
        return self.archive.put(opportunity.model_copy(update={
            'history': opportunity.history + [entry],
            'evidence_ids': sorted(set(opportunity.evidence_ids + review.source_evidence_ids)),
            'paper_ids': sorted(set(opportunity.paper_ids + [item.paper_id for item in evidence])),
        }))


def research_review_markdown(reviews: list[dict]) -> list[str]:
    """Render retained work with explicit scope, uncertainty and content pins."""
    lines = []
    for payload in reviews:
        review = ResearchReview.model_validate(payload)
        lines += ['', '### 研究复核 / Research review', '',
                  f'判定：{review.decision}；新颖性：{review.novelty}；来源：{review.origin}', '',
                  review.summary, '', '收窄后的问题：' + review.revised_question, '']
        for finding in review.findings:
            lines += [f'- [{finding.kind}] {finding.claim}',
                      '  范围：' + finding.scope, '  假设：' + '; '.join(finding.assumptions),
                      '  指标：' + finding.metric, '  限制：' + finding.limitation,
                      '  核验状态：' + finding.verification]
        lines += ['', '后续工作：'] + ['- ' + item for item in review.remaining_work]
        lines += ['', '背景来源证据（不证明本轮推导）：'
                  + ', '.join(review.source_evidence_ids), '', '本地研究产物及内容指纹：']
        lines += [f'- `{a.path}` ({a.role}); sha256 `{a.sha256}`' for a in review.artifacts]
    return lines
