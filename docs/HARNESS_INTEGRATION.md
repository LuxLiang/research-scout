# Independent Research Harness handoff

Inspected sibling repository `research-harness`: `docs/architecture.md`,
`docs/contracts.md`, `docs/usage.md`, `research_artifacts/proposal_review.py` and
`tests/test_proposal_review.py`. The live ingestion boundary is **Markdown or
text-extractable PDF**, not a Scout-shaped `ResearchProposal` JSON object.
Harness structures this source into its own v0.1.3 ResearchProposal artifact.

`scout export OPPORTUNITY --format research-harness --output proposal.md`
produces the research question, closest literature, historical open problem,
bottleneck, mechanism, novelty/uncertainty, proposed theorem/experiment, assumptions,
proof obligations, risks and first validation plan. All reachable evidence is
listed with exact source/version/locator and canonical record hashes/revisions.
Synthetic exports are prominently labeled. Rejected opportunities and failure
records remain in Scout; exporting does not change scientific status.

```bash
research --workspace /path/to/independent-harness-workspace init scout-review \
  --runtime cordis --mode proposal-review --proposal /absolute/path/to/proposal.md
```

The runtime requires the user's separately configured model host. Scout never
modifies the Harness repository or directly promotes artifacts in its workspace.

## Future reverse import contract (design only)

A future `HarnessOutcome/v1` envelope should carry:
`source_workspace_id`, `project_id`, `artifact_id`, `artifact_revision`,
`artifact_sha256`, `outcome_type` (VALIDATED_RESULT, FAILED_CONJECTURE,
COUNTEREXAMPLE, NEW_MECHANISM), exact `source_proposal_hash`, `scope`,
`evidence_refs`, reviewer identity and immutable verification resources.
It must enter Scout staging as a HUMAN/import-origin candidate, validate references
and pinned hashes, and create new claims/events with provenance. A Harness status
label alone must not overwrite Scout history or close a broader problem. This
reverse interface is documented but not implemented in v0.1.0.
