# Weekly sampling literature workflow

`scout weekly` discovers recent arXiv literature, deduplicates scientific versions,
selects a bounded shortlist, caches available PDFs, extracts scientific records,
runs comparisons/discovery and writes a local report. It preserves failed and
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
an overlapping eight-day discovery window and processes at most five papers.
Queries return at most twenty candidates each. Previously published extraction
stages are reused. PDF, model or validation failures stay visible and retryable;
abstract-only metadata never becomes full-text analysis by fallback. Retries reuse cached
PDF/text versions, avoiding repeated downloads when the extraction needs another attempt.

```bash
scout --workspace /path/to/library init
cp config/sampling-weekly.example.json /path/to/library/tracking-profile.json
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
Evidence offsets can be calculated from unique verbatim source quotations;
ambiguous or absent quotations fail instead of receiving invented locators.
`scout doctor` checks backend availability/login, without making a model call.

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
