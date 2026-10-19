# Recording research development

An opportunity can retain source reviews, conditional derivations, counterexamples
and numerical diagnostics as structured, append-only research reviews. This closes
the loop from exploratory work back to the candidate's history without treating
our own calculations as published evidence or independently verified mathematics.

Prepare a UTF-8 JSON review, then record and inspect it:

```bash
scout --workspace /path/to/library review-opportunity review.json
scout --workspace /path/to/library opportunity-reviews OPPORTUNITY_ID
```

The review contains `opportunity_id`, `reviewer`, `summary`, `decision`,
`revised_question`, `findings`, `remaining_work`, `artifacts` and optional
`source_evidence_ids`. A decision is `CONTINUE_NARROWED`, `DOWNRANK` or `DEFER`;
it records the reviewer's recommendation and does not change the opportunity's
lifecycle status or six ranking dimensions.

Each finding includes a `kind`, `claim`, `scope`, `assumptions`, `metric` and
`limitation`. Supported kinds are `CONDITIONAL_DERIVATION`,
`NUMERICAL_DIAGNOSTIC`, `COUNTEREXAMPLE_DERIVATION` and `PRIOR_ART_REVIEW`.
State the precise assumptions and limitations: a diagnostic does not prove a
theorem, and a conditional derivation does not establish novelty. Review `origin`
is fixed to `SYSTEM_INFERENCE`, `novelty` to `UNDETERMINED`, and finding
`verification` to `NOT_INDEPENDENTLY_VERIFIED`.

Artifacts contain a workspace-relative `path`, a lowercase SHA-256 digest in
`sha256`, and a `role`: `PROOF_NOTES`, `SOURCE_REVIEW`, `EXPERIMENT_SCRIPT`,
`EXPERIMENT_DATA`, `FIGURE` or `REPORT`. Compute the digest from the actual bytes,
for example with `sha256sum notes/proof.md`. All referenced files must exist
inside the workspace, including after resolving symbolic links. Absolute paths,
escapes and mismatched digests are rejected before publication.

`source_evidence_ids` must refer to existing canonical `Evidence` records. Artifact
hashes establish which version of our own work was reviewed; they are not a
substitute for version-pinned quotations from papers. A hash match establishes
file identity, not scientific correctness.

Successful publication appends a `RESEARCH_REVIEW` entry with a deterministic
review fingerprint in `review_fingerprint`. Repeating identical content is
idempotent. A later revision of a note or experiment requires a new digest and a
new review, retaining the older review
payload and archive revision. The old payload records the old file digest; it
does not imply that a mutable working file still contains those bytes. Preserve
versioned artifact files when later byte-for-byte replay is needed.
