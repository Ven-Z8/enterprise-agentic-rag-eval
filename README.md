# Agentic AI Engineering Portfolio

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Framework: LangChain & LangGraph](https://img.shields.io/badge/Framework-LangChain%20%7C%20LangGraph-green.svg)](https://www.langchain.com/)

Production-grade Agentic AI Systems, RAG Architecture, and Domain-Adaptive Evaluation Frameworks. Built for high-reliability, verifiable accuracy, and production readiness.

---

## 🚀 Projects Overview

| Component | Description | Highlights |
| :--- | :--- | :--- |
| **[P3: Enterprise RAG Orchestrator](./p3-rag-filings)** | Multi-Agent Agentic **Graph** RAG over messy SEC 10-K filings | Typed fact graph + multi-hop augmentation (ratios/CAGR/comparisons), deterministic clarification for under-specified questions, FastMCP/FastAPI service, Hybrid + BGE-rerank retrieval, safe Python financial-math tool, LangGraph orchestrator — **84.0% Canonical Enterprise-50 (42/50) · 84.0% FinanceBench (126/150) · 69.7% ConvFinQA (129/185 turns)**, < 0.9¢/query |
| **[P1: Agent Evaluation Harness](./p1-eval-harness)** | "Proving Ground" evaluation harness for Agent & RAG systems | Audited canonical 50-case dataset, two-tier scoring (deterministic + calibrated G-Eval judge, 88.5% human agreement / κ 0.723, DeepEval integration), full trajectory traces, regression diffs, scorecards — measured P3's 84.0% Enterprise-50, 84.0% FinanceBench, and 69.7% ConvFinQA |
| **[P5: System Optimization Layer](./p5-cost-optimization)** | Cost, Latency & Token Optimization Profiler | Model routing, AST evaluation, prompt caching, and verification gates |

---

## 🛠️ Architecture & Key Features

```
               +-------------------------------------------------------+
               |                  User Query / Prompt                  |
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |        LangGraph Multi-Role Agent Orchestrator        |
               +-------------------------------------------------------+
                                           |
                 +-------------------------+-------------------------+
                 |                                                   |
                 v                                                   v
  +-----------------------------+                     +-----------------------------+
  |    Query Decomposition &    |                     |  Hybrid Retrieval & Dense   |
  |     Sub-Question Router     |                     |    BGE Reranker Engine     |
  +-----------------------------+                     +-----------------------------+
                 |                                                   |
                 +-------------------------+-------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |         Safe Python Financial Execution Tool          |
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |      Synthesis Engine & Citation Grounding (LLM)       |
               +-------------------------------------------------------+
                                           |
                                           v
               +-------------------------------------------------------+
               |      Evaluation Harness Scorecard & HTML Dashboard    |
               +-------------------------------------------------------+
```

### Domain skill packs

The engine above is **domain-agnostic**: ingestion, hybrid retrieval +
reranking, the grounded synthesis loop, confidence gating, corrective
verification retries, and refusal/clarification routing are shared by every
domain. Everything domain-specific ships as a **skill pack**
(`p3-rag-filings/src/ragfilings/domains/<name>/`) satisfying one contract
(`DomainPack`):

| Pack hook | financial (SEC 10-K) | legal (commercial contracts) |
| :--- | :--- | :--- |
| Prompts | 10-K synthesis rules (consolidated vs segment, GAAP) | contract synthesis rules (quote the clause, one-agreement rule) |
| Fact layer | typed fact graph parsed from financial tables (chunk provenance) | deterministic defined-term extraction (913 terms, chunk provenance) |
| Scope agent | ticker/metric/fiscal-year rescue + clarifications (missing year, vague metric, no company) | contract-code rescue + "which agreement?" clarification |
| Claim semantics | monetary/percentage figures with unit scaling | quoted language verbatim + money/date claims |
| Derivation tool | safe Python financial math | — (none in v1) |

The evaluation harness selects a pack with `--domain financial|legal`; each
domain has its own golden set under `p1-eval-harness/data/domain_*` and its
own retrieval index. The financial pack is measured end-to-end (below); the
legal pack runs on the CUAD corpus (102 held-out commercial contracts,
attorney-annotated, CC-BY-4.0) — **82.1% (46/56)** on
its 56-case golden set, measured 2026-09-03 (first baseline 80.4% with zero domain-specific tuning (clarifications 6/6;
remaining failures: clause-extraction misses and 3 unanswerable hallucinations
— the same failure taxonomy the financial pack started with). The point is
that adding a domain never touches the engine.

---

## 💻 Quickstart & Setup Instructions

### 1. Prerequisites
- Python **3.11+**
- [`uv`](https://github.com/astral-sh/uv) (recommended fast package installer) or `pip`
- Git

### 2. Environment Setup

Clone the repository and enter the directory:
```bash
git clone https://github.com/Ven-Z8/FreeLance-Potfolio.git
cd FreeLance-Potfolio
```

Copy the sample environment configuration and add your API credentials:
```bash
cp .env.example .env
```

Fill in your API key in `.env`:
```env
OPENROUTER_API_KEY=sk-or-v1-...
# Or set individual keys:
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIzaSy...
```

---

### 3. Setup Project 3: RAG Filings (`p3-rag-filings`)

```bash
cd p3-rag-filings

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e .

# Step 1: Download SEC 10-K filings corpus (~25 financial reports)
python scripts/download_corpus.py

# Step 2: Parse sections and build chunk index
python scripts/dump_sections.py
python scripts/dump_chunks.py
ragfilings index

# Step 3: Build the fact graph, then run an interactive query
ragfilings graph
ragfilings ask "What was Apple's total net sales for FY2025?"

# Conversational multi-turn UI (chat + citations + math + graph)
ragfilings serve          # then open http://127.0.0.1:8000
```

---

### 4. Setup Project 1: Agent Evaluation Harness (`p1-eval-harness`)

The harness evaluates P3 through an adapter, so install it into the **same
venv** you activated for P3:

```bash
cd ../p1-eval-harness

# Install the evaluation harness into the active (P3) venv
uv pip install -e .

# Run pytest unit tests
pytest tests/

# Evaluate P3 against the audited golden set
# (writes scorecards + traces + regression diff to reports/evals/<run>/)
eval-harness run --strategy hybrid_rerank_graph --skip-judge-metrics

# External benchmark: FinanceBench, reasoning-over-evidence (81.3%)
python scripts/benchmark_financebench.py
```

---

## 📊 Measured Results — The 3-Pillar Evaluation Suite

Evaluated using calibrated G-Eval judges (`openai/gpt-5.6-luna`, 88.5% human agreement / κ 0.723), deterministic AST financial-math comparison, and DeepEval faithfulness & relevancy. Reproduce via `p1-eval-harness`:

| Benchmark / Evaluation Surface | Mode / Task Type | Accuracy | Key Reliability Metrics |
| :--- | :--- | :--- | :--- |
| **Canonical Enterprise Golden Set** (`golden_set_v1.jsonl`) | End-to-end multi-hop graph RAG over SEC 10-K filings (50 complex cases) | **84.0%** (42/50) | Retrieval Hit Rate: **92.3%** · Citation Hit: **87.9%** · Unanswerable Hallucination: **0.0%** · DeepEval Faithfulness: **100%** |
| **FinanceBench** (Patronus AI) | Public benchmark: reasoning over filing evidence (150 questions) | **84.0%** (126/150 full dev split) | Calibrated G-Eval judge · Zero hallucination on unanswerables · Grounded metric computation |
| **ConvFinQA** (EMNLP 2022) | Public benchmark: multi-turn conversational financial reasoning | **69.7%** turn accuracy (129/185) · **52.0%** full conv (26/50) | Fast conversational rewriter (~0.8s, gemini-2.5-flash) · Zero JSON/pipeline errors · 1% tolerance |

---

### 1 · Canonical Enterprise 50-Case Golden Set

A comprehensive test suite of 50 complex enterprise financial queries spanning 25 public companies:
- **Accuracy**: **84.0% (42/50)** (Run `20260909-151341-b7f244a1-hybrid_rerank`)
- **Retrieval Hit Rate**: **92.3% (36/39)**
- **Citation Reference Hit**: **87.9% (29/33)**
- **Hallucination Rate on Unanswerables**: **0.0% (0/6)** — strict refusal guardrail prevents fabricating numbers
- **DeepEval G-Eval Quality**: **100.0% Faithfulness** and **100.0% Answer Relevancy**
- **Query Economics**: **$0.0086 / query** (< 0.9¢)

Representative test cases from [`golden_set_v1.jsonl`](./p1-eval-harness/data/domain_a_financial/golden_set_v1.jsonl):

| Category | Question | Expected Behavior |
| :--- | :--- | :--- |
| **lookup** | What was Coca-Cola's operating income for fiscal year 2025? | $13,762 million |
| **table** | What did Tesla report as net cash from operating activities for FY2023? | $13,256 million (from the cash-flow table) |
| **synthesis** | How did Microsoft's R&D expense change from FY2024 to FY2025? | $32,488M, up from $29,510M |
| **unanswerable** | What was Tesla's total revenue for fiscal year 2022? | **Refuse** — FY2022 is not in the corpus |
| **ambiguous** | What was the net income? | **Clarify** — asks which company and year |

### 2 · FinanceBench (Patronus AI)

Evaluates financial grounding, metric derivation, and evidence reasoning over public 10-K filings with retrieval isolated or end-to-end:
- **Reasoning-over-Evidence Accuracy**: **84.0% (126/150)** on the full 150-question benchmark (`fb_evidence_20260909-173735.jsonl`).
- Evaluated against official answers using the calibrated G-Eval LLM judge (`openai/gpt-5.6-luna`).
- Handled complex analytical queries (e.g., operating margin drivers, capital expenditures) and financial ratios without over-refusal.

### 3 · ConvFinQA (EMNLP 2022)

Evaluates multi-turn conversational financial reasoning with chained calculations over annual-report tables:
- **Conversational Turn Accuracy**: **69.7% (129/185 turns)** across 50 multi-turn conversations (`convfinqa_20260909-184557.jsonl`).
- **Full Conversation Accuracy (all turns correct)**: **52.0% (26/50 conversations)**.
- **Ultra-Fast & Resilient Conversational Pipeline**: High-speed rewriter (~0.8s via `google/gemini-2.5-flash`), 0 JSON/pipeline errors, and seamless chained follow-up arithmetic (`"what is that times 100?"`).

---

## 📂 Repository Structure

```
FreeLance-Potfolio/
├── README.md                      # Global setup & portfolio overview
├── .env.example                   # Environment keys template
├── p3-rag-filings/                # Project 3: Multi-Agent RAG Orchestrator
│   ├── src/ragfilings/            # Core RAG source code (retrieval, agent, prompts)
│   ├── golden/                    # Golden-set drafts & schema (canonical data in p1)
│   ├── scripts/                   # SEC EDGAR downloader, parser, golden builders
│   └── pyproject.toml             # Python dependencies & CLI entrypoints
├── p1-eval-harness/               # Project 1: Agent Eval Harness ("Proving Ground")
│   ├── src/harness/               # Scoring engine, calibrated judge, runner, adapters
│   ├── data/domain_a_financial/   # Audited golden sets, calibration labels, audit evidence
│   ├── scripts/                   # Judge calibration, FinanceBench benchmark
│   └── reports/                   # Scorecards & JSON traces (gitignored)
├── web/                           # Portfolio Web UI Showcase
│   ├── index.html                 # Interactive portfolio homepage
│   ├── app.js                     # Dashboard interaction logic
│   └── styles.css                 # Custom modern dark-mode styles
├── p5-cost-optimization/          # 🔮 FUTURE SCOPE — optimization roadmap (prototype, not evaluated)
```

---

## 📄 License

This repository is licensed under the [MIT License](LICENSE).
