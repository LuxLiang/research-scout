# Architecture

Scout primarily maintains research-field dossiers and source-supported related work.
Discovery and idea formation are optional workflows. Research Harness independently owns
proposal review, research execution and verification. Its inspected interface
accepts Markdown or text-extractable PDF via `research init <project> --mode
proposal-review --proposal PATH`. Scout exports Markdown; it does not write
Harness artifacts or alter that repository.

Scientific graph: Problem → limited by Bottleneck ← addressed by Mechanism →
establishes Result. Papers and exact versions provide Evidence and attributable
Claims. Four independent navigable projections expose the Problem Atlas,
Bottleneck Registry, Mechanism Library and Result/Evolution Graph.

Canonical UTF-8 JSON records and retained revisions are the source of truth.
A single-writer file lock and atomic batch publication prevent partial graph
updates. SQLite FTS5 is a disposable projection. Stable IDs do not encode file
paths; aliases and explicit merge/split records preserve historical references.
Sources and extracted text live in configurable caches outside code.

Each workflow retrieves history before proposing records. Structured extraction
is staged and validated before canonical promotion. Unknown comparisons retain
proof obligations. New paper versions preserve the old version and flag dependent
assessments for review. Append-only evolution events are never corrected in place.
Timelines derive scoped state, never mutable global solved flags on topics.

Offline fixtures are explicitly synthetic. Live source adapters and configured
model adapters fail visibly on missing configuration or network errors. No fake
fallback. Attribution validation does not prove mathematical correctness.

Field dossiers are versioned projections in `fields/`, configured by `fields.json`.
They retain the full matching result history, exact source/evidence references,
optional source-pinned result notes, conservative setting comparisons and input
change records. Their readable related work is backed by structured records;
stale prose is marked while result tables can update offline. Field membership
and thematic branches do not change canonical scientific scope or status.

Theory-gap review defaults to all extracted papers' structured records and
evidence, matching the related-work source range. Context/model failures remain
explicit; there is no automatic fallback to a recent-paper subset.

Research development is recorded as typed, content-fingerprinted reviews appended
to Opportunity history. Findings separate conditional derivations, counterexample
derivations, numerical diagnostics and prior-art review. Workspace-relative
artifacts are checked against their hashes before publication. These entries do
not promote scientific status or replace paper Evidence. Later gap prompts and
Harness exports carry the retained refinements, including downranked scopes.
