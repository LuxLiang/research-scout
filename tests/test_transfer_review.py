"""Artificial sources exercise transfer attribution and weekly failure isolation."""
import json
from types import SimpleNamespace

import pytest

from research_scout.domain.models import PreciseProblem
from research_scout.workflows.transfer_review import TransferReview
from research_scout.workflows.weekly import WeeklyCollector
from test_gaps import setup as gap_setup
from test_weekly import profile


def setup(tmp_path):
    archive, _ = gap_setup(tmp_path)
    result = archive.get('result:2')
    archive.put(PreciseProblem(id='problem:target', title='ARTIFICIAL TARGET',
        statement='Artificial target question', desired_result='Test improved guarantee',
        scope=result.scope, evidence_ids=['evidence:2']))
    archive.put(result.model_copy(update={'problem_ids':['problem:target']}))
    result = archive.get('result:1')
    archive.put(result.model_copy(update={'mechanism_ids':['mechanism:1']}))
    idea = dict(title='ARTIFICIAL TRANSFER', source_result_id='result:1',
        source_mechanism_id='mechanism:1', target_problem_id='problem:target',
        target_result_ids=['result:2'], evidence_ids=['evidence:1','evidence:2'],
        shared_structure='Test shared structure', adaptation='Construct test operator on target',
        expected_gain='Conditional gain only if the test stability lemma holds',
        required_assumptions=['Test uniform moments'], missing_lemmas=['Test stability lemma'],
        likely_counterexamples=['Test heavy-tailed input'],
        first_falsification_test='Compute the operator on a two-variable example',
        closest_prior_art='Test result 2 has no established transfer', uncertainty='Artificial test only')
    return archive, idea


class Model:
    def __init__(self, ideas):
        self.ideas, self.calls = ideas, 0
        self.grounding_calls = 0

    def run_structured(self, prompt, schema):
        if prompt.startswith('Ground these unverified'):
            self.grounding_calls += 1
            assert 'untrusted data' in prompt and 'Retrieved original source windows' in prompt
            batch = json.loads(prompt.split('\nCandidates:\n', 1)[1].split(
                '\nOriginal source records and evidence:\n', 1)[0])
            return {'batch_json': json.dumps(batch)}
        self.calls += 1
        assert 'untrusted data' in prompt and 'entire library' in prompt
        assert schema['additionalProperties'] is False
        context = json.loads(prompt.split('\nContext:\n', 1)[1])
        candidates = {idea['source_mechanism_id'] for idea in self.ideas}
        technique_reviews = [dict(source_mechanism_id=t['source_mechanism_id'],
            outcome='CANDIDATE' if t['source_mechanism_id'] in candidates else 'NO_SUPPORTED_IDEA',
            rationale='ARTIFICIAL focus technique considered against supplied problems')
            for t in context.get('techniques_to_review', [])]
        return {'batch_json':json.dumps(dict(ideas=self.ideas, excluded_ideas=[],
            technique_reviews=technique_reviews, limitations=['Artificial unit-test sources only']))}


def test_transfer_report_cache_and_no_scientific_promotion(tmp_path):
    archive, idea = setup(tmp_path)
    model = Model([idea])
    worker = TransferReview(archive,tmp_path,tmp_path/'sources',model)
    first = worker.run(focus_paper_ids=['paper:1'])
    assert worker.run(focus_paper_ids=['paper:1']) == first and model.calls == 1
    assert first['source_paper_count'] == 2
    assert first['novelty'] == 'UNDETERMINED' and not first['external_prior_art_searched']
    assert set(first['evidence_index']) == {'evidence:1','evidence:2'}
    assert '首个证伪测试' in (tmp_path/'reports/transfers/latest.md').read_text()
    assert not archive.list('opportunity') and not archive.list('transfer')
    worker.run(refresh=True,focus_paper_ids=['paper:1'])
    assert model.calls == 2


def test_unknown_focus_paper_fails_before_model_or_report_publication(tmp_path):
    archive, _ = setup(tmp_path)
    model = Model([])
    worker = TransferReview(archive, tmp_path, tmp_path / 'sources', model)
    with pytest.raises(ValueError, match='Focus papers'):
        worker.run(focus_paper_ids=['invented-paper'])
    assert model.calls == 0
    assert not (tmp_path / 'reports' / 'transfers' / 'latest.json').exists()


@pytest.mark.parametrize('change', ['invented','wrong_mechanism','wrong_target','missing_owner',
    'unrelated_evidence','duplicate','too_many','promoted_novelty','blank','existing_application','same_paper'])
def test_unsupported_transfer_is_rejected_before_publication(tmp_path, change):
    archive, idea = setup(tmp_path)
    ideas = [idea]
    if change == 'invented':
        idea['source_result_id'] = 'invented'
    elif change == 'wrong_mechanism':
        idea['source_mechanism_id'] = 'mechanism:2'
    elif change == 'wrong_target':
        idea['target_result_ids'] = ['result:1']
    elif change == 'missing_owner':
        idea['evidence_ids'] = ['evidence:1','evidence:1']
    elif change == 'unrelated_evidence':
        r = archive.get('result:2')
        archive.put(r.model_copy(update={'evidence_ids':[]}))
    elif change == 'duplicate':
        ideas *= 2
    elif change == 'too_many':
        ideas *= 4
    elif change == 'promoted_novelty':
        idea['novelty'] = 'CONFIRMED'
    elif change == 'blank':
        idea['adaptation'] = ' '
    elif change == 'existing_application':
        r = archive.get('result:2')
        archive.put(r.model_copy(update={'mechanism_ids':['mechanism:1']}))
    else:
        r = archive.get('result:2')
        archive.put(r.model_copy(update={'paper_id':'paper:1','version_id':'version:1',
                                        'evidence_ids':['evidence:1']}))
    with pytest.raises(ValueError):
        TransferReview(archive,tmp_path,tmp_path/'sources',Model(ideas)).run()
    assert not (tmp_path/'reports/transfers/latest.json').exists()


def test_zero_candidates_and_model_failure_are_explicit(tmp_path):
    archive, _ = setup(tmp_path)
    worker = TransferReview(archive,tmp_path,tmp_path/'sources',Model([]))
    assert worker.run()['ideas'] == []
    with pytest.raises(ValueError,match='backend'):
        TransferReview(archive,tmp_path,tmp_path/'sources',object()).run(refresh=True)
    with pytest.raises(ValueError,match='candidate limit'):
        worker.run(0)


def test_weekly_transfer_runs_after_fields_despite_narrative_failure(tmp_path,monkeypatch):
    from research_scout.workflows.related_work import RelatedWorkReview
    from research_scout.workflows.fields import FieldDossiers
    archive, idea = setup(tmp_path)
    order = []
    def failed_narrative(self):
        order.append('related')
        raise RuntimeError('Narrative model unavailable')
    monkeypatch.setattr(RelatedWorkReview,'run',failed_narrative)
    monkeypatch.setattr(FieldDossiers,'update',lambda self:order.append('fields') or [])
    def review(self, n, **kwargs):
        order.append('transfers')
        assert n == 3 and kwargs['focus_paper_ids'] == []
        return dict(ideas=[idea], excluded_ideas=[], limitations=['Artificial test only'])
    monkeypatch.setattr(TransferReview,'run',review)
    worker = WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),
        arxiv=SimpleNamespace(search=lambda *a,**k:[]))
    selected = profile(transfer_review=True,related_work_review=True,field_dossiers=True)
    report = worker.run(selected)
    assert order == ['related','fields','transfers']
    assert report['transfer_review']['candidate_count'] == 1
    text = (tmp_path/'reports/latest.md').read_text()
    assert 'ARTIFICIAL TRANSFER' in text and '首个证伪测试' in text
    assert report['errors'][0]['stage'] == 'related_work_review'
    def fail(*a, **kw):
        raise RuntimeError('Transfer model unavailable')
    monkeypatch.setattr(TransferReview,'run',fail)
    report = worker.run(selected)
    assert not report.get('transfer_review')
    assert report['errors'][-1]['stage'] == 'transfer_review'
    assert 'Transfer model unavailable' in (tmp_path/'reports/latest.md').read_text()


def test_default_twenty_papers_and_sampling_profile_enabled(tmp_path):
    from pathlib import Path
    from research_scout.workflows.weekly import WeeklyProfile
    from research_scout.storage import Archive
    from test_weekly import Sources, source
    assert profile(extract=False).max_papers == 20
    example = WeeklyProfile.load(Path(__file__).parents[1]/'config/sampling-weekly.example.json')
    assert example.max_papers == 20 and example.transfer_review
    worker = WeeklyCollector(Archive(tmp_path/'knowledge'),tmp_path,tmp_path/'sources',
        arxiv=Sources([source(i,f'Artificial sampling {i}') for i in range(21)]))
    report = worker.run(profile(extract=False))
    assert report['selected'] == 20 and report['remaining_pending'] == 1
    assert not report.get('transfer_review')


def field_context(tmp_path):
    archive,idea=setup(tmp_path)
    fields=[dict(id='overview',title='ARTIFICIAL overview',question='Test',
                 result_ids=['result:1','result:2']),
            dict(id='source-field',parent_id='overview',title='ARTIFICIAL source',question='Test',
                 result_ids=['result:1']),
            dict(id='target-field',parent_id='overview',title='ARTIFICIAL target',question='Test',
                 result_ids=['result:2'])]
    (tmp_path/'fields.json').write_text(json.dumps(dict(fields=fields)))
    worker=TransferReview(archive,tmp_path,tmp_path/'sources',object())
    context=worker._context()
    context['focus_paper_ids']=[]
    context['field_pairs_to_review']=[dict(source_field_id='source-field',target_field_id='target-field')]
    idea.update(source_field_id='source-field',target_field_id='target-field')
    pair=dict(source_field_id='source-field',target_field_id='target-field',
              outcome='CANDIDATE',rationale='Artificial operator acts on the same test structure')
    return worker,context,idea,pair


def test_directed_cross_field_membership_and_rotation(tmp_path):
    from research_scout.workflows.transfer_review import TransferIdeas
    worker,context,idea,pair=field_context(tmp_path)
    batch=TransferIdeas(ideas=[idea],field_pair_reviews=[pair],limitations=['Artificial tests only'])
    worker._validate(batch,context,3)
    chosen=worker._field_pairs(context,1)
    assert chosen==context['field_pairs_to_review']
    assert all('overview' not in p.values() for p in worker._field_pairs(context,100))
    directory=tmp_path/'reports/transfers'
    directory.mkdir(parents=True)
    report=dict(field_pair_reviews=[pair])
    (directory/'abc123.json').write_text(json.dumps(report))
    (directory/'latest.json').write_text(json.dumps(report))
    next_pair=worker._field_pairs(context,1)
    assert next_pair==[dict(source_field_id='target-field',target_field_id='source-field')]
    assert len(worker._field_pairs(context,100))==2


@pytest.mark.parametrize('change',['missing_review','duplicate_review','fake_field','swapped_fields',
                                   'overlapping_memberships','false_outcome','blank_reason'])
def test_cross_field_coverage_and_attribution_cannot_be_fabricated(tmp_path,change):
    from research_scout.workflows.transfer_review import TransferIdeas
    worker,context,idea,pair=field_context(tmp_path)
    reviews=[pair]
    if change=='missing_review':
        reviews=[]
    elif change=='duplicate_review':
        reviews*=2
    elif change=='fake_field':
        idea['target_field_id']='invented'
    elif change=='swapped_fields':
        idea.update(source_field_id='target-field',target_field_id='source-field')
    elif change=='overlapping_memberships':
        context['field_index']['target-field']['result_ids'].append('result:1')
    elif change=='false_outcome':
        pair['outcome']='NO_SUPPORTED_IDEA'
    else:
        pair['rationale']=' '
    with pytest.raises(ValueError):
        batch=TransferIdeas(ideas=[idea],field_pair_reviews=reviews,limitations=['Artificial tests only'])
        worker._validate(batch,context,3)


def test_cross_field_zero_ideas_still_records_every_attempt(tmp_path):
    from research_scout.workflows.transfer_review import TransferIdeas
    worker,context,idea,pair=field_context(tmp_path)
    pair['outcome']='NO_SUPPORTED_IDEA'
    pair['rationale']='Artificial source smoothness has not been established at target'
    worker._validate(TransferIdeas(ideas=[],field_pair_reviews=[pair],limitations=['Test']),context,3)
    report=dict(ideas=[],field_pair_reviews=[pair],excluded_ideas=[],limitations=['Test'],
                source_paper_count=2,evidence_index={})
    assert 'NO_SUPPORTED_IDEA' in worker._markdown(report)


def test_scheduler_prefers_cross_family_and_spreads_sources(tmp_path):
    worker,context,_,_=field_context(tmp_path)
    # ARTIFICIAL navigation data; no scientific inference is tested here.
    context['field_index']={
        'family-a':dict(parent_id=None,is_leaf=False,result_ids=[]),
        'family-b':dict(parent_id=None,is_leaf=False,result_ids=[]),
        'a1':dict(parent_id='family-a',is_leaf=True,result_ids=['test-a1']),
        'a2':dict(parent_id='family-a',is_leaf=True,result_ids=['test-a2']),
        'b1':dict(parent_id='family-b',is_leaf=True,result_ids=['test-b1']),
        'b2':dict(parent_id='family-b',is_leaf=True,result_ids=['test-b2'])}
    pairs=worker._field_pairs(context,4)
    index=context['field_index']
    assert len(pairs)==4
    assert all(index[p['source_field_id']]['parent_id'] != index[p['target_field_id']]['parent_id']
               for p in pairs)
    assert len({p['source_field_id'] for p in pairs})==4


def exploratory_idea(idea):
    """ARTIFICIAL lead deliberately has no known bottleneck or target baseline."""
    lead = {k: v for k, v in idea.items() if k not in {
        'target_result_ids', 'adaptation', 'expected_gain', 'required_assumptions',
        'missing_lemmas', 'likely_counterexamples', 'first_falsification_test'}}
    lead.update(maturity='EXPLORATORY_LEAD',
        match_basis=['ARTIFICIAL source operator and target both act on the supplied quadratic form'],
        next_action='Write the source operator on the two-variable target and inspect its domain')
    return lead


def test_focus_technique_finds_unknown_difficulty_without_baseline(tmp_path):
    archive, idea = setup(tmp_path)
    lead = exploratory_idea(idea)
    worker = TransferReview(archive, tmp_path, tmp_path/'sources', Model([lead]))
    report = worker.run(focus_paper_ids=['paper:1'])
    retained = report['ideas'][0]
    assert retained['target_result_ids'] == [] and retained['missing_lemmas'] == []
    assert report['technique_reviews'][0]['outcome'] == 'CANDIDATE'
    text = (tmp_path/'reports/transfers/latest.md').read_text()
    assert 'EXPLORATORY_LEAD' in text and '下一步' in text and '尚未指定' in text
    assert not archive.list('transfer')


@pytest.mark.parametrize('change', ['no_match', 'no_action', 'blank_match', 'fake_evidence',
                                   'source_only_evidence', 'hypothesis_without_details',
                                   'plan_without_bridge', 'plan_without_test'])
def test_exploration_does_not_relax_evidence_or_maturity_gates(tmp_path, change):
    archive, idea = setup(tmp_path)
    lead = exploratory_idea(idea)
    if change == 'no_match':
        lead.pop('match_basis')
    elif change == 'no_action':
        lead.pop('next_action')
    elif change == 'blank_match':
        lead['match_basis'] = [' ']
    elif change == 'fake_evidence':
        lead['evidence_ids'] = ['evidence:1', 'invented']
    elif change == 'source_only_evidence':
        lead['evidence_ids'] = ['evidence:1', 'evidence:1']
    elif change == 'hypothesis_without_details':
        lead['maturity'] = 'TRANSFER_HYPOTHESIS'
    else:
        lead = dict(idea, maturity='VALIDATION_PLAN')
        if change == 'plan_without_test':
            lead.update(bridge_statement='ARTIFICIAL: the target operator is contractive in L2')
            lead.pop('first_falsification_test')
    with pytest.raises(ValueError):
        TransferReview(archive, tmp_path, tmp_path/'sources', Model([lead])).run()
    assert not (tmp_path/'reports/transfers/latest.json').exists()


def test_validation_plan_requires_bridge_and_retains_retry_conditions(tmp_path):
    archive, idea = setup(tmp_path)
    plan = dict(idea, maturity='VALIDATION_PLAN',
        bridge_statement='ARTIFICIAL: the target operator is contractive in the supplied L2 norm',
        next_action='Compute the two-dimensional operator norm',
        revisit_when=['A source extension handles degenerate covariance'])
    report = TransferReview(archive, tmp_path, tmp_path/'sources', Model([plan])).run()
    assert report['ideas'][0]['revisit_when'] == plan['revisit_when']
    assert '桥接命题' in (tmp_path/'reports/transfers/latest.md').read_text()


def test_same_field_and_unattributed_ideas_survive_supplementary_rotation(tmp_path):
    from research_scout.workflows.transfer_review import TransferIdeas
    worker, context, idea, pair = field_context(tmp_path)
    pair['outcome'] = 'NO_SUPPORTED_IDEA'
    context['field_index']['shared'] = dict(is_leaf=True, result_ids=['result:1', 'result:2'])
    idea.update(source_field_id='shared', target_field_id='shared')
    worker._validate(TransferIdeas(ideas=[idea], field_pair_reviews=[pair], limitations=['Test']), context, 3)
    lead = exploratory_idea(idea)
    lead.pop('source_field_id')
    lead.pop('target_field_id')
    worker._validate(TransferIdeas(ideas=[lead], field_pair_reviews=[pair], limitations=['Test']), context, 3)


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'invented', 'false_outcome'])
def test_each_focus_technique_has_honest_review_even_without_candidate(tmp_path, change):
    from research_scout.workflows.transfer_review import TransferIdeas
    worker, context, idea, pair = field_context(tmp_path)
    context['techniques_to_review'] = [dict(source_mechanism_id='mechanism:1', source_result_ids=['result:1'])]
    review = dict(source_mechanism_id='mechanism:1', outcome='CANDIDATE', rationale='ARTIFICIAL match')
    reviews = [review]
    if change == 'missing':
        reviews = []
    elif change == 'duplicate':
        reviews *= 2
    elif change == 'invented':
        review['source_mechanism_id'] = 'invented'
    else:
        review['outcome'] = 'NO_SUPPORTED_IDEA'
    with pytest.raises(ValueError):
        worker._validate(TransferIdeas(ideas=[idea], field_pair_reviews=[pair],
            technique_reviews=reviews, limitations=['Test']), context, 3)


def test_focus_technique_zero_candidates_keeps_attempt_record(tmp_path):
    archive, _ = setup(tmp_path)
    report = TransferReview(archive, tmp_path, tmp_path/'sources', Model([])).run(focus_paper_ids=['paper:1'])
    assert report['ideas'] == []
    assert report['technique_reviews'][0]['source_mechanism_id'] == 'mechanism:1'
    assert report['technique_reviews'][0]['outcome'] == 'NO_SUPPORTED_IDEA'
