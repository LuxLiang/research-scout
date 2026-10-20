from datetime import date
import pytest
from pydantic import ValidationError

from research_scout.domain.models import (
    AssessmentStatus, Bottleneck, BottleneckStatus, ClaimOrigin, EvolutionEvent,
    EventType, ScientificClaim, parse_record, reference_ids,
)
from research_scout.workflows.demo import SCOPE, synthetic_records


def test_all_fixture_schemas_round_trip_and_references():
    records=synthetic_records()
    ids={r.id for r in records}
    for record in records:
        assert parse_record(record.model_dump(mode='json')) == record
        assert reference_ids(record) <= ids
        assert record.synthetic


def test_scientific_authority_requires_review_and_evidence():
    with pytest.raises(ValidationError,match='review'):
        ScientificClaim(id='claim-x',title='Unsupported',content='Solved',
            origin=ClaimOrigin.SYSTEM_INFERENCE,version_id='v1',
            assessment_status=AssessmentStatus.INDEPENDENTLY_REVIEWED)
    with pytest.raises(ValidationError,match='evidence'):
        Bottleneck(id='bn-x',title='Invented obstruction',description='d',obstruction='o',
            insufficiency='i',status=BottleneckStatus.ESTABLISHED_BOTTLENECK)


def test_events_require_evidence_and_are_frozen():
    with pytest.raises(ValidationError,match='evidence'):
        EvolutionEvent(id='e-x',title='No evidence',event_type=EventType.PROBLEM_POSED,
            subject_id='p',scientific_date=date(2023,1,1),paper_id='a',version_id='a1',
            scope=SCOPE,rationale='unattributed')
    event=next(r for r in synthetic_records() if r.kind=='event')
    with pytest.raises(ValidationError):
        event.rationale='rewrite history'


def test_unknown_schema_and_unknown_fields_fail_closed():
    data=synthetic_records()[0].model_dump(mode='json')
    with pytest.raises(ValidationError):
        parse_record({**data,'schema_version':'99.0'})
    with pytest.raises(ValidationError):
        parse_record({**data,'globally_solved':True})


@pytest.mark.parametrize('field', ['domain','model','objective','metric','guarantee'])
def test_blank_formulation_rejected(field):
    with pytest.raises(ValidationError,match='blank'):
        SCOPE.model_copy().model_validate({**SCOPE.model_dump(),field:'   '})


def test_unsupported_numeric_ranking_rejected():
    from research_scout.domain.models import RankingDimension
    with pytest.raises(ValidationError,match='evidence'):
        RankingDimension(score=5,rationale='a guess')


def test_naive_recording_timestamp_rejected():
    data=synthetic_records()[0].model_dump(mode='json')
    data['created_at']='2026-10-18T12:00:00'
    with pytest.raises(ValidationError,match='timezone'):
        parse_record(data)


def test_validation_plan_requires_a_bridge_and_an_executable_test():
    from research_scout.domain.models import TransferHypothesis
    data = dict(id='transfer-test', title='SYNTHETIC validation interface', synthetic=True,
                mode='TECHNIQUE_FIRST', source_problem_id='source', target_problem_id='target',
                source_mechanism_id='mechanism', maturity='VALIDATION_PLAN', shared_structures=[],
                structural_differences=[], required_assumptions=[], missing_lemmas=['Bridge bound'],
                likely_counterexamples=[], proposed_result='SYNTHETIC target improvement',
                adaptation='Replace the old conditional-error bound',
                first_falsification_test='Compute the conditional variance for a two-state chain',
                uncertainty='SYNTHETIC unproved plan')
    with pytest.raises(ValidationError, match='bridge statement'):
        TransferHypothesis(**data)
    data['bridge_statement'] = 'The one-step conditional variance is bounded by C h squared'
    assert TransferHypothesis(**data).target_bottleneck_id is None
    data['first_falsification_test'] = '   '
    with pytest.raises(ValidationError, match='obligations and test'):
        TransferHypothesis(**data)
