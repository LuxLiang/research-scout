"""Adversarial theory-candidate tests with explicitly artificial unit-test sources."""
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from research_scout.discovery import SourcePaper
from research_scout.domain.models import Evidence, Mechanism, Paper, PaperVersion, Result, Scope
from research_scout.storage import Archive
from research_scout.workflows.gaps import TheoryGapReview


def setup(tmp_path):
    archive = Archive(tmp_path / 'knowledge')
    scope = Scope(domain='unit-test only', model='test kinetic model', objective='test source bound',
                  metric='test distance', guarantee='source guarantee', quantifiers=['all test inputs'])
    rows = []
    for n in (1, 2):
        text = tmp_path / f'{n}.txt'
        text.write_text('UNIT TEST SOURCE EVIDENCE')
        rows.extend([
            Paper(id=f'paper:{n}', title=f'ARTIFICIAL UNIT TEST SOURCE {n}',
                  version_ids=[f'version:{n}'], extraction_status='EXTRACTED'),
            PaperVersion(id=f'version:{n}', title='Test v1', paper_id=f'paper:{n}',
                         version='v1', text_path=str(text), coverage='FULL_TEXT'),
            Evidence(id=f'evidence:{n}', title='Test evidence', paper_id=f'paper:{n}',
                     version_id=f'version:{n}', locator='char:0-25',
                     quotation='UNIT TEST SOURCE EVIDENCE', coverage='FULL_TEXT'),
            Mechanism(id=f'mechanism:{n}', title='Test method', principle='Test only', evidence_ids=[f'evidence:{n}']),
            Result(id=f'result:{n}', title='Test result', paper_id=f'paper:{n}', version_id=f'version:{n}',
                   result_type='THEOREM', statement='Artificial source result', scope=scope,
                   evidence_ids=[f'evidence:{n}']),
        ])
    archive.put_many(rows)
    card = dict(title='UNIT TEST research candidate', research_question='Test a different uniform guarantee.',
        target_scope=scope.model_copy(update={'guarantee':'new unproved uniform bound'}).model_dump(mode='json'),
        source_paper_ids=['paper:1','paper:2'], evidence_ids=['evidence:1','evidence:2'],
        mechanism_ids=['mechanism:1'], closest_result_ids=['result:1','result:2'],
        obstruction='Test missing local stability', why_existing_results_insufficient='The test source bounds differ.',
        missing_lemmas=['Prove uniform coordinate moments'],
        first_falsification_test='Check a two-variable artificial example',
        failure_conditions=['The required uniform moment can fail'],
        prior_art_queries=['all:"test kinetic sampling"'], novelty='UNDETERMINED')
    return archive, card


class Model:
    def __init__(self, cards, excluded=None):
        self.cards, self.excluded, self.calls = cards, excluded or [], 0

    def run_structured(self, prompt, schema):
        self.calls += 1
        assert 'not a literature gap' in prompt
        assert 'untrusted data' in prompt
        assert schema['additionalProperties'] is False
        return {'batch_json': json.dumps({'proposals':self.cards, 'excluded_ideas':self.excluded,
                                         'limitations':['Unit-test-only source scope']})}


class Sources:
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def search(self, *args, **kwargs):
        self.calls += 1
        if self.fail:
            raise RuntimeError('test retrieval failure')
        return [SourcePaper(title='Artificial related metadata', arxiv_id='2610.99999',version='v1',
                            abstract='Unit-test-only related abstract', coverage='ABSTRACT_ONLY')]


def test_real_references_hypothesis_only_and_repeat_is_cached(tmp_path):
    archive, card = setup(tmp_path)
    model, sources = Model([card]), Sources()
    worker = TheoryGapReview(archive,tmp_path,tmp_path/'sources',model,sources)
    result = worker.run()
    opportunity = archive.get(result['cards'][0]['opportunity_id'])
    assert opportunity.status == 'HYPOTHESIS'
    assert all(d.score is None for d in opportunity.ranking.values())
    assert 'UNDETERMINED' in opportunity.novelty_assessment
    assert opportunity.proof_obligations and opportunity.first_validation
    assert len(archive.list('bottleneck')) == 1
    assert archive.list('bottleneck')[0].status == 'HYPOTHESIZED_BOTTLENECK'
    assert not archive.validate()
    assert result['cards'][0]['external_matches'][0]['coverage'] == 'ABSTRACT_ONLY'
    assert worker.run() == result
    assert model.calls == sources.calls == 1
    assert len(archive.list('opportunity')) == 1
    assert (tmp_path/'reports/gaps/latest.md').is_file()


@pytest.mark.parametrize('field,value', [
    ('source_paper_ids',['paper:1','paper:1']),
    ('source_paper_ids',['paper:1','paper:missing']),
    ('evidence_ids',['evidence:1','missing']),
    ('evidence_ids',['evidence:1','evidence:1']),
    ('mechanism_ids',['result:1']),
    ('closest_result_ids',['evidence:1']),
    ('novelty','CONFIRMED_NEW'),
    ('missing_lemmas',[' ']),
])
def test_invalid_second_card_cannot_partially_publish_first(tmp_path,field,value):
    archive, card = setup(tmp_path)
    model = Model([card,{**card,field:value}])
    with pytest.raises(ValueError):
        TheoryGapReview(archive,tmp_path,tmp_path/'sources',model,Sources()).run()
    assert not archive.list('opportunity')
    assert not archive.list('bottleneck')


def test_missing_target_quantifiers_cannot_be_called_theory_question(tmp_path):
    archive, card = setup(tmp_path)
    card['target_scope']['quantifiers'] = []
    with pytest.raises(ValueError,match='quantifiers'):
        TheoryGapReview(archive,tmp_path,tmp_path/'sources',Model([card]),Sources()).run()


def test_failed_external_search_is_not_reported_as_successful_empty_novelty(tmp_path):
    archive, card = setup(tmp_path)
    report = TheoryGapReview(archive,tmp_path,tmp_path/'sources',Model([card]),Sources(fail=True)).run()
    item = report['cards'][0]
    assert item['external_searched'] and item['external_errors']
    assert item['novelty'] == 'UNDETERMINED'
    assert '1 query failures' in archive.get(item['opportunity_id']).novelty_assessment


def test_incomplete_external_search_retries_without_repeating_model_call(tmp_path):
    archive, card = setup(tmp_path)
    model, sources = Model([card]), Sources(fail=True)
    worker = TheoryGapReview(archive,tmp_path,tmp_path/'sources',model,sources)
    assert worker.run()['cards'][0]['external_errors']
    sources.fail = False
    assert not worker.run()['cards'][0]['external_errors']
    assert sources.calls == 2 and model.calls == 1


def test_empty_review_can_exclude_supported_old_idea_without_inventing_gap(tmp_path):
    archive, _ = setup(tmp_path)
    model = Model([], [dict(idea='Already covered',reason='Test source covers it',evidence_ids=['evidence:1'])])
    report = TheoryGapReview(archive,tmp_path,tmp_path/'sources',model,Sources()).run(external=False)
    assert not report['cards'] and report['excluded_ideas']
    assert not archive.list('opportunity')


def test_exclusions_cannot_invent_prior_art_url(tmp_path):
    archive, _ = setup(tmp_path)
    model = Model([], [dict(idea='Old',reason='Untrusted',prior_art_urls=['https://invented.test'])])
    with pytest.raises(ValueError,match='outside supplied prior art'):
        TheoryGapReview(archive,tmp_path,tmp_path/'sources',model,Sources()).run(external=False)


def test_week_old_review_refreshes_search_without_another_model_call_or_promotion(tmp_path):
    archive, card = setup(tmp_path)
    model, sources = Model([card]), Sources()
    worker = TheoryGapReview(archive,tmp_path,tmp_path/'sources',model,sources)
    original = worker.run()
    report_file = tmp_path/'reports/gaps'/f"{original['input_fingerprint']}.json"
    original['recorded_at'] = (datetime.now(ZoneInfo('Asia/Shanghai'))-timedelta(days=8)).isoformat()
    report_file.write_text(json.dumps(original))
    worker.run()
    assert sources.calls == 2 and model.calls == 1
    assert len(archive.list('opportunity')) == 1
    assert archive.list('opportunity')[0].status == 'HYPOTHESIS'
    assert archive.list('opportunity')[0].history[-1]['action'] == 'GAP_PRIOR_ART_REFRESH'


def test_cached_or_refreshed_review_never_reopens_rejected_opportunity(tmp_path):
    from research_scout.opportunities import OpportunityPortfolio
    archive, card = setup(tmp_path)
    model, sources = Model([card]), Sources()
    worker = TheoryGapReview(archive,tmp_path,tmp_path/'sources',model,sources)
    first = worker.run(external=False)
    oid = first['cards'][0]['opportunity_id']
    OpportunityPortfolio(archive).transition(oid,'REJECTED','Artificial reason: source already covers it')
    assert worker.run(external=False)['cards'][0]['status'] == 'REJECTED'
    assert worker.run(external=False,refresh=True)['cards'][0]['status'] == 'REJECTED'
    assert archive.get(oid).rejection_reason
    assert sources.calls == 0 and model.calls == 2


def test_same_structured_scope_is_flagged_instead_of_assumed_novel(tmp_path):
    archive, card = setup(tmp_path)
    card['target_scope'] = archive.get('result:1').scope.model_dump(mode='json')
    report = TheoryGapReview(archive,tmp_path,tmp_path/'sources',Model([card]),Sources()).run(external=False)
    assert set(report['cards'][0]['exact_scope_result_ids']) == {'result:1','result:2'}
    opp = archive.get(report['cards'][0]['opportunity_id'])
    assert 'same structured scope already exist' in opp.novelty_assessment
    assert 'UNDETERMINED' in opp.novelty_assessment


def test_unconfigured_backend_or_insufficient_sources_fail_explicitly(tmp_path):
    archive, _ = setup(tmp_path)
    with pytest.raises(ValueError,match='Codex structured backend'):
        TheoryGapReview(archive,tmp_path,tmp_path/'sources',object()).run()
    empty = Archive(tmp_path/'empty')
    with pytest.raises(ValueError,match='two extracted papers'):
        TheoryGapReview(empty,tmp_path,tmp_path/'sources',object()).run()


def test_weekly_includes_review_link_and_reports_failures(tmp_path,monkeypatch):
    from research_scout.workflows.weekly import WeeklyCollector, WeeklyProfile
    archive, _ = setup(tmp_path)
    worker = WeeklyCollector(archive,tmp_path,tmp_path/'sources',provider=object(),
                             arxiv=SimpleNamespace(search=lambda *a,**k:[]))
    profile = WeeklyProfile(name='test',arxiv_queries=['all:test'],theory_gap_review=True)
    monkeypatch.setattr(TheoryGapReview,'run',lambda self,n:dict(cards=[{}]))
    result = worker.run(profile)
    assert result['theory_gap_review']['candidate_count'] == 1
    assert 'gaps/latest.md' in (tmp_path/'reports/latest.md').read_text()
    def fail(*args):
        raise RuntimeError('test review failure')
    monkeypatch.setattr(TheoryGapReview,'run',fail)
    result = worker.run(profile)
    assert result['errors'][0]['stage'] == 'theory_gap_review'
    assert not result.get('theory_gap_review')
