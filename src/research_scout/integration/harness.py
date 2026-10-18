"""Markdown bridge to Research Harness's actual proposal-review input interface."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from research_scout.domain.models import (
    Bottleneck, Evidence, Mechanism, Opportunity, Paper, PreciseProblem, reference_ids,
)


def proposal_markdown(archive, opportunity_id: str) -> str:
    opportunity = archive.get(opportunity_id)
    if not isinstance(opportunity, Opportunity):
        raise ValueError('export requires an Opportunity ID')
    problem = archive.get(opportunity.target_problem_id)
    if not isinstance(problem, PreciseProblem):
        raise ValueError('opportunity target must be a precise problem')
    bottlenecks = [archive.get(i) for i in opportunity.bottleneck_ids]
    mechanisms = [archive.get(i) for i in opportunity.mechanism_ids]
    if not all(isinstance(b, Bottleneck) for b in bottlenecks):
        raise ValueError('invalid bottleneck reference')
    if not all(isinstance(m, Mechanism) for m in mechanisms):
        raise ValueError('invalid mechanism reference')
    linked: dict = {}
    todo = [opportunity.id]
    while todo:
        rid = todo.pop()
        if rid in linked:
            continue
        record = archive.get(rid)
        linked[rid] = record
        todo.extend(reference_ids(record)-linked.keys())
    evidence = [r for r in linked.values() if isinstance(r, Evidence)]
    papers = [r for r in linked.values() if isinstance(r, Paper)]
    lines = [f'# Research Proposal: {opportunity.title}', '',
        '> SYNTHETIC demonstration. Not genuine scientific findings.' if opportunity.synthetic
        else '> Scout candidate: hypotheses require independent scientific review.', '',
        '## Research question', problem.statement, '',
        '## Closest known literature']
    for paper in papers:
        identifier = paper.doi or paper.arxiv_id or 'fixture / local source'
        lines.append(f'- {paper.title} ({identifier}); archive `{paper.id}`, revision {paper.revision}.')
    lines.extend(['', '## Historical open problem',
        f'{problem.title}: {problem.desired_result}',
        f'Model: {problem.scope.model}. Metric: {problem.scope.metric}.',
        'Original assumptions: '+ '; '.join(problem.scope.assumptions), '', '## Relevant bottleneck'])
    lines.extend(f'- {b.title}: {b.obstruction}. Existing methods: {b.insufficiency}' for b in bottlenecks)
    lines.extend(['', '## Proposed mechanism'])
    lines.extend(f'- {m.title}: {m.construction or m.principle}. Limits: {"; ".join(m.limitations)}' for m in mechanisms)
    lines.extend(['', '## Potential theorem or experiment', opportunity.contribution,
        '', '## Novelty assessment', opportunity.novelty_assessment,
        '', '## Required assumptions'])
    lines.extend(f'- {x}' for x in opportunity.assumptions)
    lines.extend(['', '## Proof obligations'])
    lines.extend(f'- {x}' for x in opportunity.proof_obligations)
    lines.extend(['', '## Risks and counterexamples'])
    lines.extend(f'- {x}' for x in opportunity.counterexamples)
    lines.extend(['', opportunity.uncertainty, '', '## Initial validation plan',
        opportunity.first_validation, '', '## Expected significance', opportunity.significance,
        '', '## Historical progression'])
    for r in sorted(linked.values(), key=lambda r:r.id):
        if r.kind == 'event':
            lines.append(f'- {r.scientific_date}: {r.event_type.value}; {r.rationale} (`{r.id}`).')
    lines.extend(['', '## Separate assessment dimensions'])
    for name, score in opportunity.ranking.items():
        lines.append(f'- {name}: {score.score if score.score is not None else "unassessed"}; {score.rationale}')
    lines.extend(['', '## Evidence and provenance',
        'Source support records attribution; it does not independently prove any theorem.'])
    for e in sorted(evidence, key=lambda r:r.id):
        lines.append(f'- `{e.id}`: paper `{e.paper_id}`, exact version `{e.version_id}`, '
                     f'locator **{e.locator}**, coverage `{e.coverage.value}`; hash `{e.source_hash or "unavailable"}`.')
    lines.extend(['', '## Pinned Scout records',
        'Each hash covers the canonical JSON serialization below the data-model contract.'])
    for r in sorted(linked.values(), key=lambda r:r.id):
        data = json.dumps(r.model_dump(mode='json'),sort_keys=True,ensure_ascii=False,separators=(',',':'))
        digest = hashlib.sha256(data.encode()).hexdigest()
        lines.append(f'- `{r.id}` revision {r.revision}: sha256 `{digest}`')
    lines.extend(['', '## Research Harness handoff',
        'Import this Markdown using the independent proposal-review workflow:', '', '```bash',
        'research --workspace /path/to/harness-workspace init scout-review --runtime cordis \\',
        '  --mode proposal-review --proposal /absolute/path/to/this-proposal.md', '```',
        'Scout does not mark this proposal approved or perform Harness scientific verification.', ''])
    return '\n'.join(lines)


def export_proposal(archive, opportunity_id: str, output: str | Path) -> Path:
    text = proposal_markdown(archive, opportunity_id)
    path = Path(output).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.scout-proposal-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path
