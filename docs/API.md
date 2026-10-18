# Programmatic interfaces

The CLI composes the same APIs. `domain/models.py` defines strict versioned
Pydantic records; `domain/interfaces.py` defines archive/extraction protocols.

```python
from pathlib import Path
from research_scout.storage import Archive
from research_scout.workflows.demo import run_demo

archive = Archive(Path('/tmp/scout-api/knowledge'))
report = run_demo(archive, '/tmp/scout-api/proposal.md')  # explicit synthetic data
print(report)
```

Archive supports `get`, `list`, `put`, atomic `put_many`, `history`, `audit`,
`validate`, `search`, `traverse`, `rebuild`, `find_paper`, `resolve_id`, `merge`,
`split` and `migrate`. Mutable updates require the current record revision;
`put` auto-increments and returns the new record. Use the returned record for
subsequent edits. Duplicate unchanged content is idempotent. Immutable Evidence,
PaperVersion, EvolutionEvent and EntityChange require new IDs for corrections.
`Archive(root, index_path=...)` separates canonical storage and search projection.

`evolution.assess_resolution(archive, problem_id, result_id)` returns a qualified
scope comparison. `EventStore.append(event)` validates immutable history.
`ProblemEvolutionTimeline(archive, problem_id).build(as_of=DATE,
recorded_before=DATETIME)` reconstructs scientific history and recording-time
knowledge. New sources trigger `flag_version_review(archive, old_id, new_id)`.

`BreakthroughDiscovery(archive).analyze(result_id)` retrieves historical attempts,
exact technical delta and analogous open problems. `TransferDiscovery.propose`
and `.discover` implement the four modes; `.record_failure` persistently records
negative knowledge and blocks linked opportunities atomically.

```python
from research_scout.transfer import TransferDiscovery
from research_scout.opportunities import OpportunityPortfolio

transfer = TransferDiscovery(archive).propose('mechanism-cross', 'problem-q')
portfolio = OpportunityPortfolio(archive)
opportunity = portfolio.from_transfer(transfer.id)
portfolio.assess_dimension(opportunity.id, 'feasibility', None,
                           'The delay commutator remains unproved.')
```

`NoveltyAudit` accepts an optional `PriorArtAdapter` protocol. It always reports
retrieval limitations. `OpportunityPortfolio.transition` validates lifecycle;
`rank(dimension=...)` sorts one explicit assessment dimension, never an invented
aggregate. Six dimensions remain unassessed until evidence/rationale is supplied.

`PaperIngestor(archive, cache_dir).ingest(source)` handles source-only ingestion.
`PaperPipeline(..., provider=...).process(source)` validates staged extraction.
`ScoutController(...).process(source)` additionally triggers breakthrough,
transfer and opportunity discovery and reports downstream analysis errors.
`OpenAICompatibleProvider` runs real configured model HTTP calls; `FixtureProvider`
is explicitly synthetic only. Exact Unicode text offsets anchor extracted evidence.
`ArxivClient` and `OpenAlexClient` expose genuine metadata/citation adapters.

`integration.export_proposal(archive, opportunity_id, path)` writes Markdown
accepted by Harness's proposal-review input, without importing Harness or
changing its repository. Reverse import is a documented future contract.
