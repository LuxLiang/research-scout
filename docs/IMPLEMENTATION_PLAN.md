# Implementation plan and ownership

Initial contracts frozen: domain/models.py, domain/interfaces.py. Root owns them.
1. Contracts, taxonomy and installable skeleton (root).
2. Archive agent owns storage/, taxonomy/, retrieval/ and test_archive.py:
   canonical atomic persistence, reference/type gates, aliases, duplicate checks,
   retained revisions, migrations, FTS5 and graph rebuild/recovery tests.
3. Evolution agent owns evolution/, breakthrough/ and test_evolution.py:
   immutable append, derived timeline, conservative resolution, technical deltas,
   analog retrieval, version re-review and historical consistency tests.
4. Paper agent owns discovery/, ingestion/, extraction/, comparison/ and
   test_intelligence.py: actual arXiv/OpenAlex adapters, DOI/URL/PDF/text identity,
   staged structured model extraction, explicit fixture provider and comparisons.
5. Discovery agent follows when a slot opens; owns transfer/, opportunities/,
   novelty/ and test_discovery.py. Four discovery modes, retained failures,
   lifecycle/ranking and novelty audit. Root owns Harness export.
6. Root integrates CLI/controller, independent Harness Markdown export, bundled
   synthetic three-paper history and cross-domain demo; then runs all tests,
   installation, command smoke checks and audit against the supplied requirements.

Acceptance: preserve A→B→C history, conditional resolution must not close P;
M2 technical delta exposes its enabling construction; Q is retrieved through a
shared obstruction; transfer includes missing lemmas; failed transfer remains;
v2 invalidates dependent assessments; duplicates are idempotent; absent references
and unsupported review fail; index rebuild preserves graph/history; full offline
sequence exports a Harness-consumable proposal. Live adapters are separately
identified from synthetic evaluation and tested using bounded HTTP fixtures.
