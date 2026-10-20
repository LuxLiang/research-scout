# New techniques for existing problems

The main question is: **does a newly available technique create a useful way to
approach an older question?** A known bottleneck is optional. Problems may retain
only their precise goal, known results, open questions and tentative explanations
of difficulty. Exploring a technique can reveal the obstruction for the first time,
replace a lossy proof step, or bypass the old proof entirely.

Mechanisms retain attributable input objects, output guarantees, reusable steps,
assumptions and limitations. These capability descriptions support three routes:
matching the desired goal, matching explicit mathematical structure, and trying
a proof role or construction in a different setting. Same-field reuse is eligible;
cross-field exploration supplements rather than restricts this search.

## Specificity, not scientific certification

| Maturity | Required content | Next step |
| --- | --- | --- |
| EXPLORATORY_LEAD | Attributable connection and next action; the obstruction may be unknown | Read the target proof, test an analogy, or identify a possible construction |
| TRANSFER_HYPOTHESIS | A proposed adaptation, assumptions and outstanding proof obligations | Refine the mathematical interface and inspect prior attempts |
| VALIDATION_PLAN | A bridge proposition, adaptation, obligations and first falsification test | Execute the scoped proof attempt or diagnostic |

None of these labels establishes correctness, novelty or an open-problem status.
A lead may have no target baseline result or known bridge lemma; unknowns remain
explicit rather than being filled with template claims. Leads cannot automatically
enter the Opportunity portfolio, including through raw archive imports.

Failed canonical transfers retain the original reason and `revisit_when`
conditions. An explicit failure-first retry links the old attempt; changed tools
can motivate a new attempt without erasing the previous failure. Merely storing a
revisit condition does not prove that it has been met.

## Trigger and inspect exploration

[Research RAG](RETRIEVAL.md) supplies ranked leads and original source windows
while retaining the complete extracted inventory. Candidate adaptations trigger
a second retrieval at source and target versions. Model grounding receives the
original evidence and source context and may narrow or remove ideas. Reports
distinguish source-passage references from canonical Evidence IDs and record
missing sources and partial-reading coverage.

Incremental ingestion with discovery enabled explores extracted mechanisms even
if the breakthrough analysis is inconclusive. Offline exploration is available
without a model, using explicit archived structures, scope matches and proof roles:

```bash
scout --workspace /path/to/library discover MECHANISM_ID --mode technique-first
```

Offline matching produces tentative connections; it cannot infer mathematical
implication or invent an unknown proof interface. Model-assisted weekly review
examines newly extracted mechanisms against the retained library and records an
attempt rationale even when no candidate is supported. Model failures remain
errors, not successful coverage or empty scientific conclusions.

## Model-assisted review

The sampling weekly profile reads up to **20 papers per run** and enables
`transfer_review`. After related work and field tables, Scout compares the entire
extracted library for potential technical arbitrage: a concrete mechanism from
one problem that might overcome an obstruction in another. Newly extracted papers
are focus inputs, not a restriction on historical context. A narrative failure
does not block this review: it uses canonical source records, not stale prose.

Run just this review without collecting more papers:

```bash
scout --workspace /path/to/library transfer-review
scout --workspace /path/to/library transfer-review --refresh --max-candidates 3
scout --workspace /path/to/library transfer-review --focus-paper PAPER_ID
```

Each candidate supplies an archived source result and its actual mechanism,
a distinct target problem, target baseline results when known, and evidence
for every referenced result, mechanism and problem. It describes shared structure,
the specific adaptation, conditional gains, required assumptions, missing lemmas,
counterexample risks, closest known prior art and a first falsification test.
Already archived applications of that mechanism at the target are rejected.
Missing/foreign record references, missing evidence, duplicate pairs, empty
technical fields, excess candidates and asserted confirmed novelty are rejected
before publication. Attribution checks do not validate the proposed mathematics.

The model receives existing opportunities (including rejected ones), research
reviews and failed transfers, with instructions to address retained objections.
This is context-based reasoning, not an automatic proof that all past failures
have been resolved. External prior-art search is not performed by this review;
novelty remains `UNDETERMINED`. Use the separate theory-gap review and independent
source inspection for further investigation. Zero ideas is valid.

Reports are retained in `reports/transfers/<input-fingerprint>.{json,md}`, with
`latest.json` and `latest.md`, exact evidence locators/versions/hashes, input and
model checkpoints. Unchanged inputs reuse a validated report; `--refresh` requests
new generation. The weekly report embeds candidate summaries and links to the
full review. Model or validation errors are listed as `transfer_review` errors,
with successful ingestion and field updates preserved.

This stage creates report candidates, not canonical Opportunity or Result records.
It does not enable the legacy `automatic_discovery` chain or `theory_gap_review`.
Set `transfer_review: false` to disable it. `max_transfer_candidates` is 1–3;
`max_papers` defaults to 20 and can be reduced per run with `--max-papers`.
The configured structured Codex backend is required for nonempty source libraries;
there is no fabricated or fixture fallback.

## Directed cross-field exploration

When `fields.json` exists, the review receives the same result-level memberships
used by the field dossiers. The sampling configuration has four parent overviews
and eighteen leaf subfields. Only nonempty leaves participate. A source result
must belong to its chosen source leaf but not the target leaf; every target
baseline must belong to the target leaf but not the source leaf. Choosing two
overlapping tags for the same results cannot manufacture a cross-field idea.

As supplementary exploration, each run schedules up to `max_transfer_field_pairs: 12` directed pairs. It first
considers least-reviewed pairs, then favors different parent families, new-paper
context and diversity of source/target families and subfields within the batch.
Retained report history rotates future runs toward unreviewed pairs. A→B and B→A
are separate attempts. Empty or identical result sets are not paired.

The model must record exactly one `field_pair_reviews` entry for every scheduled
pair: `CANDIDATE` with a retained idea, or `NO_SUPPORTED_IDEA` with a concrete
obstruction or evidence limitation. Review outcomes and candidate field
attributions are validated before publication. These entries record model
analysis, not executed experiments or mathematical validation. Weekly reports
show attempted pair counts and candidate directions; the detailed report retains
all attempted pairs and their reasons. At most three supported candidates are
retained even when more pairs are examined.

```bash
scout --workspace /path/to/library transfer-review --max-field-pairs 12
```

Field configuration and selected pairs are included in the input fingerprint.
Rotation can therefore trigger a fresh review even when the literature is
unchanged. Context or backend failure cannot be recorded as successful coverage.

## Large-library reading

The inspected Codex CLI rejects a turn longer than 1,048,576 characters. Scout
uses an explicit staged protocol when the transfer prompt exceeds a conservative
one-million-character budget; it does not switch to a recent-paper subset.

Every original Evidence record is read in a bounded window. Each window must
return exactly one short reading note per supplied evidence ID; missing,
duplicate or invented IDs fail before synthesis. Validated windows are retained
and reusable. Reading notes are model inferences, never canonical Evidence.

Synthesis receives all extracted scientific records and their scopes, evidence
locator/version/hash metadata and reading notes. Bookkeeping/empty defaults and
redundant paper-level first-pass summary arrays are omitted from this model
projection; the complete input snapshot remains retained. Long identifiers are
reversibly aliased for transport, then restored before scientific validation.
If the complete projection still exceeds the budget, the review fails explicitly.

Before publication, a separate grounding pass receives each proposed candidate's
original scientific records, full cited quotations and source bibliography. It
may narrow or remove candidates, but cannot introduce unseen source/target
triples or cite records outside that pass. The normal canonical attribution and
coverage gates then run on the final candidates. Model grounding checks source
attribution, not independent mathematical correctness. Reports describe this
reading protocol and retain input, passage, synthesis and grounding checkpoints.
