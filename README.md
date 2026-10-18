# Research Scout

<p align="center">
  <img src="assets/research-crystallization.webp?v=2x-lossless" alt="Research Scout: flowing evidence glyphs converge into a research note with a smooth blue curve, on a transparent background." width="960" />
</p>

<p align="center"><em>From scattered evidence to a clearer research picture.</em></p>

Research Scout is a local-first scientific knowledge and research discovery system.
It connects **problems → bottlenecks → mechanisms → results**, using papers and
exact source versions as evidence, and preserves how that knowledge changes.

The system complements [Research Harness](https://github.com/LuxLiang/research-harness):
Scout discovers and develops ideas; Harness independently reviews proposals and
executes and verifies research. Their repositories and workspaces stay separate.

## What works

- Typed, versioned records for the Problem Atlas, Bottleneck Registry, Mechanism
  Library, Paper/Result Archive, claims, evidence and qualified relationships.
- Atomic canonical JSON snapshots, retained revisions, append-only events,
  aliases, identity/version deduplication, controlled merge/split and migrations.
- Rebuildable SQLite FTS5, taxonomy filters and graph traversal across domains.
- Scoped problem timelines, conservative result comparison, revision-triggered
  re-review and historical breakthrough analysis with explicit technical deltas.
- Technique-first, problem-first, failure-first and breakthrough-first transfer
  discovery, with missing lemmas, assumptions, counterexamples and falsification.
- Persistent opportunity portfolios, rejected/failed reasoning, six independent
  ranking dimensions and evidence-grounded Research Harness Markdown export.
- arXiv/OpenAlex source adapters; DOI, URL, text and optional PDF ingestion;
  staged structured extraction through a configured model HTTP adapter.

**Source-supported means attributable, not mathematically proven.** Broader
problems stay open when a result needs stronger assumptions. Similar text does
not prove logical implication. Missing models never trigger fabricated summaries.

## Reproduce the offline end-to-end workflow

Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,pdf]'
export SCOUT_WORKSPACE=/tmp/research-scout-demo
scout init
scout import-history
scout search dissipation
scout mechanism mechanism-cross
scout evolution problem-p
scout breakthroughs --result result-c
scout transfer mechanism-cross --target problem-q --mode breakthrough-first
scout demo --output /tmp/scout-proposal.md
scout opportunities
# Copy opportunity_id printed by demo:
scout export OPPORTUNITY_ID --format research-harness --output /tmp/proposal.md
scout index rebuild
scout doctor
scout eval
python -m pytest -q
ruff check src tests
```

The bundled demonstration is explicitly **SYNTHETIC**: A poses P, B makes partial
progress, C changes the mechanism and supports the original scope, Q is retrieved
through a related obstruction, and a transfer hypothesis becomes a persistent
opportunity and proposal. These tests validate software behavior, not science.

Canonical workspaces and source caches are configurable and can live anywhere;
user data is not required inside this repository. Offline knowledge commands need
no API credentials. See [usage](docs/USAGE.md) for live ingestion and model setup.

## Architecture and interfaces

- [Architecture](docs/ARCHITECTURE.md), [scientific data model](docs/DATA_MODEL.md),
  [knowledge evolution](docs/KNOWLEDGE_EVOLUTION.md)
- [Python APIs](docs/API.md), [weekly automation with Codex](docs/AUTOMATION.md),
  [Research Harness handoff](docs/HARNESS_INTEGRATION.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md), [validation and limits](docs/VALIDATION.md)

Optional semantic/vector retrieval, Semantic Scholar and automatic reverse import
from Harness are future extensions. Full logical theorem implication and scientific
correctness verification belong to reviewers and downstream research workflows.

## README animation

An original transparent WebP animation: curved evidence trajectories, a research
card and a continuous loss curve, rendered at 25 fps with a seamless resting loop.
The 1920×1000 lossless asset displays at 960px width for sharp high-DPI text and
fine lines, preserving full alpha transparency.
Concept inspired by [Autonomous Machine Learning Research](https://automlr.com/).
[Static transparent preview](assets/research-crystallization.png).

```bash
python -m pip install -r requirements-animation.txt
python scripts/render_readme_animation.py
```

Animation rendering additionally requires DejaVu fonts at the configurable path
in the script. No website source code or image assets are bundled.
