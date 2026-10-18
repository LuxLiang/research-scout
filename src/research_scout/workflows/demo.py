"""Explicit synthetic history used by the deterministic offline demonstration."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from importlib.resources import files

from research_scout.domain.models import (
    Application, Attempt, AssessmentStatus as A, Bottleneck, BottleneckStatus, ClaimOrigin,
    Coverage, Evidence, EvolutionEvent, EventType, Mechanism, MechanismFamily,
    MechanismVariant, Paper, PaperVersion, PreciseProblem, ProblemFamily, Record,
    Relationship, RelationType, Result, Review, Scope, ScientificClaim, Topic,
)

STAMP = datetime(2026, 10, 18, tzinfo=timezone.utc)
SCOPE = Scope(domain="synthetic sampling", model="finite-dimensional coupled stochastic system",
    objective="convergence to equilibrium", assumptions=["smooth potential", "uniform curvature", "bounded noise"],
    quantifiers=["all admissible initial laws"], metric="weighted Wasserstein distance",
    guarantee="exponential convergence")
TARGET_SCOPE = Scope(domain="synthetic distributed optimization", model="delayed consensus",
    objective="decay of disagreement", assumptions=["bounded delay", "connected communication graph"],
    quantifiers=["all admissible initial histories"], metric="augmented-state disagreement",
    guarantee="exponential decay")


def base(id: str, title: str, evidence: list[str] | None = None, reviewed=False):
    evidence = evidence or []
    result = dict(id=id, title=title, synthetic=True, provenance="explicit synthetic fixture",
        created_at=STAMP, updated_at=STAMP, evidence_ids=evidence,
        assessment_status=A.INDEPENDENTLY_REVIEWED if reviewed else A.SUPPORTED_BY_SOURCE)
    if reviewed:
        result['review'] = Review(reviewer="synthetic-reviewer-not-a-real-scientific-review",
            timestamp=STAMP, rationale="SYNTHETIC attribution gate fixture only; no mathematical verification.",
            evidence_ids=evidence)
    return result


def synthetic_records() -> list[Record]:
    source = files('research_scout.resources').joinpath('synthetic-history.md').read_text()
    digest = hashlib.sha256(source.encode()).hexdigest()
    records: list[Record] = []
    for name, year, title in [('a', 2023, 'An energy obstruction'),
                             ('b', 2024, 'A restricted quadratic calculation'),
                             ('c', 2026, 'A cross-term energy construction')]:
        records.extend([
            Paper(**base(f'paper-{name}', f'SYNTHETIC Paper {name.upper()}: {title}'),
                authors=['Fictional Researcher'], published=date(year, 1, 1),
                labels=['synthetic', 'sampling', 'convergence'], version_ids=[f'version-{name}-1']),
            PaperVersion(**base(f'version-{name}-1', f'SYNTHETIC {name.upper()} v1'),
                paper_id=f'paper-{name}', version='1', content_hash=digest,
                coverage=Coverage.FULL_TEXT, published=date(year, 1, 1),
                source_urls=['synthetic://research-scout/history']),
        ])
    for eid, paper, locator, quote in [
        ('evidence-a-problem','a','Paper A / Problem P','The missing state-space dissipation estimate obstructs a direct proof.'),
        ('evidence-a-failure','a','Paper A / Failed approach','A position-only energy ignores the cross-coordinate interaction.'),
        ('evidence-b-result','b','Paper B / Result B','The general smooth-potential case remains open.'),
        ('evidence-c-result','c','Paper C / Result C',"Under exactly Problem P's original assumptions and quantifiers"),
        ('evidence-c-delta','c','Paper C / Construction delta','a state-dependent block energy with a mixed position–velocity term'),
        ('evidence-q','a','Target Q / Problem Q','the delay operator is nonlocal in time'),
        ('evidence-q-failure','a','Target Q / Failure witness','Unbounded delay can create oscillatory modes'),
    ]:
        assert ' '.join(quote.split()) in ' '.join(source.split()), quote
        records.append(Evidence(**base(eid, 'SYNTHETIC source: '+locator), paper_id=f'paper-{paper}',
            version_id=f'version-{paper}-1', locator=locator, quotation=quote,
            source_hash=digest, coverage=Coverage.FULL_TEXT))
    records += [
        Topic(**base('topic-sampling', 'Sampling'), labels=['synthetic']),
        ProblemFamily(**base('family-convergence', 'Coupled-system convergence'), topic_id='topic-sampling'),
        PreciseProblem(**base('problem-p', 'SYNTHETIC P: full-state convergence', ['evidence-a-problem']),
            family_id='family-convergence', statement='Establish full-state convergence under the original assumptions.',
            scope=SCOPE, desired_result=SCOPE.guarantee, bottleneck_ids=['bottleneck-dissipation'],
            known_result_ids=['result-b', 'result-c'], structures=['coupled state space', 'dissipation deficit', 'mixed energy']),
        PreciseProblem(**base('problem-q', 'SYNTHETIC Q: delayed consensus', ['evidence-q']),
            statement='Control disagreement in an augmented-state delayed consensus system.', scope=TARGET_SCOPE,
            desired_result=TARGET_SCOPE.guarantee, bottleneck_ids=['bottleneck-delay'],
            unresolved_scope=['nonlocal delay commutator bound'],
            structures=['coupled state space', 'dissipation deficit', 'mixed energy']),
        Bottleneck(**base('bottleneck-dissipation', 'Missing full-state dissipation', ['evidence-a-problem', 'evidence-a-failure']),
            description='Energy cannot control full-state distance.', obstruction='uncontrolled mixed term',
            insufficiency='Position-only and diagonal energy omit the mixed interaction.',
            status=BottleneckStatus.ESTABLISHED_BOTTLENECK, problem_ids=['problem-p'],
            attempts=[Attempt(description='Position-only energy lacks full-state control',
                outcome='FAILED',evidence_ids=['evidence-a-failure'],
                reason='The mixed interaction is not controlled.'),
                Attempt(description='Quadratic special case',outcome='PARTIAL',
                    mechanism_id='mechanism-diagonal',result_id='result-b',
                    evidence_ids=['evidence-b-result'],reason='General smooth-potential setting remains open.')],
            addressing_mechanism_ids=['mechanism-diagonal'], overcoming_mechanism_ids=['mechanism-cross'],
            structures=['dissipation deficit', 'coupled state space']),
        Bottleneck(**base('bottleneck-delay', 'Missing augmented-state dissipation', ['evidence-q']),
            description='Delay operator prevents a local coercivity estimate.', obstruction='nonlocal mixed term',
            insufficiency='A state-local energy does not bound history interactions.',
            problem_ids=['problem-q'], remaining_settings=['delay commutator control'],
            structures=['dissipation deficit', 'coupled state space']),
        MechanismFamily(**base('mechanism-family-energy', 'Energy methods'), principle='Construct a coercive energy.'),
        Mechanism(**base('mechanism-diagonal', 'Diagonal Lyapunov energy', ['evidence-b-result']),
            family_id='mechanism-family-energy', principle='Use a diagonal quadratic form.',
            construction='Diagonal state-coordinate weights.', proof_role='restricted-case decay',
            bottleneck_ids=['bottleneck-dissipation'], structures=['coupled state space'],
            limitations=['Fails to control mixed interactions outside the quadratic special case.']),
        Mechanism(**base('mechanism-cross', 'Cross-term Lyapunov energy', ['evidence-c-delta']),
            family_id='mechanism-family-energy', principle='Recover dissipation with mixed-coordinate energy.',
            construction='State-dependent block energy with mixed position–velocity term.',
            proof_role='close the missing coercivity estimate', bottleneck_ids=['bottleneck-dissipation'],
            necessary_assumptions=['uniform curvature', 'bounded commutator', 'positive-definite energy'],
            structures=['coupled state space', 'dissipation deficit', 'mixed energy'],
            limitations=['No established delay commutator bound.'], variant_ids=['variant-cross-state']),
        MechanismVariant(**base('variant-cross-state', 'State-dependent mixed block form', ['evidence-c-delta']),
            mechanism_id='mechanism-cross', construction='State-dependent off-diagonal energy blocks.',
            technical_difference='A curvature-dependent mixed block replaces constant off-diagonal weights.'),
    ]
    partial = SCOPE.model_copy(update={'assumptions': SCOPE.assumptions + ['quadratic potential']})
    records += [
        Result(**base('result-b', 'SYNTHETIC restricted convergence result', ['evidence-b-result'], reviewed=True),
            paper_id='paper-b', version_id='version-b-1', result_type='THEOREM',
            statement='Exponential convergence for quadratic potential.', scope=partial,
            mechanism_ids=['mechanism-diagonal'], problem_ids=['problem-p'],
            bottleneck_ids=['bottleneck-dissipation'], rate='C exp(-lambda t)'),
        Result(**base('result-c', 'SYNTHETIC original-scope convergence', ['evidence-c-result','evidence-c-delta'], reviewed=True),
            paper_id='paper-c', version_id='version-c-1', result_type='THEOREM',
            statement='Cross-term energy establishes the original P guarantee.', scope=SCOPE,
            mechanism_ids=['mechanism-cross'], variant_ids=['variant-cross-state'], problem_ids=['problem-p'],
            bottleneck_ids=['bottleneck-dissipation'], previous_result_ids=['result-b'],
            technical_delta='The diagonal energy left a mixed term uncontrolled. A state-dependent mixed block and a uniform-curvature commutator estimate recover positive coercivity and close the dissipation bound.',
            rate='C exp(-lambda t)'),
        Application(**base('application-b', 'Diagonal method in P', ['evidence-b-result']),
            mechanism_id='mechanism-diagonal', problem_id='problem-p', result_id='result-b', scope=partial, outcome='PARTIAL'),
        Application(**base('application-c', 'Mixed energy in P', ['evidence-c-result']),
            mechanism_id='mechanism-cross', variant_id='variant-cross-state', problem_id='problem-p',
            result_id='result-c', scope=SCOPE, outcome='SUCCESS'),
        ScientificClaim(**base('claim-c', 'SYNTHETIC authors claim original-scope convergence', ['evidence-c-result']),
            content='Authors attribute full original-scope convergence to the mixed energy construction.',
            origin=ClaimOrigin.AUTHOR, version_id='version-c-1', subject_ids=['result-c','problem-p'], scope=SCOPE),
    ]
    for rid, source_id, target_id, kind, evidence, scope in [
        ('rel-p-b','problem-p','bottleneck-dissipation',RelationType.PROBLEM_LIMITED_BY_BOTTLENECK,['evidence-a-problem'],SCOPE),
        ('rel-q-b','problem-q','bottleneck-delay',RelationType.PROBLEM_LIMITED_BY_BOTTLENECK,['evidence-q'],TARGET_SCOPE),
        ('rel-c-b','result-c','bottleneck-dissipation',RelationType.RESULT_OVERCOMES_BOTTLENECK,['evidence-c-delta'],SCOPE),
        ('rel-c-p','result-c','problem-p',RelationType.RESULT_ADDRESSES_PROBLEM,['evidence-c-result'],SCOPE),
        ('rel-m-b','mechanism-cross','bottleneck-dissipation',RelationType.MECHANISM_ADDRESSES_BOTTLENECK,['evidence-c-delta'],SCOPE),
        ('rel-b-p','result-b','problem-p',RelationType.RESULT_ADDRESSES_PROBLEM,['evidence-b-result'],partial),
    ]:
        records.append(Relationship(**base(rid,'SYNTHETIC '+kind.value,evidence), source_id=source_id,
            target_id=target_id, relation_type=kind, scope=scope, hypothesis=False, origin=ClaimOrigin.AUTHOR))
    for eid, paper, year, kind, evidence, related, previous, scope in [
        ('event-posed','a',2023,EventType.PROBLEM_POSED,['evidence-a-problem'],[],[],SCOPE),
        ('event-partial','b',2024,EventType.PARTIAL_PROGRESS,['evidence-b-result'],['result-b','mechanism-diagonal'],['event-posed'],partial),
        ('event-result','c',2026,EventType.NEW_RESULT,['evidence-c-result','evidence-c-delta'],['result-c','mechanism-cross'],['event-partial'],SCOPE),
    ]:
        records.append(EvolutionEvent(**base(eid,'SYNTHETIC '+kind.value,evidence), event_type=kind,
            subject_id='problem-p', related_ids=related, scientific_date=date(year,1,1),
            recorded_at=STAMP, paper_id=f'paper-{paper}', version_id=f'version-{paper}-1',
            scope=scope, previous_event_ids=previous, rationale='Synthetic historical milestone.'))
    return records


def import_history(archive) -> list[Record]:
    """Atomic, repeatable fixture import, explicit and never a model fallback."""
    records = synthetic_records()
    # Existing records can have richer post-import state; never rewind them.
    missing = []
    for record in records:
        try:
            archive.get(record.id)
        except KeyError:
            missing.append(record)
    if missing:
        archive.put_many(missing)
    return records


def run_demo(archive, output=None):
    """A→B→C, scoped resolution, breakthrough→Q→hypothesis→opportunity→proposal."""
    from research_scout.breakthrough import BreakthroughDiscovery
    from research_scout.comparison import ComparisonEngine
    from research_scout.domain.models import ResolutionKind
    from research_scout.evolution import EventStore, ProblemEvolutionTimeline, assess_resolution
    from research_scout.integration import export_proposal
    from research_scout.opportunities import OpportunityPortfolio
    from research_scout.transfer import TransferDiscovery

    import_history(archive)
    partial = assess_resolution(archive, 'problem-p', 'result-b')
    full = assess_resolution(archive, 'problem-p', 'result-c')
    if full.resolution != ResolutionKind.FULL_RESOLUTION_SUPPORTED:
        raise ValueError('Synthetic C must support the exact fixture problem scope')
    event = EvolutionEvent(**base('event-supported', 'SYNTHETIC source-supported resolution',
        ['evidence-c-result','evidence-c-delta']), event_type=EventType.SUPPORTED_RESOLUTION,
        subject_id='problem-p', related_ids=['result-c','mechanism-cross', 'bottleneck-dissipation', full.id],
        scientific_date=date(2026,1,2), recorded_at=STAMP, paper_id='paper-c',
        version_id='version-c-1', scope=SCOPE, previous_event_ids=['event-result'],
        resolution=full.resolution, rationale='Exact original scope supported by fictional source; not mathematical verification.')
    EventStore(archive).append(event)
    comparisons = ComparisonEngine(archive).compare('paper-c')
    breakthrough = BreakthroughDiscovery(archive).analyze('result-c')
    transfer = TransferDiscovery(archive).propose('mechanism-cross','problem-q',
        mode='BREAKTHROUGH_FIRST', breakthrough_id=breakthrough.id)
    opportunity = OpportunityPortfolio(archive).from_transfer(transfer.id)
    proposal = export_proposal(archive, opportunity.id, output) if output else None
    timeline = ProblemEvolutionTimeline(archive,'problem-p').build()
    return {
        'synthetic':True, 'scientific_correctness_verified':False,
        'partial_resolution':partial.resolution.value,
        'problem_id':'problem-p', 'timeline_status':timeline.status.value,
        'event_ids':[e.id for e in timeline.events],
        'comparison_ids':[c.id for c in comparisons], 'breakthrough_id':breakthrough.id,
        'analogous_problem_ids':breakthrough.analogous_problem_ids,
        'transfer_id':transfer.id,'opportunity_id':opportunity.id,
        'proposal_path':str(proposal) if proposal else None,
    }
