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
For the original release, the HTTP model adapter was mocked and no real model-backed
scientific extraction was run. The later Codex extension and live smoke are recorded
in the follow-up section below.
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

## Weekly collection and Codex follow-up

Added a saved-login `CodexExecProvider`, bounded weekly collection, matched-topic
classification, persistent retry/overflow queue, local Markdown/JSON reports and
an idempotent user cron installer. Follow-up execution: **122 pytest tests passed
in 57.96 seconds**, including mocked subprocess, source failure/retry, version reuse,
selection limits, pending-only resumption, cached PDF/text reuse, concurrent-run lock
and preservation of unrelated cron entries.
Ruff passes. A real ChatGPT-authenticated Codex smoke extracted an Evidence and
Claim from a short explicitly synthetic source, reported missing theorem/proof
information, and required no API key. The exact-quote anchoring hardening separately
passed **22 provider tests**. The wheel builds with the new modules.

This extends the original HTTP-backend validation above: HTTP calls remain mocked;
Codex saved-login execution has now been exercised. Genuine full-paper processing
is an operational corpus run, not proof that its scientific extraction is correct.

## Source-segment extraction follow-up

The first genuine full-paper attempt was rejected because a model quotation was
absent or ambiguous in the PDF-extracted text. No scientific records were published.
The Codex backend now provides a complete indexed source and accepts an explicit
segment selection. Original text and character spans are copied deterministically;
invalid segment IDs or conflicting quotations fail. Legacy exact quotations remain
supported. The backend retains the last structured model envelope in memory for
callers to checkpoint rejected outputs without retaining CLI diagnostics.

Follow-up verification: **132 tests passed in 46.71 seconds**. Ten added tests
cover complete Unicode/long-line source segmentation, exact source-segment copying,
invalid IDs, negative/noncanonical IDs, conflicting quotations, retained rejected
envelopes and strict normalization of an explicit non-verification synonym.
Verified statuses remain rejected by the pipeline. This validates
source anchoring, not the mathematical interpretation of model-selected passages.

The operational bootstrap subsequently saved ten distinct PDF/text sources and
completed ten real ChatGPT-authenticated Codex first-pass extractions. The local
corpus contains ten precise problems, ten mechanisms, nineteen results, twenty
claims and sixty-one evidence records. Every PDF hash and every evidence
quotation/character span was checked against the corresponding cached source;
archive integrity checks passed. A transient download timeout was retried, and
one explicit non-verification synonym was normalized with provenance retained.
The corpus and its reports are outside the package checkout. These are successful
source-attributed extractions, not independent mathematical verification.

## Theory-first gap review

Added `scout gaps` and optional weekly theory review with typed hypotheses,
two-paper evidence requirements, explicit target quantifiers, closest results,
proof obligations, falsification tests, prior-art queries and retained exclusions.
The stage creates proposed problems, hypothesized bottlenecks and HYPOTHESIS
opportunities; it never confirms novelty or assigns numerical rankings.

Executed **151 tests in 59.08 seconds**, with Ruff and wheel build passing.
Nineteen added adversarial cases cover fabricated references, incomplete source
coverage, missing quantifiers, false novelty labels, blank proof obligations,
validation-before-publication, unsupported exclusion URLs, external failures and
retry, cache reuse, same-scope prior results, rejection retention and weekly
report/error integration. The original Codex boundary tests also pass after
factoring its saved-login structured task runner.

A real ten-paper review produced **two theoretical candidates and eight excluded
or deferred ideas**, with explicit arXiv search records. Supplementary primary-source
checks found related high-temperature marginal-error work for the discrete
candidate. This was retained as a prior-art warning, not converted into either a
novelty confirmation or an unsupported assertion of theorem equivalence. Both
opportunities remain HYPOTHESIS with UNDETERMINED novelty. Actual review artifacts
and source snapshots are in the independent local library. Archive validation
passes with the two new proposed problems, hypothesized bottlenecks and opportunities.

## Related work before gap discovery

Added `scout related-work`, connected problem-driven prose, a source comparison
matrix, bibliography observations, a citation/thematic graph and prioritized
missing foundations. Every cited archived paper needs its own existing evidence;
external metadata cannot promote itself to full-text coverage. Bibliography title
matches retain exact source spans. Citation is distinguished from thematic
comparison, and neither asserts a proved technical improvement. Narrative output
does not mutate scientific statuses or create opportunities.

Twelve added tests cover source/evidence ownership, complete matrix coverage,
fabricated citation edges, metadata coverage, cache reuse, downstream foundation
URLs, workflow ordering and blocking gap generation after a history-stage failure.
The final suite passes **163 tests**; Ruff and wheel build pass.

The real ten-paper library produced **four development tracks, ten comparison
rows and eight citation/thematic relations**, drawing on ten archived papers and
seven separately labeled metadata sources. The report indexes 59 existing source
evidence records; ten positive bibliography observations were available to the
writer. Five foundational metadata records were verified from primary sources;
this task did not download additional full papers. The library still contains ten
PDFs, and archive validation passes. Existing opportunities remain hypotheses.
This is a source-supported first draft, not a complete related-work search or an
independent check of the cited proofs. Weekly automation now updates this context
before generating theoretical gap candidates when enabled.

## Field maintenance as the primary workflow — 2026-10-19

Added validated field/branch registries, offline result-level dossiers, optional
own-version evidence-pinned result notes, conservative setting comparisons and
parent-linked immutable snapshots. The result table distinguishes theorem,
algorithmic and empirical records; unknown cost/oracle details remain unknown.
Dossiers retain all matching results, while source-supported prose considers all
extracted papers rather than silently dropping old sources after twenty papers.
Model-written prose receives the prior draft as editorial context for incremental
revision, without treating previous narrative as scientific evidence.

The final suite passes **214 tests in 60.77 seconds**; Ruff and wheel build pass.
New checks cover multi-field reuse, exact/inexact result separation, explicit
branch-only membership, unchanged-input reuse, per-invocation deltas, source
revision flags, conservative lower evidence coverage, stale result notes,
wrong-owner evidence, invalid registries, retained A→B→A snapshots, interrupted
publication recovery, cross-field narrative dependencies, historical source
retention, CLI operation without a model, weekly stage order and explicit
suppression of automated hypotheses. Comparison tests cover metrics, model,
assumptions, quantifiers, unexpanded numbered assumptions, mathematical case,
empirical/theory separation and immutable inputs; rate ordering remains
UNASSESSED.

The genuine independent library now has four field dossiers covering **21 unique
results across 11 full papers**: Langevin/high-accuracy sampling 12, SGHMC 2,
SFS 5 and discrete sampling 2. Seven source-reading annotations distinguish
oracle access, initialization and scoped operation counts. All 70 cached evidence
spans/quotations and PDF hashes were checked again; archive validation passes.
Field updates leave canonical records unchanged, retain the two existing
hypotheses, and produce no new revision or repeated additions on a no-op run.
The actual weekly profile now maintains related work and dossiers, with both
automatic discovery and theory-gap generation disabled. These checks establish
attribution and software behavior, not independent theorem verification.

The final wheel was also installed into a separate virtual environment and run
from `/tmp`, outside the checkout. Workspace initialization, field configuration,
offline dossier update and Markdown display all passed using the installed wheel.

## Full-corpus gap context and retained research reviews — 2026-10-19

Gap generation now defaults to every extracted paper's structured records and
evidence, matching related-work coverage. Explicit bounded inspection is labeled
accurately; model/context failures do not retry with a silently truncated corpus.
Regressions exercise more than twenty sources, earliest-paper evidence, old-result
cache invalidation and failure behavior.

Typed research reviews retain scoped conditional derivations, counterexample
derivations, diagnostics, prior-art findings and workspace artifact SHA-256 pins
in append-only Opportunity history. Imports validate all artifacts and references
before writing, are idempotent, and cannot promote novelty, verification,
lifecycle status or numerical ranking. Later gap inputs/cache fingerprints and
Harness exports include the retained refinements. Re-parsing prevents unvalidated
Pydantic model copies from bypassing review gates.

Executed **244 tests in 105.70 seconds**; Ruff and wheel build passed. Adversarial
checks cover forged hashes, traversal, absolute paths, symlink escape, invalid
references, atomic rejection, retained-history tampering, model-copy bypass,
CLI import/read, export and review-triggered gap cache invalidation.

In the real independent workspace, offline context contains **67 extracted papers,
130 results and 590 evidence records**. SFS and discrete candidates each received
one structured review; original history prefixes and revisions were retained.
Repeated import leaves revisions unchanged. Their lifecycle remains HYPOTHESIS,
novelty remains UNDETERMINED and all six numerical ranks remain unchanged. Archive
validation passed. This validates persistence, coverage and attribution controls;
it does not certify the research derivations or their novelty. No new model-backed
gap batch was generated for this maintenance operation.
