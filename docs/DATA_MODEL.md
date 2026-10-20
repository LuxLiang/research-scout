# Scientific data model v1.0

`domain/models.py` is the shared executable contract. Every canonical Record has
stable ID, schema version, revision, timestamps, provenance, multi-label taxonomy,
aliases, synthetic flag, evidence IDs and assessment status. Unknown fields fail.

Paper identity and PaperVersion are distinct. Evidence pins paper/version and an
actual supplied locator, source hash and coverage. Abstract-only evidence cannot
support theorem-level independent verification. ScientificClaim explicitly
separates AUTHOR, SYSTEM_INFERENCE and HUMAN origin. Independent review requires
reviewer identity, timestamp, rationale and evidence; storage validates references.

Topic → ProblemFamily → PreciseProblem; only precise formulations have timelines.
Scope pins model, objective, assumptions, quantifiers, metric, guarantee and
unresolved settings. Text resemblance never proves assumption implication.
Bottleneck is reusable and hypothesized by default; established status requires
evidence. MechanismFamily → Mechanism → Variant; Application is a separate record.
PreciseProblem may have no bottleneck: optional `open_questions` and
`difficulty_hypotheses` preserve unknowns and tentative explanations without
asserting an established obstruction. Mechanism optionally records `input_objects`,
`output_guarantees` and `reusable_steps`; assumptions and limitations remain attached.
Variants state an exact technical difference; use in a new field is an application.
Result distinguishes theorem, algorithmic guarantee and empirical observation.

Relationships have typed endpoints, scope, assumptions, provenance, evidence and
explicit hypothesis status. Event records are immutable and include scientific
and recording dates, source/version, prior events and scoped assessment.
BreakthroughAssessment describes technical delta and analog targets.
TransferHypothesis records assumptions, missing lemmas, differences, counterexamples,
prior art and falsification test; failed outcomes retain reasons. Opportunities
retain lifecycle history and six separate evidence-qualified ranking dimensions.
EntityChange records merges/splits without rewriting historical event IDs.

Transfer bottleneck references are optional. `maturity` distinguishes an
`EXPLORATORY_LEAD` (requires `match_basis` and `next_action`), a
`TRANSFER_HYPOTHESIS`, and a `VALIDATION_PLAN` (requires `adaptation`,
`bridge_statement`, proof obligations and a falsification test). Existing transfers
default to TRANSFER_HYPOTHESIS for backward compatibility. `revisit_when` retains
conditions for reconsideration after failure. No maturity value certifies a proof.
Exploratory leads cannot be supported transfers or linked to Opportunities,
including through raw canonical imports. Missing bottlenecks stay null and are
never replaced with placeholder scientific records.

Scope dimensions must be nonblank. Missing quantifiers can be retained during
incomplete extraction but prevent full-resolution assessment. Recording and
review timestamps must carry a timezone. Numeric portfolio rankings require
attributable evidence, and all six dimensions stay separate. Canonical storage
also checks lifecycle transitions and append-only portfolio reasoning, so a raw
record import cannot silently bypass the portfolio service.

ResearchField/FieldBranch configuration and ResultNote annotations are separately
typed workspace projections, not new canonical scientific statuses. Result notes
pin a content fingerprint and own-version evidence; unknown cost and oracle
fields remain null. Field snapshots preserve exact Result/Scope references,
conservative comparison outcomes and parent-linked changes. Source-currentness,
coverage and mathematical verification remain distinct. See [field dossiers](FIELDS.md).

ResearchReview/ResearchFinding/ResearchArtifact are typed input envelopes for
append-only `RESEARCH_REVIEW` entries in Opportunity history, not new canonical
Result or Evidence kinds. Each review retains a deterministic `review_fingerprint`,
scope, assumptions, metric, limitations and content-pinned local artifacts.
Paper evidence references remain canonical references; artifact hashes and the
review fingerprint are content metadata. Novelty is always UNDETERMINED, findings
remain NOT_INDEPENDENTLY_VERIFIED and origin is SYSTEM_INFERENCE. Recording a review
does not change lifecycle status or numerical ranking. See [research reviews](RESEARCH_REVIEWS.md).
