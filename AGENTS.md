# Research Scout engineering contracts

Use Python 3.11+, Pydantic v2, Typer, SQLite FTS5. Canonical records are UTF-8
JSON (a YAML-compatible representation), independent of the SQLite projection.
Read docs/ARCHITECTURE.md, DATA_MODEL.md and domain/interfaces.py before editing.
Root owns shared domain contracts, CLI, integration, workflow and final QA.
Delegated ownership is disjoint; request shared model changes from root.
Never alter the sibling research-harness repository.

Scientific invariants: evidence locators must be supplied, never invented;
author claims do not imply independent verification; stronger assumptions do
not solve unrestricted problems; unknown logical implication stays unknown;
append-only events and paper versions survive correction, merge and split.
Synthetic fixtures must be prominently labeled. Missing model configuration
must fail explicitly, never silently produce fixture extraction.

Run pytest and ruff check src tests. Use meaningful adversarial tests for changes
in scientific gates or persistence. Keep the transparent README animation.
User explicitly authorizes committing and pushing completed work to GitHub.
Use actual subagents for the independent modules defined in implementation plan.
