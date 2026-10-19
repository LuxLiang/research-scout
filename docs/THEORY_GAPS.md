The primary weekly workflow maintains [research fields](FIELDS.md). Gap review
is an explicit research session; the sampling profile disables it by default.
Existing hypotheses remain retained for future review.

# Theory questions and gap review

The research library is an input to discovery. `scout gaps` compares extracted
problems, source results, mechanisms, evidence and extraction limitations to
propose up to three explicit theory questions. Zero candidates is valid. Naive
ideas already covered by the supplied literature are retained as exclusions.

The sampling profile first updates [related work and development tracks](RELATED_WORK.md).
The validated history and scope-comparison matrix inform the gap stage. If that
update fails, gap generation is skipped for the run. Existing candidate decisions
are retained; a revised narrative is not a novelty confirmation.

```bash
export SCOUT_WORKSPACE=/path/to/research-library
scout gaps
scout opportunities
scout gaps --local-only       # explicit: no external prior-art search
scout gaps --refresh          # request new model generation for the same inputs
```

The configured Codex backend uses the existing saved login. Other extraction
backends do not silently substitute a gap generator. Source material and archive
records are untrusted model input. This task proposes hypotheses; it cannot
verify a theorem, establish novelty or invent source evidence.

## Output and scientific gates

Each candidate needs two distinct supplied papers, evidence from every cited
paper, source mechanisms/results, a precise target scope with quantifiers, an
explanation of what the closest results do not establish, missing lemmas, a
first falsification test, failure conditions and focused prior-art queries.

All candidate references are checked before publishing any candidate. Accepted
formulations create a proposed problem, a **hypothesized** bottleneck and an
Opportunity in **HYPOTHESIS** status. Provenance labels these as system inference,
not author claims. Numeric ranking dimensions remain unassessed. Different metrics,
oracle access, initialization costs or numbered-but-unexpanded assumptions require
additional review before a scientific comparison.

Reports are in `reports/gaps/latest.md` and `latest.json`, with immutable input
fingerprint files. Raw structured model output is checkpointed before validation
so that failed references can be examined without repeating an expensive call.
The same input within seven days reuses the report. After a week, prior-art search
is repeated while the saved model proposals are reused. A refresh retains existing
opportunity decisions/history rather than promoting rejected or investigated items.

By default, generation includes every extracted paper in the archive, its
indexed non-synthetic evidence and attributable first-pass scientific records.
This is the full structured corpus, not every full PDF read simultaneously;
metadata-only and unextracted papers are not represented as extracted results.
Older foundational papers remain available alongside recent papers. Changes to
their supplied records change the input fingerprint and invalidate the cached
generation just as changes to recent papers do.

The internal context builder accepts an explicit `paper_limit` for bounded
inspection, and labels that context as limited. `scout gaps` and weekly gap review
use the full corpus. Backend/context-size failures are reported explicitly;
there is no silent retry with a newest-paper subset. Optional `gap-prior-art.json`
can supply a JSON list of verified SourcePaper metadata leads for
exclusions/comparison; source coverage remains explicit.

Appended [research reviews](RESEARCH_REVIEWS.md) enter subsequent gap context as
retained system inferences, including narrowed questions and counterexamples.
They change the input fingerprint but do not become paper evidence or confirmed
theorems. Reports and Harness exports retain these refinements alongside the
original candidate formulation.

## External checks and their limits

Each candidate can request at most two arXiv queries, with eight results per query
and spacing between requests. Matches are metadata/abstract leads in the report;
they do not become full-text theorem evidence. Failures are recorded separately
from successful empty searches. The query limit and arXiv-only coverage can miss
older or differently phrased results. **Novelty always remains UNDETERMINED.**
The next scientific step is to read the closest full results and verify whether
their assumptions, oracles, rates and proof constructions cover the proposed scope.

## Weekly use

Set these fields in `tracking-profile.json`:

```json
{
  "related_work_review": true,
  "theory_gap_review": true,
  "max_gap_candidates": 3
}
```

The weekly collector runs theory review after paper extraction and links its
report from the weekly report. A review failure is reported explicitly without
rolling back successful paper ingestion. Metadata-only collection skips theory
review. The sampling profile keeps this stage off unless explicitly enabled.

An Opportunity may later be rejected with a reason, investigated, or exported
through the existing Harness proposal interface. These steps retain the
distinction between an interesting question, a genuinely open problem, and a
proved result.
