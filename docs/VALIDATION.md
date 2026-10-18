# Validation and completion audit — 2026-10-18

## Executed results

- `python -m pytest -q`: **91 passed**, 51.11 seconds, Python 3.11.
- `ruff check src tests`: **passed**.
- `scout eval`: **14 passed, 0 failed** in an isolated synthetic workspace.
- `python -m pip install -e '.[dev,pdf]'`: **installed successfully**.
- `python -m build --wheel --no-isolation`: **wheel built successfully**.
- Installed the final wheel into a separate virtual environment and ran from
  `/tmp`, outside the source checkout. Initialization, synthetic demo, doctor,
  index rebuild and all 14 packaged evaluations **passed**. The earlier full
  wheel smoke also exercised search, mechanism/evolution lookup, breakthroughs,
  transfer, opportunities and export.
- Actual sibling Harness `import_proposal_resources` accepted the exported
  Markdown and indexed **18 sections** in a temporary Harness workspace. The
  original Harness repository remained unchanged.
- Genuine network metadata smoke: arXiv `1704.04289v1` returned *Stochastic
  Gradient Descent as Approximate Bayesian Inference*, coverage ABSTRACT_ONLY;
  OpenAlex DOI `10.1038/nature14539` returned *Deep learning*, coverage METADATA_ONLY.
  Neither was represented as full-text scientific extraction.

## Requirements mapped to evidence

| Required capability | Implementation and observed verification |
| --- | --- |
| Installable package and CLI | pyproject entry point; installed editable and wheel CLI smoke; test_workflows |
| Typed, versioned knowledge entities | domain/models.py; strict round-trip, unknown fields/schema and timezone tests |
| Topic/family/precise problem scopes | PreciseProblem + Scope; nonblank dimensions; missing quantifiers cannot close problems |
| Reusable bottlenecks and mechanisms | Bottleneck, MechanismFamily/Mechanism/Variant/Application; exact construction reuse across domains |
| Source identity and paper versions | Paper/PaperVersion; DOI/arXiv aliases, content hashes, source enrichment and reverse revision ingestion tests |
| Attributable evidence and claims | Evidence + ScientificClaim; exact extraction text spans, source/version/hash/coverage and review gates |
| Qualified typed relationships | Relationship + storage endpoint validation and atomic missing-reference rejection |
| Persistent canonical archive | JSON snapshots, CURRENT pointer, file lock, revision history/audit; crash and concurrent-writer tests |
| Deduplication, merges, splits, migration | Archive APIs; alias integrity and atomic rollback tests; migrations target installed v1.0 parser |
| Hybrid retrieval and rebuild | FTS5, taxonomy, graph traversal, explicit optional adapters; corrupt/deleted index recovery tests |
| Immutable evolution and derived timelines | EventStore + ProblemEvolutionTimeline; A/B/C, replay, as-of and recording-time tests |
| Scoped resolution | Exact formulation/conjunction comparison; stronger assumptions conditional, changed model/metric incomparable, author/abstract claims unverified |
| Revision review | flag_version_review plus intrinsic source supersession; direct events without cached assessments and late-created assessments tested |
| Breakthrough workflow | Prior attempts/results/mechanisms, source technical delta and related open Q; future results excluded from historical reconstruction |
| Four transfer discovery modes | TransferDiscovery; structure-based candidates, obligations, differences, counterexamples and first falsification test |
| Retained failed transfer knowledge | Atomic transfer failure, mechanism/bottleneck attempts, linked opportunity blocking and failure-first retry tests |
| Incremental paper processing | ScoutController + staged PaperPipeline + LiteratureDelta; extraction triggers breakthrough/transfer/opportunity analysis without promotion |
| Genuine source and model adapters | Real arXiv/OpenAlex smoke; model HTTP adapter tests with mock transport, explicit missing-configuration failures |
| PDF and partial-text handling | Generated real text PDF extraction/hash tests, unreadable PDF rejection and mixed-page PARTIAL_TEXT tests |
| Opportunity portfolio | Lifecycle/history/rejection retention, six evidence-qualified dimensions and raw archive transition-bypass tests |
| Harness integration | Evidence-grounded Markdown export, actual importer acceptance; future reverse-import contract documented |
| Reproducible end-to-end example | scout import-history/demo/eval, examples/offline_demo.py, docs/USAGE.md; idempotence and CLI tests |

## Scientific integrity scenarios

The fixtures exercise all ten requested scenarios: shared mechanisms; A→B→C
history; conditional resolution; decisive mechanism delta; cross-domain Q;
failed transfer; revised theorem; repeated ingestion; missing evidence; index
rebuild. Additional tests cover merge/alias integrity, missing references,
schema round-trip, partial ingestion, offline commands and invalid transitions.

Independent follow-up review found and fixed: source revisions escaping cached
review invalidation, future results leaking into prior history, and admissible
subclass counterexamples failing to challenge a universal guarantee. Regression
tests now cover each, including mismatched witness scope and historical replay.

## Boundaries and future extensions

These are **software integrity results on explicitly synthetic scientific
records**, not proof of theorem truth, novelty or complete literature coverage.
The HTTP model adapter is implemented and mocked in tests; no real model-backed
scientific extraction was run because no model credentials were supplied.
Live metadata connections were tested separately as reported above.

Logical implication between nonidentical assumptions/guarantees requires proof
obligations. Manual ranking dimensions are unassessed until evidence and rationale
are supplied. Local text/HTML is conservatively PARTIAL_TEXT; unreadable PDFs
need external OCR. Full text analysis must not be inferred from abstracts.

Semantic retrieval and external novelty expansion expose extension protocols;
there is no bundled vector model/database or automated scientific novelty oracle.
Semantic Scholar and automatic Harness reverse import remain future extensions.
The reverse-import envelope is documented; it is not silently treated as implemented.
Migrations transform records into the installed schema; unknown future schema
versions require a new parser instead of an unsafe automatic conversion.
