# AI Engineering Interview Master Cheatsheet

> **Tactical Interview Guide for Senior / Staff AI Engineer & Agentic RAG Roles**  
> *Repository:* `enterprise-agentic-rag-eval`  
> *Author:* Venkat

---

## 1. The 60-Second Elevator Pitch

> *"Most enterprise RAG pipelines fail when deployed against financial filings because standard vector search is blind to multi-column tables, LLMs hallucinate mental arithmetic, and models silently guess on ambiguous queries.*  
> 
> *I built an **Enterprise Agentic Graph RAG** system over messy SEC 10-K filings that solves this through a **Neuro-Symbolic architecture**:*  
> 1. *A **table-aware parser and typed fact graph** where every financial figure maintains immutable chunk provenance back to the source table.*  
> 2. *A **LangGraph multi-agent loop** that uses an isolated Python AST tool for exact mathematical derivation and a cyclic audit guard that rejects unverified claims.*  
> 3. *A **two-tier evaluation harness** using DeepEval and a calibrated G-Eval judge that achieved an **88.5% human agreement ($\kappa = 0.723$)**, reaching **98.0% accuracy** on our canonical enterprise suite and **86.7% on FinanceBench** at less than **$0.008 per query**."*

---

## 2. The 5 Toughest Technical Questions & Winning Answers

### Q1: "Why did you build your own Fact Graph instead of just relying on GraphRAG or a standard Vector DB?"
**Winning Answer:**
> *"Off-the-shelf GraphRAG (like Microsoft's) relies heavily on LLMs to extract entity-relation triples from free text. That works well for narrative documents, but in SEC 10-K filings, it's both extraordinarily expensive and prone to numerical hallucination.  
> 
> Instead, I built a **typed fact layer extracted deterministically from financial statement tables**. Every node (`Company` $\to$ `Filing` $\to$ `FinancialMetric` $\to$ `MetricValue`) is parsed directly from aligned table columns and tagged with its source chunk ID. When a user asks about Apple's FY2025 net sales, we don't gamble on an embedding search finding the right row—we inject the exact table fact and its source chunk upfront. This eliminated the single biggest failure mode in our baseline: false refusals caused by missed retrieval chunks."*

---

### Q2: "Are you doing hardcoding or prompt engineering?"
**Winning Answer:**
> *"We use a **Neuro-Symbolic architecture** with an intentional division of labor:  
> - **The Deterministic Layer (Fast-Path & Guardrails):** Clean factual lookups (ticker + metric + year) and obvious ambiguities (missing year, missing peer comparison set) are handled by a zero-token, zero-latency (<15ms) triage router. In production, paying $0.03 and 4 seconds of latency just to have an LLM say 'Which fiscal year?' is poor engineering.  
> - **The Neural Layer (LangGraph Multi-Agent):** Complex, open-ended analytical queries (e.g., cross-company margin analysis, driver synthesis, multi-hop trends) bypass triage completely. The **Planner Agent** uses Instructor-validated Pydantic models to decompose queries into sub-questions, and the **Synthesis Agent** reasons over multi-chunk evidence.  
> - **The Symbolic Math Tool:** All arithmetic (YoY change, CAGR, margin gaps) is computed via an isolated Python AST interpreter, not LLM token prediction.  
> 
> Every figure cited by the neural model is deterministically audited against the retrieved chunk IDs before being returned."*

---

### Q3: "Why did you choose LangGraph over standard LangChain or LlamaIndex?"
**Winning Answer:**
> *"Linear DAGs (like vanilla LangChain chains) cannot handle real-world failures. If an LLM hallucinates a number or generates a citation to a chunk it didn't use, a linear chain returns bad data to the client.  
> 
> LangGraph gave us three critical enterprise primitives:  
> 1. **Cyclic State Loops:** Our `audit` node verifies candidate figures against cited chunks. If verification fails, a conditional edge routes back to `synthesize` with targeted error feedback up to a bounded retry limit.  
> 2. **Explicit Typed State (`OrchestratorState`):** Every node is a pure function over state, passing structured Pydantic objects instead of loose prompt strings.  
> 3. **Deterministic Branching:** We can instantly short-circuit out of the graph when confidence is below threshold (<0.35) or when scope is ambiguous, saving token cost and eliminating hallucinations."*

---

### Q4: "How did you calibrate your evaluation judge, and why does Cohen's Kappa matter?"
**Winning Answer:**
> *"Many AI developers treat LLM-as-a-judge as ground truth. But LLM judges suffer from position bias, length bias, and over-refusal bias.  
> 
> To prove our evaluation harness was statistically reliable, I created a hand-labeled calibration dataset across SEC 10-K answers:  
> - We measured agreement between the G-Eval judge (`openai/gpt-5.6-luna`) and human expert labels.  
> - We achieved **88.5% raw agreement** and a **Cohen's Kappa ($\kappa$) of 0.723**, which indicates 'Substantial Agreement' beyond random chance.  
> - We also identified the exact failure mode of the judge: it was biased toward penalizing enumeration-style answers on ambiguous queries. Knowing this allowed us to decouple deterministic exact checks (numbers and refusals) from G-Eval semantic checks."*

---

### Q5: "How would you scale this architecture to 50,000 public companies in production?"
**Winning Answer:**
> *"Our current local architecture proves the algorithmic core on 25 filers and 8,400 chunks. To scale this horizontally to 50,000 filers:  
> 1. **Storage Layer:** Replace local NumPy arrays and in-memory BM25 with **Qdrant** or **pgvector** using partitioned HNSW indexes filtered by ticker and fiscal year. Migrate `financial_graph.json` to **Neo4j** for cluster-scale Cypher traversal.  
> 2. **Native XBRL Ingestion:** Rather than parsing raw HTML tables with heuristics, integrate SEC EDGAR's direct **inline-XBRL (iXBRL) JSON/XML API**. XBRL metrics use standardized US-GAAP taxonomies, eliminating table extraction ambiguities at the source.  
> 3. **Distributed Execution:** Decouple ingestion and evaluation using a **Kafka message queue and Celery worker pool**. Wrap LangGraph sessions in FastAPI with Redis session caching and stream token chunks to the frontend via WebSockets/SSE.  
> 4. **Observability:** Instrument all LangGraph nodes with OpenTelemetry into **LangSmith / Arize Phoenix** to monitor p95 latency, prompt drift, and token economics in real-time."*

---

## 3. Key Metrics to Have at Your Fingertips

| Metric | Measured Value | Meaning / Business Impact |
| :--- | :--- | :--- |
| **Canonical SEC 10-K Accuracy** | **98.0% (49/50)** | Accuracy on complex enterprise financial queries. |
| **Hallucination Rate on Unanswerables** | **0.0% (0/6)** | Strict refusal guardrail prevents fabricating numbers. |
| **FinanceBench Evidence Accuracy** | **86.7% (130/150)** | Industry benchmark on public financial filings. |
| **Judge Human Agreement** | **88.5% ($\kappa = 0.723$)** | Statistically validated evaluation reliability. |
| **Cost per Query** | **$0.0076** (< 0.8¢) | Highly cost-effective through fast-path scope triage. |
| **p50 Query Latency** | **7.9s** | Full multi-agent deliberation, hybrid retrieval, and audit. |
| **Deterministic Clarification Latency** | **< 15ms** | Instant scope disambiguation for ambiguous queries. |
