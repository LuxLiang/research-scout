# Maintained research fields

A field dossier is the main reading interface: a problem map, a quantitative
**result-level** table, source-supported related work, comparison boundaries and
revision history. Papers and canonical Result/Evidence records remain the source
of truth. This projection does not manufacture gaps, rankings or theorem proofs.

## Configure and use

```bash
scout --workspace /path/to/library fields configure config/sampling-fields.example.json
scout --workspace /path/to/library fields list
scout --workspace /path/to/library fields update
scout --workspace /path/to/library fields update sfs
scout --workspace /path/to/library fields show sfs --markdown
# Explicitly regenerate model-written prose, then update the dossiers:
scout --workspace /path/to/library fields update --refresh-related-work
```

The registry is `fields.json`, with stable slug IDs, titles, questions, membership
selectors and problem branches. Paper labels/title terms select members;
`exclude_labels` filters automatic membership. Explicit `paper_ids` and
`result_ids` add curated members. `context_paper_ids` makes a source available to
related-work filtering without placing all its results in that field's table.
One canonical result may appear in several fields without being duplicated.
Branch `match_terms` match whole normalized words in result title/model/objective;
explicit `result_ids` support curated assignment. Branches are navigation labels,
not claims of equivalent assumptions. Unassigned results stay visible.

`fields update` works offline, with no model backend or network calls. It uses
**all matching canonical results**, not just recent papers. The field index is
`fields/README.md`; each dossier has `latest.md`, `latest.json` and retained
`revisions/<snapshot>.{md,json}`. Unchanged inputs reuse a snapshot. Changes and
reversions retain separate parent-linked snapshots. Added, changed and removed
result IDs are recorded; removing membership does not delete canonical records.
Registry changes and narrative changes are also distinguished.

## Quantitative meaning and unknowns

Each row pins its Result ID, source PaperVersion/hash, exact Scope, rate, result
type, mechanisms and source evidence. A paper's exact-drift theorem, noisy-drift
theorem, initialization guarantee and empirical finding remain separate rows.
The detailed section shows every extracted assumption and quantifier. Missing
quantifiers, source revisions, metadata-only coverage and unresolved conditions
remain explicit. A new source snapshot does not silently replace old theorems.

Settings are checked within organizational branches, with statuses:

- `SAME_SCOPE_REQUIRES_REVIEW`: extracted strings match; costs and implications
  still need source review.
- `DIFFERENT_SCOPE`: settings differ; no ordering is inferred.
- `INSUFFICIENT_INFORMATION`: missing scope or source-review obligations.

Rate ordering is always `UNASSESSED`. String normalization is deliberately limited;
this is not an algebra engine or a mathematical implication verifier. Empirical
results cannot be silently compared as theorems. Source attribution does not
establish mathematical correctness, and mixed metrics do not define a leaderboard.

Optional `result-notes.json` is a list of ResultNote records for **one exact result
at a time**. Fields include `oracle`, `total_cost`, `initialization`,
`parameter_dependence`, `proof_mechanism`, `boundary`, `provenance`, the
`result_fingerprint` and own-paper/version `evidence_ids`. Obtain the fingerprint
from the result card in `latest.json`, then supply source-supported details.
Unknown values remain null. Wrong-owner evidence fails validation. A changed
result disables its stale note instead of copying obsolete costs into the table.
Paper-level summaries are not copied into every theorem's cost column.

## Related-work maintenance

Dossiers reuse validated, evidence-supported paragraphs from
`reports/related-work/latest.json`. Matching field/context papers select paragraphs;
cross-field references retain their sources. Foundations are still explicitly
abstract/metadata coverage. The input snapshot is compared to current field source
records: changed/new inputs label retained prose `STALE`; absence is `MISSING`.
The result table remains current independently. `CURRENT` means source content
matches, not that proofs or completeness were independently verified.

`scout related-work` updates the source-supported synthesis and then any configured
field dossiers. It considers all extracted papers in the archive, retaining old
foundations as the library grows. Model/context limits can still cause an explicit
failure; no silent truncation or fixture fallback is used. The field projection
can still be rebuilt from source records when synthesis is unavailable.

## Weekly policy

The sampling example enables `related_work_review` and `field_dossiers`, and sets
`automatic_discovery: false` and `theory_gap_review: false`. The order is:

1. Discover, download and extract a bounded selection of papers.
2. Update source-supported related work.
3. Refresh field dossiers and report changed result IDs.

A failed synthesis retains old prose with a stale marker while successful paper
extraction and quantitative dossier updates remain saved. A failed dossier update
is visible in the weekly error list. Manual `scout ingest --extract` also refreshes configured fields and defaults to
no downstream discovery; pass `--discover` to request it. Gap review stays available as an explicit
`scout gaps` command; existing opportunities are retained. Enabling
`automatic_discovery` restores legacy breakthrough/transfer/opportunity processing
for newly ingested papers. Enabling `theory_gap_review` requests weekly theoretical
gap proposals. Neither option is needed to maintain the research fields.
