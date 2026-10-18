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

Scope dimensions must be nonblank. Missing quantifiers can be retained during
incomplete extraction but prevent full-resolution assessment. Recording and
review timestamps must carry a timezone. Numeric portfolio rankings require
attributable evidence, and all six dimensions stay separate. Canonical storage
also checks lifecycle transitions and append-only portfolio reasoning, so a raw
record import cannot silently bypass the portfolio service.
