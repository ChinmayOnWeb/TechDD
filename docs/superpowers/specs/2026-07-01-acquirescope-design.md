# AcquireScope — Design Spec

**Date:** 2026-07-01
**Status:** Draft — pending user review
**Author:** brainstormed with Claude Code (superpowers:brainstorming)
**Supersedes:** `2026-07-01-earningsdesk-design.md` (shelved — user goal changed from AI-engineering roles to Tech M&A; EarningsDesk spec retained as an alternative)

## Summary

AcquireScope is a portfolio project for breaking into Tech M&A (technical due diligence + financial modelling). It has two coupled deliverables:

1. **An open-source technical due diligence engine** — a Python CLI that analyzes a target company's public repository and git history and produces evidence-linked DD findings.
2. **A published series of acquisition-style DD reports on real commercial open-source companies** ("If you were acquiring PostHog…"), each ending in a real valuation model where technical findings appear as priced line items.

**Core thesis:** the scarcest skill in tech M&A is translating engineering findings into dollars. Most tech DD says "high tech debt"; almost nobody can say "that is $2.3M of remediation capex and 9 months of integration delay — here is the adjusted model." AcquireScope proves that bridge, publicly.

**Target builder profile:** solo mid-level SWE (2–6 YOE) pivoting to tech M&A; 1–3 months of effort; public data only; no paid data sources.

## Problem

Acquirers pay $50–150k per deal to tech DD firms (Crosslake, AKF Partners, Big4 deal advisory) to answer: "what is actually inside this company's technology, and what does it do to the price?" The craft requires reading a codebase and translating findings into valuation adjustments — a rare combination. There is no public body of worked examples; published acquisition-grade DD reports on real companies do not exist. That gap is the portfolio opportunity: each report is simultaneously a work sample, an outreach artifact, and an interview script.

## Deliverable 1: The DD engine

Python CLI, runs against a cloned repo + GitHub API. Six analysis modules, each producing findings linked to specific evidence (files, commits, dependencies):

1. **Architecture & scale map** — module/dependency graph, language breakdown, service boundaries, LOC and ownership by component.
2. **Tech debt quantification** — churn-vs-complexity hotspot analysis on git history (behavioral code analysis, CodeScene-style), complexity metrics (radon/lizard), test-coverage proxies. Output converted to engineer-months → $ remediation capex using documented, benchmark-based assumptions with confidence bands.
3. **Key-person risk** — bus factor per module from commit authorship, contributor concentration (Gini coefficient), detection of critical contributors going inactive. The finding acquirers fear most and rarely quantify.
4. **License & IP risk** — SBOM generation (syft or ORT), dependency license scan, GPL/AGPL contamination in core code paths, CLA presence. License contamination is a genuine deal-killer.
5. **Security posture** — dependency vulnerabilities (osv-scanner), patch cadence, secrets-history scan, security-policy maturity.
6. **Delivery health** — DORA-style metrics: release cadence, PR lead time, review coverage, CI maturity.

**LLM narrative layer (optional module):** synthesizes module outputs into report prose with citations back to specific evidence. Keeps AI-engineering skills visible (retains the verify-against-ground-truth pattern from the shelved EarningsDesk design, applied to code facts). The engine must work fully without it.

## Deliverable 2: The financial modelling bridge

- **Revenue estimation for private targets** from public signals: stated ARR, pricing pages, headcount growth, adoption curves. Every assumption documented in the model.
- **Valuation:** comps-based revenue multiples from public OSS/devtools companies, plus a scenario DCF.
- **DD adjustments as explicit line items:** remediation capex, key-person retention packages, license-risk discount, security remediation, integration cost.
- **Headline artifact:** sensitivity table showing valuation before vs. after diligence findings.
- **Format:** a real Excel model (.xlsx, engine-populated via openpyxl from a hand-built template). Excel is the language of M&A interviews; a notebook is not a deliverable.

## Validation layer

- **GitLab anchor:** run the full methodology on GitLab (public company, real financials) to validate the valuation approach against reality.
- **Bus-factor backtest:** compare model predictions against actual contributor departures visible in later git history.
- **Hotspot backtest:** where targets publicly documented rewrites or incidents, verify the hotspot analysis flagged those components.

## Targets and publishing

- 3–5 report targets from: PostHog, Cal.com, Sentry, Supabase, n8n. GitLab as the validation case.
- Published as a PDF/blog series plus a methodology write-up; engine open-sourced.
- **Legal/ethical guardrails:** public data only; every report clearly labeled as an educational analysis, not investment advice or a statement about the companies; findings framed as observations from public data with dates; no defamatory claims; factual accuracy over sensational headlines.

## Error handling

- A module failure degrades gracefully: the report marks that dimension "not assessed" and the run continues.
- GitHub API usage is rate-limit aware with local caching; re-runs are idempotent.
- Every quantified estimate carries a documented assumption and a confidence band — no naked point estimates.

## Testing

- Unit tests per analysis module against fixture repositories.
- One synthetic repository with known planted issues (a GPL dependency in a core path, a single-owner module, a churn hotspot file) as the end-to-end regression test: the engine must find all planted issues.
- The GitLab validation run doubles as the methodology integration test.

## Tech stack

Python 3.12 · GitPython + GitHub REST API · radon/lizard (complexity) · syft or ORT (SBOM/licenses) · osv-scanner (vulnerabilities) · pandas · openpyxl (Excel model generation) · optional LLM API for the narrative layer · Typer CLI · pytest · GitHub Actions CI.

## Roadmap (3 months, solo)

- **Month 1:** engine core (git analysis, bus factor, license scan) + first full report on one target.
- **Month 2:** financial bridge + Excel deliverable + GitLab validation piece; reports #2–3.
- **Month 3:** security and delivery modules, LLM narrative layer, remaining reports, publish the series + methodology write-up.

**Scope floor:** Month 1–2 output (engine core + financial bridge + two published reports + GitLab validation) is a complete, defensible project. Security/delivery modules and the LLM layer are stretch.

## How it maps to the job

- **Tech DD firms** (Crosslake, AKF, Big4 TMT deal advisory): they do exactly this manually per deal — the candidate arrives with a working methodology and published samples.
- **Corp dev / modelling seats:** the Excel model with DD-driven sensitivity analysis proves the finance half.
- **Networking:** "I wrote a DD report on a company in your space" is outreach currency that resumes are not; each published report targets the exact community that hires for these roles.

## Resume-ready impact metrics (measure first, then claim)

- Published N acquisition-grade technical DD reports on commercial OSS companies; methodology open-sourced (N GitHub stars).
- Quantified technical debt into valuation adjustments of X–Y% of enterprise value via engineer-month remediation modelling.
- Bus-factor model flagged N at-risk modules; backtested against actual contributor departures with Z% precision.
- Built comps + DCF valuation models for N targets (3–5 report subjects plus GitLab); validated methodology against GitLab's public financials.

## Assumptions

- Public data only; no paid data sources; no contact with target companies required.
- Python; solo builder; public repo and blog are allowed.
- Targets are commercial open-source companies with substantially open repos.

## Out of scope

- Private data rooms or confidential materials.
- Investment advice, price targets, or claims about whether any company should be acquired.
- Analysis of closed-source companies (no repo access — different methodology).
- A hosted SaaS product (the engine is a CLI + report pipeline, not a service).

## Relationship to EarningsDesk

EarningsDesk (`2026-07-01-earningsdesk-design.md`) is shelved, not deleted: it remains the better project if the goal reverts to pure AI-engineering roles. If time permits after AcquireScope's scope floor, the LLM narrative layer preserves enough AI surface to credibly hedge both markets. Recommendation remains: one exceptional artifact beats two good ones.
