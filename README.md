# Autonomous Agentic AI Engineering Portfolio

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Framework: LangChain & LangGraph](https://img.shields.io/badge/Framework-LangChain%20%7C%20LangGraph-green.svg)](https://www.langchain.com/)

Production-grade Agentic AI Systems, RAG Architecture, and Domain-Adaptive Evaluation Frameworks. Built for high-reliability, verifiable accuracy, and production readiness.

---

## 🚀 Projects Overview

| Component | Description | Highlights |
| :--- | :--- | :--- |
| **[P3: Enterprise RAG Orchestrator](./p3-rag-filings)** | Multi-Agent Agentic **Graph** RAG over messy SEC 10-K filings | Typed fact graph + multi-hop augmentation (ratios/CAGR/comparisons), deterministic clarification for under-specified questions, conversational multi-turn UI, Hybrid + BGE-rerank retrieval, safe Python financial-math tool, LangGraph orchestrator — **96.0% v1-50 (48/50) · 95.6% enterprise (43/45) · 81.3% FinanceBench**, all-free $0.00 |
| **[P1: Agent Evaluation Harness](./p1-eval-harness)** | "Proving Ground" evaluation harness for Agent & RAG systems | Audited golden datasets, two-tier scoring (deterministic + calibrated G-Eval judge, 88.5% human agreement / κ 0.723), full trajectory traces, regression diffs, scorecards — measured P3's 96.0% v1-50 and 81.3% FinanceBench |
| **[Web Portfolio Showcase](./web)** | Interactive Web Dashboard & Scorecard Explorer | Responsive Dark-Mode UI, Live Metric Breakdown, Brutal 20 Stress Test Visualizer |

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

### 5. Launch Portfolio Web Dashboard (`web`)

To view the interactive Web UI and scorecard visualizer:

```bash
cd ..
python -m http.server 8080 -d web
```

Open your browser to [http://localhost:8080](http://localhost:8080) to inspect the interactive dashboard.

---

## 📊 Measured Results — three evaluation surfaces (all-free models, $0.00)

Every figure below was measured on 2026-08-31 using free models
(`minimax/minimax-m3:free` for generation, extraction, and judging). Reproduce
with `eval-harness run` from `p1-eval-harness` (golden sets) or
`python scripts/benchmark_financebench.py` there (FinanceBench).

### 1 · External benchmark — FinanceBench (150 real public-company questions)

| Benchmark | Mode | Accuracy |
| :--- | :--- | :--- |
| **FinanceBench** (Patronus AI, [150 open questions](https://huggingface.co/datasets/PatronusAI/financebench), CC-BY-NC-4.0) | reasoning over given evidence | **81.3%** (122/150) |

*What "reasoning over evidence" means:* FinanceBench's questions reference
filings outside this repo's corpus, as PDFs. So each question is handed its
official evidence excerpt as context, and the system must **ground, verify,
and compute on top of it** — synthesis, numeric-claim verification, and
financial math all run for real. The only step isolated out is *finding* the
evidence (retrieval); the full-retrieval variant is the documented follow-up.

Sample questions from the run (including one failure — honest by design):

| Question (abridged) | Our answer | Verdict |
| :--- | :--- | :--- |
| What is the FY2018 capital expenditure amount (in USD millions) for 3M? | $1,577 million | ✅ |
| Excluding M&A, which segment dragged down 3M's overall growth in 2022? | Consumer — organic sales shrank 0.9% | ✅ |
| Is 3M a capital-intensive business based on FY2022 data? | Yes — citing $9,178M net PP&E and capex… | ❌ official answer is **No** (capex/revenue only 5.1%) — the system argued the opposite conclusion |

### 2 · Enterprise multi-hop set (45 cases — answers in no single chunk)

| Configuration | Accuracy |
| :--- | :--- |
| Retrieval-only (no graph) | 37.8% |
| **+ fact-graph augmentation** | **84.4%** |

The point of this set: ratios, CAGR, and cross-company comparisons need 2+
figures from 2+ places, so retrieval-only fails; the fact graph does the
joining. Samples from
[`golden_set_enterprise_v1.jsonl`](./p1-eval-harness/data/domain_a_financial/golden_set_enterprise_v1.jsonl):

| Question | Expected (figure joins in bold) |
| :--- | :--- |
| What was Microsoft's net profit margin in fiscal year 2025? | 36.1% — **$101,832M ÷ $281,724M** |
| What was the CAGR of Apple's net sales from FY2023 to FY2025? | 4.2%/yr — **$383,285M → $416,161M** |
| Which had the higher operating margin in FY2025: Microsoft or Meta? | Microsoft **45.6% vs 41.4%** |
| How did Microsoft's net profit margin change FY2024 → FY2025? | **36.0% → 36.1%** (+0.2pp) |

### 3 · Audited golden set v1 (50 cases, every answer proven against filing text)

> **Current hiring set: v1-50** — a stratified trim of the frozen 80-case set
> (lookup 12 / table 10 / synthesis 10 / unanswerable 8 / ambiguous 10: all 10
> ambiguous + every documented edge case kept, easy lookup/table thinned).
> **Measured on v1-50 (2026-09-03, free models): 96.0% (48/50)** — lookup
> 100% · table 90% · synthesis 90% · unanswerable 100% (8/8 refusals) ·
> ambiguous 100% (10/10). The 2 failures are the same known pair as v1-80
> (fin-3003 metric-disambiguation, fin-8007 Exxon scope flip). The
> stage-by-stage ladder below was measured on frozen v1-80; the deltas are
> structural (graph injection, deterministic clarification), not fitted.

| Configuration | Accuracy | Note |
| :--- | :--- | :--- |
| Retrieval-only (hybrid + rerank) | 53.8% | generator refuses figures it actually retrieved |
| **+ fact-graph augmentation** | **85.0%** | +31.2pp — fixes all 16 incorrect refusals |
| **+ clarification & company-aware chunks** | **92.5%** | ambiguous 8/10; lookup & table 100% |

Samples from
[`golden_set_v1.jsonl`](./p1-eval-harness/data/domain_a_financial/golden_set_v1.jsonl)
(one per failure category the set is designed to catch):

| Category | Question | Expected behavior |
| :--- | :--- | :--- |
| lookup | What was Coca-Cola's operating income for fiscal year 2025? | $13,762 million |
| table | What did Tesla report as net cash from operating activities for FY2023? | $13,256 million (from the cash-flow table) |
| synthesis | How did Microsoft's R&D expense change from FY2024 to FY2025? | $32,488M, up from $29,510M |
| unanswerable | What was Tesla's total revenue for fiscal year 2022? | **refuse** — FY2022 isn't in the corpus |
| ambiguous | What was the net income? | **ask which company and year** — never guess |

(The `+clarification` configuration measured as high as 96.2% on one run, but
that run caught 2 unanswerable questions flipping to correct refusals by
ordinary free-model variance; 92.5% is the representative repeat.)

Retrieval-strategy ablation (no graph, v1 set): dense 56.2% · hybrid 46.2% ·
hybrid + rerank 55.0% — within run-to-run noise; the fact graph, not the
ranker, is the ~30-point signal.

**Re-validation (2026-08-31, frozen v1-80):** after the eval stack moved to
`p1-eval-harness`, full re-runs through the ported harness reproduced the
results — v1 set **93.8%** (75/80), enterprise set **86.7%** (39/45), and the
G-Eval judge re-calibrated at **88.5% human agreement / Cohen's kappa 0.723**
(original calibration: 86.5% / 0.669). Free-model run-to-run variance is a
few cases; the deltas above are that noise, and the numbers reproduce.

**Post-fix measurement (2026-09-01, frozen v1-80; reproduced on v1-50 + enterprise 2026-09-03, free models):** targeted work on the two remaining
failure classes moved both sets again — v1 set **97.5%** (78/80; **96.0%**,
48/50 on v1-50), enterprise set **95.6%** (43/45, reproduced twice + again 2026-09-03):

- *Ambiguity*: deterministic clarifications now also cover vague-metric
  questions ("earnings", "cash", "growth rate", …) and company-less
  questions — ambiguous cases score **10/10** on v1 (all kept in v1-50) and 7/7 on enterprise
  (was 8/10 and 4/7). The clarifications are scan-verified to fire on
  ambiguous questions only.
- *Unanswerable hallucinations*: an explicit refusal rule in the synthesis
  prompt (never substitute a related figure, never answer from outside
  knowledge) plus closing a verification gap where hedged magnitudes like
  "1.64 million" escaped claim-checking. Refusal safety on the genuinely
  unanswerable cases: **8/8 kept in v1-50** (10/10 on frozen v1-80) and 8/8 (enterprise).
- *Enterprise multi-hop*: graph-rescue outcomes now carry the exact derived
  ratio/CAGR as a grounded line, ending free-model rounding drift ("7%" →
  6.8%, "15%" → 15.2%).
- *Data integrity*: three golden labels were found stale — the filings DO
  contain Tesla's FY2025 deliveries (1.64M, Item 7) and Exxon's crude price
  per barrel ($65.64 consolidated, as "average production prices"), and one
  enterprise expected value was built on a poisoned graph fact (quarantined;
  69 facts now excluded). All three were re-labeled with chunk-level
  evidence; details in the failure-notes doc below.
- *Remaining failures* (2 on v1-50, 2 on enterprise — all previously documented): fin-3003 (synthesis
  metric-disambiguation), fin-8007 (the model alternates between the filing's
  two disclosed scopes: $65.64 consolidated vs $76.23 total-incl-equity),
  ent-1016 (over-refusal of a ratio whose inputs are present — needs the PEP
  graph rebuild noted below), and
  ent-1019 (rounding drift, 7% vs 6.8%). Free-model noise, not a systematic
  gap.

Failure analysis and caveats:
[`p3-rag-filings/docs/graph_augmentation_v1.md`](./p3-rag-filings/docs/graph_augmentation_v1.md).

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
