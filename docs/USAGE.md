# Install and reproduce

Python 3.11+ is required. SQLite must include FTS5. Install from the repository:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,pdf]'
export SCOUT_WORKSPACE=/tmp/research-scout-demo
scout init
scout import-history
scout search 'dissipation'
scout mechanism mechanism-cross
scout evolution problem-p
scout breakthroughs --result result-c
scout transfer mechanism-cross --target problem-q --mode breakthrough-first
scout demo --output /tmp/scout-proposal.md
scout opportunities
```

`import-history` is an explicit **SYNTHETIC** fixture import. It never runs as a
fallback for missing credentials. `demo` computes scoped resolution and
breakthroughs, retrieves Q, proposes a transfer and persists an Opportunity;
it prints exact IDs including `opportunity_id`. Use that ID below:

```bash
scout export OPPORTUNITY_ID --format research-harness --output /tmp/proposal.md
scout index rebuild
scout doctor
scout eval
python -m pytest -q
ruff check src tests
```

`--workspace PATH` before any command overrides SCOUT_WORKSPACE. Default:
`~/.local/share/research-scout`. `SCOUT_CACHE` overrides the source/text cache.
Workspace `config.json` controls interests, source cache, model and endpoint;
credentials remain environment variables. Workspaces need not be in this repo.

## Genuine sources and structured extraction

```bash
scout ingest arxiv:2601.12345v1 --metadata-only  # use a real paper ID
scout ingest '10.1234/replace-with-real-doi' --metadata-only
scout ingest /absolute/path/paper.pdf --metadata-only
scout ingest /absolute/path/paper.md --metadata-only
scout sync --since 7d --profile config/interests.example.json
```

The example IDs are placeholders, not claims that those publications exist.
Metadata/abstract sources retain their actual coverage. Extractable local PDFs
need the `pdf` extra; scans without text fail and require OCR externally.
OpenAlex DOI metadata and citation expansion are also programmatic APIs.

For a provider serving the OpenAI-compatible Chat Completions protocol:

```bash
export SCOUT_MODEL=your-configured-model
export SCOUT_API_KEY=your-key
export SCOUT_BASE_URL=https://your-provider.example/v1
scout ingest /absolute/path/paper.md --extract
```

No configured model means an explicit error for `--extract`, never a synthetic
summary. Extraction validates structured schemas, source hash, coverage and
exact text-span locators before publishing. Reused mechanisms remain shared;
new applications and changed technical constructions are separate records.
Stages and rejected candidates remain in the configurable source cache.
`scout compare PAPER_ID` retains uncertain comparisons and proof obligations.
A revised version preserves the old version and flags dependent assessments.

## Scientific discovery and portfolio

```bash
scout discover mechanism-cross --mode technique-first
scout discover problem-q --mode problem-first
scout discover BREAKTHROUGH_ID --mode breakthrough-first
scout discover FAILED_TRANSFER_ID --mode failure-first
scout opportunity TRANSFER_ID
scout transition OPPORTUNITY_ID SCREENED --reason 'Reviewed scope and evidence'
```

Every candidate remains a hypothesis until scientific review. Ranking dimensions
are separate with reasons/evidence; absence from the archive does not prove
novelty. Failed transfers/rejected opportunities remain persistent negative
knowledge. Programmatic APIs support explicit failures and lifecycle control.

Local text and HTML inputs are conservatively labeled PARTIAL_TEXT; supplying a
text file does not assert that it contains an entire paper. Extractable PDFs
with text on every page are FULL_TEXT; partially readable PDFs stay PARTIAL_TEXT.


## Automatic weekly collection using ChatGPT/Codex

See [automation setup](AUTOMATION.md) for a saved-login Codex extraction provider,
a bounded weekly shortlist, PDF reading, failure retry queue and local reports.
The `scout weekly` command supports `--since 365d --max-papers 1` for a first
bootstrap and uses the workspace profile for subsequent runs. The cron installer
preserves unrelated jobs and requires a running machine/daemon.
