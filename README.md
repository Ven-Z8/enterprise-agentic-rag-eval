# Enterprise Agentic Graph RAG & Evaluation Studio

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Framework: LangGraph](https://img.shields.io/badge/Orchestrator-LangGraph-orange.svg)](https://www.langchain.com/langgraph)
[![Validation: Instructor & Pydantic](https://img.shields.io/badge/Validation-Pydantic%20%7C%20Instructor-green.svg)](https://python.useinstructor.com/)
[![Evals: DeepEval](https://img.shields.io/badge/Evals-DeepEval%20G--Eval-purple.svg)](https://confident-ai.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A production-grade, **Neuro-Symbolic Agentic RAG System** engineered for high-precision financial intelligence over messy SEC Form 10-K filings. Combines table-aware chunking, typed fact graphs with chunk provenance, sandboxed Python AST mathematical computation, and a calibrated evaluation harness with proven human agreement ($\kappa = 0.723$).

---

## ⚡ Quick Navigation

- 📖 **[System Architecture Specification](docs/ARCHITECTURE.md)** — Deep dive into the LangGraph state machine, typed fact graph, and enterprise scaling blueprint.
- 🔬 **[Evaluation Harness & Proving Ground](eval-harness/)** — Enterprise evaluation framework, audited golden sets, and calibrated G-Eval judge ($\kappa = 0.723$).

---

## 💥 The Problem: Why Naive / Baseline RAG Fails on SEC 10-K Filings

| Challenge | Why Naive / Baseline RAG Fails | How This System Solves It |
| :--- | :--- | :--- |
| **Tabular Financial Data** | Naive text chunking cuts multi-column tables arbitrarily, separating numeric cells from year headers. | **Table-Aware Parser:** Reconstructs financial statements into aligned grids and maps them to a typed **Fact Graph** with chunk provenance. |
| **Mental Math Hallucination** | LLMs cannot reliably calculate YoY changes, CAGR, or margins in freeform text without arithmetic errors. | **Safe Python AST Math Tool:** Mathematical expressions are extracted and executed in an isolated, sandboxed Python runtime. |
| **Consolidated vs. Segment Ambiguity** | Vector search matches "revenue" chunks indiscriminately, confusing segment tables (e.g. AWS or Family of Apps) with consolidated totals. | **Deterministic Scope Triage:** Disambiguates ticker, metric, and fiscal-period scope up front with zero token expenditure. |
| **Silent Guessing** | Under-specified queries cause models to guess corporate intent or fabricate figures. | **Deterministic Clarification & Safe Refusal:** Unambiguously clarifies missing parameters (<15ms) and strictly refuses out-of-corpus requests (0% hallucinations). |

---

## 🏗️ System Architecture & Workflow

```
                                  +------------------------------------+
                                  |         User Query / Prompt        |
                                  +------------------------------------+
                                                     |
                                                     v
                                  +------------------------------------+
                                  |     Deterministic Scope Triage     |
                                  |            (rescue.py)             |
                                  +------------------------------------+
                                      /                            \
              [Clean Scope / Ambiguous]                            [Complex / Open-Ended]
                     /                                                        \
                    v                                                          v
    +--------------------------------+                         +--------------------------------+
    |   Instant Scope Disambiguation |                         |     Neural Planning Agent      |
    |   or Fact-Graph Fast-Path      |                         |  - Instructor Pydantic Plan    |
    |   (0 tokens · < 15ms latency)  |                         |  - Multi-Query Decomposition   |
    +--------------------------------+                         +--------------------------------+
                    \                                                          /
                     \                                                        /
                      +-----------------------+------------------------------+
                                              |
                                              v
                              +--------------------------------+
                              |    Hybrid Retrieval Engine     |
                              | - Dense (bge-small-en-v1.5)    |
                              | - Sparse BM25 Keyword Search   |
                              | - Reciprocal Rank Fusion (RRF) |
                              | - Cross-Encoder Reranker       |
                              +--------------------------------+
                                              |
                                              v
                              +--------------------------------+
                              |   Safe Python Math Tool (AST)  |
                              |   - Margins, YoY %, CAGR       |
                              |   - Sandboxed Execution        |
                              +--------------------------------+
                                              |
                                              v
                              +--------------------------------+
                              |    Grounded Synthesis Agent    |
                              |    - Verbatim Citation Binding |
                              +--------------------------------+
                                              |
                                              v
                              +--------------------------------+
                              |     Two-Tier Audit Engine      |
                              | 1. Deterministic AST Verifier  |
                              | 2. LLM Claim Auditor Guard     |
                              +--------------------------------+
                                       |              ^
                            [Pass]     |              | [Fail: Retry Feedback]
                               v       v              | (Bounded Cyclic Loop)
                        +--------------------------------+
                        | Verified Answer with Provenance|
                        +--------------------------------+
```

---

## 🚀 Key Measured Results

Evaluated across Financial (SEC 10-K), Legal (CUAD, LegalBench), and Biomedical (PubMedQA, PubChem) domains using calibrated G-Eval judges (`openai/gpt-5.6-luna`, **88.5% human agreement / Cohen's $\kappa = 0.723$**), deterministic AST claim matching, and DeepEval faithfulness.

### 1. Primary Enterprise Financial Benchmarks

| Benchmark Suite | Scope & Dataset | Accuracy | Economics & Reliability |
| :--- | :--- | :--- | :--- |
| **Canonical SEC 10-K Suite** | 50 audited enterprise cases across 25 public filers | **98.0%** (49/50) | **0.0% Hallucinations** · Ambiguous: **100%** · Math & Ratios: **97.1%** · **$0.0076 / query** |
| **FinanceBench** (Patronus AI) | 150 public SEC 10-K questions requiring multi-step financial reasoning | **86.7%** (130/150) | Full evidence reasoning · 0 rate-limit dropouts · Evaluated via calibrated G-Eval judge |
| **ConvFinQA** (EMNLP 2022) | 50 multi-turn financial table dialogues (185 turns) | **69.2%** (128/185 turns) | Fast-path follow-up rewrites (~0.8s) · 0 JSON schema crashes · Full conversations: **46.0%** |

### 2. Cross-Domain Generalization (Pluggable Skill Packs)

The core orchestration engine is 100% domain-agnostic. Pluggable domain packs satisfy the [`DomainPack`](rag-engine/src/ragfilings/domains/__init__.py) contract:

| Domain Benchmark | Focus Area | Performance | Highlights |
| :--- | :--- | :--- | :--- |
| **Stanford LegalBench** (NeurIPS 2023) | Consumer Terms of Service QA (396 cases) | **98.2%** (389/396) | **100.0%** Clause Citation Rate · **$0.0018 / query** · 3.10s latency |
| **CUAD Legal Contracts** (NeurIPS 2021) | Commercial contract review (102 agreements) | **78.6%** (44/56) | Ambiguous Clarifications: **100%** · Term Lookups: **90.0%** · Faithfulness: **99.0%** |
| **PubMedQA & NCBI PubChem** (BioNLP) | Clinical synthesis & live chemical API resolution | **86.0%** (43/50) | **0.0% Hallucinations** · Safe Refusals: **100%** · Live API Resolution: **80.0%** |
| **Isaacus Legal RAG Bench** (2024) | Statutory & criminal bench book retrieval | **20.0%** Hit@3 | Dual-layer retrieval & synthesis against criminal law statutes |

---

## 💻 Quickstart: Running in 3 Steps

### Prerequisites
- Python **3.11+**
- [`uv`](https://github.com/astral-sh/uv) (recommended fast package installer) or `pip`
- Git

### 1. Clone & Configure Environment
```bash
git clone https://github.com/Ven-Z8/enterprise-agentic-rag-eval.git
cd enterprise-agentic-rag-eval
cp .env.example .env
# Add your OpenRouter, OpenAI, Anthropic, or Gemini API keys to .env
```

### 2. Launch the Core RAG Orchestrator (`rag-engine`)
```bash
cd rag-engine
uv venv && source .venv/bin/activate
uv pip install -e .

# Query the engine directly via CLI
ragfilings ask "What was Apple's total net sales for FY2025?"

# Launch the FastAPI service
ragfilings serve
```

### 3. Open the Universal Agentic Cockpit UI (`cockpit-ui`)
In a separate terminal, launch the interactive visual cockpit:
```bash
cd ../cockpit-ui
python3 -m http.server 3000
```
Open **[http://localhost:3000](http://localhost:3000)** in your browser. The Cockpit auto-connects to your FastAPI backend, visualizing real-time query trajectories, force-directed knowledge graphs, and execution traces.

---

## 🧪 Running the Evaluation Harness (`eval-harness`)

The evaluation harness ("Proving Ground") verifies end-to-end correctness, citation grounding, and regression tracking:

```bash
cd eval-harness
uv venv && source .venv/bin/activate
uv pip install -e .

# Run unit tests (51 tests)
pytest tests/

# Execute the 50-case Canonical Financial Evaluation
eval-harness run --strategy hybrid_rerank_graph --skip-judge-metrics

# Execute the external FinanceBench benchmark
python scripts/benchmark_financebench.py
```

---

## 📂 Repository Architecture

```text
enterprise-agentic-rag-eval/
├── README.md                      # Global executive overview & quickstart
├── docs/                          # Architectural documentation & technical specifications
│   ├── ARCHITECTURE.md            # Deep-dive system architecture specification
│   └── PORTFOLIO_V0.2_SPEC.md     # Production release requirements & design log
├── rag-engine/                    # Core deliverable: Multi-Agent RAG Orchestrator
│   ├── src/ragfilings/            # Ingestion, hybrid retrieval, LangGraph agents, fact graph
│   ├── corpus/                    # 25 SEC 10-K filings, chunk index, financial_graph.json
│   ├── tests/                     # 184 passing unit tests
│   └── pyproject.toml             # Python dependencies & CLI entrypoints
├── eval-harness/                  # Core deliverable: Agent Evaluation Harness ("Proving Ground")
│   ├── src/harness/               # DeepEval scoring, calibrated G-Eval judge, regression diffs
│   ├── data/                      # Audited golden sets, judge calibration labels (Cohen's kappa)
│   ├── scripts/                   # FinanceBench, ConvFinQA, CUAD benchmark runners
│   └── tests/                     # 51 passing unit tests
├── cockpit-ui/                    # Visual Studio: Interactive Agentic Cockpit
│   ├── index.html                 # Cisco-inspired dark theme studio
│   ├── js/                        # Force-directed graph engine & dual-mode API bridge
│   └── styles.css                 # Custom responsive grid styling
└── roadmap/                       # Optimization Roadmaps & RFCs
    └── p5-cost-optimization/      # Architecture RFC: Model routing & speculative decoding
```

---

## 📄 License

This repository is licensed under the [MIT License](LICENSE).
