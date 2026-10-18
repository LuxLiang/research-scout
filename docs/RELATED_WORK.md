# Related work as maintained field knowledge

`scout related-work` builds a related-work draft from source-supported development
tracks. It produces connected prose, a comparison matrix, documented citations,
thematic comparisons, a Mermaid diagram and prioritized missing foundations.

```bash
export SCOUT_WORKSPACE=/path/to/library
scout related-work
scout related-work --refresh
```

Output: `reports/related-work/latest.md` and `latest.json`, alongside input and
model checkpoints keyed by the source context. Unchanged inputs reuse the draft.
The writer does not create research opportunities or promote scientific status.

The context includes all extracted papers and their source evidence.
Optional `related-work-foundations.json` accepts a list of verified SourcePaper
metadata entries. These entries provide historical context with explicit
ABSTRACT_ONLY or METADATA_ONLY coverage; they do not substitute for reading
their full theorems. `gap-prior-art.json` metadata leads are also available.
Dates are earliest arXiv submission dates unless independently established
publication information is supplied. Later revisions can change citation history.

Every archived source used in prose, a comparison row or a relationship must
have its own supplied evidence. The legacy synthesis matrix covers each extracted
paper exactly once. The primary [field dossiers](FIELDS.md) instead use one row
per Result, keeping different theorem scopes within a paper separate. Assumptions, metrics, oracle access and cost, initialization,
proof mechanisms and remaining boundaries are kept separate. A better rate
under stronger assumptions is not automatically an unrestricted improvement.

The citation scanner records only positive title matches after a bibliography
heading and retains the original character span, quotation, version and source
hash. Formatting or PDF extraction can hide references; unmatched titles do not
establish absence of citation. DOCUMENTED_CITATION requires the matching observed
entry. Other connections are labeled THEMATIC_COMPARISON. Neither relationship
asserts a proved improvement or logical implication. Model interpretations of
technical differences still require scientific review.

Set `related_work_review: true` in the weekly profile to update this draft after
paper processing and before theory gap review. A failure prevents that run from
generating gaps from an obsolete draft, while successful source ingestion remains
saved. The manual `scout gaps` command honors the same workspace profile setting.
The validated draft becomes context for subsequent gap proposals. It does not
turn a small library into a complete historical survey or confirm an open problem.

With `fields.json` configured, this command also updates the field dossiers.
For an offline result-table update use `scout fields update`; this preserves
existing prose and marks it stale when its sources have changed. The sampling
weekly profile updates related work and dossiers; gap generation is opt-in.
