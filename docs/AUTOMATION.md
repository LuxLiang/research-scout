# Weekly sampling literature workflow

`scout weekly` discovers recent arXiv literature, deduplicates scientific versions,
selects a bounded shortlist, caches available PDFs, extracts scientific records,
maintains result tables and related work, reviews potential technical transfers, and writes a local report. It preserves failed and
overflow candidates for later runs. Selection is keyword priority, not scientific
quality, truth or novelty assessment. Per-run and per-paper limits are explicit.

## Research interests

`config/sampling-weekly.example.json` tracks:

- underdamped / overdamped Langevin;
- stochastic gradient Hamiltonian Monte Carlo (SGHMC);
- Schrödinger–Föllmer sampling (SFS);
- discrete sampling;
- general stochastic sampling / MCMC.

Only matched topic labels are attached to each paper. The default run examines
an overlapping eight-day discovery window and processes at most twenty papers.
Queries return at most twenty candidates each. Previously published extraction
stages are reused. PDF, model or validation failures stay visible and retryable;
abstract-only metadata never becomes full-text analysis by fallback. Retries reuse cached
PDF/text versions, avoiding repeated downloads when the extraction needs another attempt.

```bash
scout --workspace /path/to/library init
cp config/sampling-weekly.example.json /path/to/library/tracking-profile.json
scout --workspace /path/to/library fields configure config/sampling-fields.example.json
scout --workspace /path/to/library weekly --since 365d --max-papers 1
scout --workspace /path/to/library weekly
# Resume existing candidates without repeating discovery:
scout --workspace /path/to/library weekly --pending-only --max-papers 1
```

The first command with `365d` bootstraps a historical candidate queue. Remove
`--since` for routine weekly collection. Reports retain complete source/version
identity and resulting knowledge IDs. Reports live in `reports/latest.md` and
`reports/latest.json`, with timestamped copies for history. Pending candidates
are persisted in `weekly-pending.json`. An exclusive workspace lock prevents
concurrent collectors. A failed discovery query is recorded as incomplete;
remaining queries still run. The CLI returns a nonzero exit on collection errors.

## ChatGPT-authenticated Codex extraction

The Codex CLI can execute scripted jobs, reuse saved authentication and produce
schema-constrained output: [official non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

Install/sign in to Codex on the same machine and user account as the job:

```bash
codex login
codex login status
```

Configure the workspace `config.json`:

```json
{
  "extraction_provider": "codex",
  "codex_binary": "/absolute/path/to/codex",
  "codex_timeout": 900
}
```

These are fields to update in the existing config, not its entire replacement.
An omitted `llm_model` preserves the Codex CLI's configured default model.
There is no API-key fallback. The backend runs in an empty temporary directory,
with a read-only sandbox, ephemeral sessions and a strict output envelope.
Its scientific records still pass the same Pydantic/source-evidence validator.
The complete source is indexed into exact contiguous segments. The model may select
a supplied segment ID; Scout copies its original text and verified character span,
avoiding PDF ligature/newline transcription errors. Invalid IDs and conflicting
quotations fail. Unique verbatim quotations remain supported, with no fuzzy matching.
Extraction uses a compact first pass; source attribution does not independently
verify that a selected passage proves a scientific statement.
`scout doctor` checks backend availability/login, without making a model call.
Use `scout doctor --check-model` for a minimal live structured model probe. This
sends only a fixed connectivity question, never archive contents, and reports
`model_check.status` separately from `llm_configured`; a failed probe exits nonzero.
Saved login alone does not establish that model execution can start.

In an agent execution sandbox that mounts `~/.codex` read-only, the CLI can report
an existing login but fail before inference with `Read-only file system (os error
30)`. Codex needs to initialize its runtime state; use an authorized execution
environment permitting those state writes. Scout does not relocate or duplicate
the saved credentials to work around that restriction. The supported state
locations are documented in [OpenAI's environment-variable reference](https://learn.chatgpt.com/docs/config-file/environment-variables).
The weekly scheduler outside that restricted execution context uses the existing
login and configuration normally. A live probe is still required to establish
that a particular scheduled-job environment works.

Codex process failures now report fixed categories (`READ_ONLY_STATE`,
`AUTHENTICATION`, `RATE_LIMIT`, `CONTEXT_LIMIT`, `NETWORK`, `MODEL_ACCESS` or
`INPUT_LIMIT` or `UNKNOWN`) without printing raw CLI diagnostics, source text or credentials.
Final error diagnostics take precedence over nonfatal startup warnings.
`INPUT_LIMIT` identifies the CLI's per-turn character limit separately from the
model's token context limit. Large transfer reviews use the explicit
[windowed reading and original-evidence grounding protocol](TRANSFERS.md#large-library-reading).

Saved ChatGPT authentication can expire and usage limits can interrupt runs;
those are explicit retry failures. Do not put authentication files in GitHub.
The existing HTTP model backend remains available as `extraction_provider=http`.

## Install the local schedule

From the repository, preview and install one user cron entry:

```bash
python scripts/install_weekly_cron.py --workspace /path/to/library --print-only
python scripts/install_weekly_cron.py --workspace /path/to/library
```

Defaults are Monday 09:00 Asia/Shanghai. The installer requires the host cron
timezone to match, preserves unrelated entries, and replaces only its own
workspace marker on reinstallation. The machine and cron daemon must be running;
this is local scheduling, not an independently hosted cloud service. Logs are
saved to `weekly-cron.log`; raw credentials are not copied into the job command.
Check the installed entry with `crontab -l`. Remove the line ending in
`# research-scout-weekly:/absolute/library/path` to stop this collection schedule.

The helper writes `run-weekly.sh` outside the package repository. The package must
remain installed in the selected Python interpreter. If an IDE upgrade moves the
Codex binary, update `codex_binary` or provide a stable CLI installation path.

## Existing PDFs and reports

Import an existing paper with `scout --workspace PATH ingest paper.pdf --extract`.
The optional `inbox/` directory is a place to stage files, not a watched folder.
Weekly collection performs literature discovery automatically and does not require
seed PDFs. No email or chat messages are sent by the local collector; its output
is the persistent report and knowledge archive.

## Field maintenance; discovery on demand

The sampling profile enables [related work](RELATED_WORK.md) followed by
[field dossiers](FIELDS.md). It disables `automatic_discovery` and
`theory_gap_review`: routine ingestion does not create canonical breakthrough/transfer
opportunities or gap proposals. `transfer_review: true` separately adds up to three
source-grounded technical transfer ideas to the weekly report, using all extracted
papers and focusing on newly read papers. Each idea records its source mechanism,
target baseline, adaptation, conditional gain, assumptions, missing lemmas and first
falsification test. Zero candidates is valid; failures are explicit. These report
candidates remain unverified, with novelty UNDETERMINED and no external prior-art
search. Retained opportunities, reviews and failed transfers are included as context.
It also schedules up to twelve directed cross-field pairs per run, prioritizing
least-reviewed combinations and different parent families. All attempted pairs
require a candidate or a specific obstruction; past attempts drive rotation.
See [technical transfer review](TRANSFERS.md). Reports link to the field index and include
added, changed and removed result IDs for each maintained field.

A failed narrative update is reported explicitly; current result tables can still
be maintained with old prose labeled stale. Scientific records and prior
opportunities remain preserved. Use `scout --workspace PATH gaps` when a separate
theory-question review is wanted, or explicitly enable the discovery switches.
