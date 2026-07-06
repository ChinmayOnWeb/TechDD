# git-due-diligence

Technical due diligence and valuation modeling for M&A, driven entirely by a target's git history.

Point it at a local clone of a target company's repository and it produces two artifacts:

1. **A due-diligence report** (`analyze`) — findings mined from the full commit history: bus-factor
   risk, leaked secrets, license exposure, tech-debt hotspots, and delivery/release cadence.
2. **A valuation model** (`model`) — the same findings priced into a comps + DCF Excel workbook,
   with the findings applied as concrete EV adjustments (remediation cost, key-person retention,
   license-risk discount, etc).

Everything runs against locally available data only (`git log`, source files on disk) — no code
is uploaded anywhere, and no API calls are made unless you opt into the LLM-backed flags.

## What it checks

| Module | Signal |
|---|---|
| `bus_factor` | Single points of failure per directory; contributors who've gone quiet. CI/bot accounts (e.g. `dependabot[bot]`, `*-bot@*`) are excluded so automation churn doesn't drown out real risk. |
| `security` | Secrets committed to history (even if later removed from HEAD), with confidence-scored false-positive filtering for test fixtures, doc examples, and framework template-binding syntax (e.g. Vue's `:token="expr"`); missing security policy/dependency automation; stale manifests; optional `osv-scanner` integration for known-vulnerability counts. |
| `licenses` | Repository license classification (OSI, non-OSI/fair-code, unknown); copyleft dependencies; JS/TS dependency counts where per-package classification isn't available locally. |
| `hotspots` | Files combining high churn with high cyclomatic complexity — where tech debt actually costs money to fix. |
| `delivery` | Release cadence, merge-commit share, recent commit activity, CI presence. |

Findings degrade gracefully — if a module errors on a given repo, it's marked `failed` with the
error preserved, and every other module still runs.

## Setup

Requires Python 3.12+.

```bash
git clone https://github.com/ChinmayOnWeb/git-due-diligence.git
cd git-due-diligence
python -m venv .venv
.venv/Scripts/activate      # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e .
```

For the LLM-backed flags (`--narrative`, `--questions`), install the optional extra and set an
API key:

```bash
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=sk-...   # or ANTHROPIC_AUTH_TOKEN
```

For dependency vulnerability counts, install [osv-scanner](https://github.com/google/osv-scanner)
and make sure it's on `PATH`; the `security` module detects it automatically and otherwise reports
an honest "not available" finding instead of a false zero.

## Usage

Clone the target repository locally first (this tool never fetches on your behalf):

```bash
git clone <target-repo-url> /path/to/target
```

### Generate a due-diligence report

```bash
gitdd analyze /path/to/target -o dd-report.md
```

Optional flags:

- `--narrative` — prepend an LLM-generated, citation-verified executive summary
- `--questions` — generate an LLM-drafted "question for management" per non-trivial finding
- `--dispositions triage.json` — apply an analyst triage file (see below)

### Generate a valuation model

```bash
gitdd model /path/to/target -a assumptions.toml -o dd-model.xlsx
```

`assumptions.toml` holds every analyst-supplied number the model needs — revenue band, public
comps with their EV/Revenue multiples, DCF growth/margin/discount-rate scenarios, and per-finding
remediation cost assumptions. See [`examples/assumptions.example.toml`](examples/assumptions.example.toml)
for a fully worked, sourced example. Every number in that file should cite where it came from —
the model is only as trustworthy as its assumptions.

The output workbook has five sheets: Assumptions, Comps, DCF, DD Adjustments, and a Valuation
Summary that blends comps + DCF into a pre- and post-DD enterprise value, plus a sensitivity grid.

### Analyst disposition workflow

Real findings need analyst judgment — a "departed key contributor" might just be a founder who
moved into a non-coding role. The `--dispositions` flag points at a JSON file the tool reads,
merges new findings into, and writes back on every run:

```bash
gitdd analyze /path/to/target --dispositions triage.json
```

Each finding can be marked `confirmed`, `downgraded` (with a `severity_override`), or `dismissed`
(with a required `note` explaining why). Dismissed findings are removed from the main report but
preserved in an appendix, and never priced into the valuation model.

## Validating the methodology

Because most acquisition targets are private, there's no ground truth to check a valuation model
against. As part of developing this tool, the full pipeline was run against **GitLab**'s public
repository (117K+ commits) — a public company with known real financials — modeled using GitLab's
actual reported revenue and margins, and the output compared against GitLab's real enterprise
value and market cap. The DCF leg landed within ~20% of reality; the comps leg overshot by ~2.6x
because the peer set didn't match GitLab's actual growth stage — a finding about how to use comps
correctly, not just a demo. (The generated report/model artifacts themselves aren't included in
this repo, since they reference specific findings against a third party's real commit history.)

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests use a shared session-scoped fixture repository (`tests/conftest.py`) with planted scenarios
(single-owner directories, an inactive key contributor, a secret added then removed from history,
a churn/complexity hotspot) so each module's behavior is verifiable without needing a real clone.

## Disclaimer

This tool produces an automated, educational analysis of publicly available data. It is not
investment advice, not a statement about any company's value or conduct, and every finding may be
incomplete or outdated. Treat its output as a starting point for analyst review, not a conclusion.
