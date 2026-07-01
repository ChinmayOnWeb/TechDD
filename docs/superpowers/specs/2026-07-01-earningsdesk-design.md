# EarningsDesk — Design Spec

**Date:** 2026-07-01
**Status:** Draft — pending user review
**Author:** brainstormed with Claude Code (superpowers:brainstorming)

## Summary

EarningsDesk is a multimodal financial research agent and portfolio project for an AI-engineering job search. It ingests three sources per company-quarter — earnings call audio, SEC filings (10-Q/10-K), and market data — and answers analyst questions with every numeric claim automatically verified against structured SEC (XBRL) data before it reaches the user.

**Core thesis:** financial numbers have ground truth, so hallucination becomes a measurable, CI-gateable metric rather than a vibe. This is the differentiator versus the flood of generic "RAG + vector DB" portfolio projects.

**Target builder profile:** solo mid-level SWE (2–6 YOE) pivoting to AI engineering; 1–3 months of evening/weekend effort; free-tier APIs and no owned GPU.

## Problem

Analysts and retail investors spend 3–6 hours per company per quarter cross-referencing the earnings call, the filing, and market data. LLM summaries of these sources are untrustworthy because they hallucinate numbers, and users have no way to tell which claims are safe. EarningsDesk makes trust visible: per-claim verification badges backed by deterministic checks against EDGAR XBRL facts.

## Market grounding (researched 2026-07-01)

- HN "Who is hiring" June/July 2026 postings ask for exactly: "agentic systems, LLM integrations, evals" (Factory AI); "multi-agent orchestration builds … 2+ yrs shipping LLM/agentic systems in production," regulated domains including finance (Catalyst Wayfare); one startup screens candidates by asking for "proof of any one exceptional AI project" (Rhythm).
- The candidate side is saturated with near-identical "AI Engineer, 2 yrs, RAG, Vector DB, agentic frameworks" profiles; June 2026 showed the largest gap on record between hiring and wants-to-be-hired threads. Differentiation requires verifiable evals, multimodality, and production ops.
- HuggingFace tasks page confirms multimodal document/audio understanding (Image-Text-to-Text 30k models, ASR 33k models, Visual Document Retrieval) is where model supply exploded while portfolio projects remain rare.

## HuggingFace tasks used

| Task | Use |
|---|---|
| Automatic Speech Recognition | Whisper-large-v3 on call audio; pyannote diarization for speaker attribution (CEO/CFO/analysts) |
| Document Question Answering | Extractive QA over 10-Q/10-K sections |
| Visual Document Retrieval | ColPali/ColQwen-style page-image retrieval over filing pages containing tables and charts |
| Table Question Answering | Financial statement tables from EDGAR XBRL |
| Sentence Similarity / Feature Extraction | Embeddings for hybrid retrieval |
| Text Ranking | Cross-encoder reranking after hybrid retrieval |
| Summarization / Text Generation | Section briefs; final analyst answers |
| Zero-Shot Classification | Question routing; tagging call segments (guidance / risk / Q&A) |
| Audio Classification (stretch) | Vocal-tone/hesitation scoring on executive answers |

## Architecture

### Ingestion layer (batch, per company-quarter)

- **SEC EDGAR API** (free, no key; declared User-Agent, ≤10 req/s): filings as PDF/HTML plus XBRL structured financial facts.
- **Earnings call audio** from company IR pages / public sources → Whisper transcription + pyannote diarization → speaker-attributed, timestamped transcript.
- **yfinance** for market data.
- Filings are indexed two ways: (a) text chunking with section metadata; (b) page-image embeddings (ColPali) so tables/charts are retrievable visually without brittle OCR pipelines.
- All artifacts land in **Postgres + pgvector** with a `document_registry` table (source, ticker, quarter, content hash, ingest status). Ingestion is idempotent; failures quarantine the document with a status row and never poison the index.

### Retrieval layer

- Hybrid search: pgvector cosine similarity + Postgres full-text (BM25-like) fused with reciprocal rank fusion, then cross-encoder rerank.
- Three retrievers behind one shared interface: transcript, filing text, filing page-images.
- Low-confidence retrieval triggers an explicit "insufficient evidence" answer path instead of generation.

### Agent layer (LangGraph supervisor graph)

- **Analyst** — decomposes the question, calls retrievers, drafts the answer with inline citations `[source:page/timestamp]`.
- **Quant** — deterministic tool-calling node: SQL/pandas tools over XBRL facts and yfinance. No free generation; produces the "trusted numbers" table.
- **Verifier** — extracts every numeric/factual claim from the Analyst draft; matches each against Quant's numbers and retrieved sources; returns pass/flag per claim. Flagged claims trigger one revision loop (max 1 retry), after which the answer ships with visible ⚠ flags. Verifier failure fails closed: claim marked unverified and flagged.

### Serving

- FastAPI backend with streaming responses.
- Thin React or Streamlit front-end: answer with per-claim verification badges; citations click through to the filing page image or the audio timestamp.

## Eval harness

- **Golden dataset:** ~150 Q/A pairs across 10 companies × 4 quarters; half manually authored, half synthetically generated then human-reviewed; versioned in-repo.
- **Metrics:** numeric-claim accuracy (exact match vs. XBRL — objective ground truth), citation faithfulness (LLM-as-judge with rubric), retrieval recall@k on labeled relevant chunks, answer completeness, latency, cost per query.
- **CI gate:** GitHub Actions runs the eval suite on every PR touching prompts, retrieval config, or the graph; >2% regression on numeric accuracy blocks merge.
- **Observability:** self-hosted Langfuse; every graph run traced with per-node token cost; weekly scheduled eval run against the golden set to detect drift as models/prompts change.

## Error handling

- Ingestion failure → quarantined document + status row; index never poisoned.
- Low retrieval confidence → "insufficient evidence" path, no generation.
- Verifier failure → fail closed (flag the claim).
- All external APIs wrapped with retry + circuit breaker; EDGAR rate limits respected.

## Testing

- Unit: XBRL parser, transcript alignment — fixture files in-repo.
- Integration: each retriever against a seeded test database.
- Graph-level: mocked LLM asserting supervisor routing and the verify-revise loop.
- End-to-end regression: the eval harness itself, gated in CI.

## Tech stack

Python 3.12 · LangGraph · Postgres + pgvector (single database for vectors, full-text, and XBRL facts — a deliberate "why one DB" system-design decision) · HuggingFace transformers / Inference API (Whisper, ColPali, reranker) · Claude or GPT API for generation and judging · Langfuse (tracing) · FastAPI · Docker Compose · GitHub Actions · demo deploy on a single VPS or HF Spaces.

## Roadmap (3 months, solo)

- **Month 1:** ingestion + hybrid RAG over filings/transcripts for 3 companies; basic Q&A; golden set v0.
- **Month 2:** LangGraph multi-agent + Verifier; eval harness + CI gate; Langfuse tracing.
- **Month 3:** visual document retrieval; UI with verification badges; audio-tone stretch goal; write-up, demo video, and a blog post on measuring hallucination against ground truth.

Scope floor (if time runs short): Months 1–2 alone are a complete, defensible project. Visual retrieval and audio-tone scoring are stretch, not core.

## JD mapping

- "Agentic systems, LLM integrations, evals" → LangGraph supervisor + CI eval gate.
- "Multi-agent orchestration in production, regulated domains (finance)" → the project's exact shape.
- Enterprise RAG (retrieval quality, reranking, hybrid search) → retrieval layer.
- LLMOps (tracing, cost, drift) → Langfuse + scheduled evals.
- "Proof of one exceptional AI project" → this, with a public demo and eval numbers.

## Resume-ready impact metrics (measure first, then claim)

- Reduced numeric hallucination rate from X% to <2% via a claim-verification agent gated in CI.
- Hybrid retrieval + reranking improved recall@5 from X to Y on a 150-question golden set.
- Cut cost per query ~40% by routing sub-tasks to smaller models (traced in Langfuse).
- Indexed N filings + M hours of earnings audio across 10 tickers; p95 answer latency under Z s.

## Assumptions

- Budget ≈ free tiers + modest API spend; no owned GPU (HF Inference API / serverless for heavy models).
- Python; solo builder; public demo and public repo are allowed.
- English-language, US-listed companies (EDGAR coverage).

## Out of scope

- Investment advice, buy/sell signals, or backtesting.
- Real-time streaming during live calls.
- Fine-tuning models (only off-the-shelf inference; fine-tuning could be a later differentiator).
