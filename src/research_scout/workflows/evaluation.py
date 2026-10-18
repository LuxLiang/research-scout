"""Deterministic, synthetic software-integrity checks; no scientific validity claim."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from research_scout.domain.models import (
    AssessmentStatus, ClaimOrigin, Coverage, PaperVersion, ScientificClaim,
)
from research_scout.storage import Archive
from .demo import run_demo


def run_evaluation():
    checks=[]
    def check(name,condition):
        checks.append({'scenario':name,'passed':bool(condition)})
    with TemporaryDirectory(prefix='scout-synthetic-eval-') as tmp:
        archive=Archive(Path(tmp)/'knowledge')
        report=run_demo(archive,Path(tmp)/'proposal.md')
        from research_scout.evolution import ProblemEvolutionTimeline, flag_version_review
        from .demo import import_history
        timeline=ProblemEvolutionTimeline(archive,'problem-p').build()
        transfer=archive.get(report['transfer_id'])
        check('mechanism reuse and explicit application', len(archive.list('application'))==2 and
              archive.get('application-c').mechanism_id=='mechanism-cross')
        check('three-stage history retained', {'event-posed','event-partial','event-result'} <= {e.id for e in timeline.events})
        check('scoped source-supported resolution',timeline.status.value=='RESOLVED_SUPPORTED')
        check('stronger assumptions conditional',report['partial_resolution']=='CONDITIONAL_RESOLUTION')
        breakthrough=archive.get(report['breakthrough_id'])
        check('technical delta retained','mixed term' in breakthrough.technical_delta and 'mechanism-diagonal' in breakthrough.previous_mechanisms)
        check('cross-domain target retrieved','problem-q' in breakthrough.analogous_problem_ids)
        check('transfer has falsification and obligations',bool(transfer.missing_lemmas and transfer.first_falsification_test and transfer.uncertainty))
        count=len(archive.list())
        import_history(archive)
        check('repeated history import idempotent',len(archive.list())==count)
        before={r.id:r.model_dump(mode='json') for r in archive.list()}
        archive.rebuild()
        check('rebuild retains canonical graph',before=={r.id:r.model_dump(mode='json') for r in archive.list()})
        check('proposal contains evidence and synthetic label','SYNTHETIC' in (Path(tmp)/'proposal.md').read_text() and '## Evidence and provenance' in (Path(tmp)/'proposal.md').read_text())
        rejected=False
        try:
            archive.put(ScientificClaim(id='unsupported-review',title='Unsupported',content='Solved',
                origin=ClaimOrigin.SYSTEM_INFERENCE,version_id='version-c-1',
                assessment_status=AssessmentStatus.INDEPENDENTLY_REVIEWED))
        except ValueError:
            rejected=True
        check('unsupported independent verification rejected',rejected)
        from research_scout.transfer import TransferDiscovery
        from research_scout.opportunities import OpportunityPortfolio
        failed=TransferDiscovery(archive).record_failure(transfer.id,
            'SYNTHETIC energy construction fails on the tested augmented system',
            evidence_ids=['evidence-q-failure'])
        check('failed transfer retained with reason',archive.get(failed.id).outcome=='FAILED'
              and bool(archive.get(failed.id).failure_reason))
        rejected_transition=False
        try:
            OpportunityPortfolio(archive).transition(report['opportunity_id'],'PROPOSAL_READY',
                'Attempt an invalid shortcut')
        except ValueError:
            rejected_transition=True
        check('invalid portfolio transition rejected',rejected_transition)
        old=archive.get('version-c-1')
        version=PaperVersion(id='version-c-2',title='SYNTHETIC C revised',paper_id='paper-c',
            version='2',coverage=Coverage.FULL_TEXT,content_hash='synthetic-v2',
            supersedes_version_id=old.id,synthetic=True)
        paper=archive.get('paper-c').model_copy(update={'version_ids':['version-c-1','version-c-2']})
        archive.put_many([paper,version])
        affected=flag_version_review(archive,old.id,version.id)
        stale=ProblemEvolutionTimeline(archive,'problem-p').build()
        check('new version triggers re-review',bool(affected) and stale.requires_review and stale.status.value!='RESOLVED_SUPPORTED')
    return {'synthetic':True,'scientific_correctness_verified':False,
        'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'checks':checks}
