# Portfolio v0.2 — Evidence-grounded financial Agentic Graph RAG

**Owner:** Venkat. **Role of this document:** implementation handoff to a separate Codex session. **Assessment dates:** 2026-09-06–07. **Base commit:** `2ae5937`; assess the working tree on `codex/model-routing`, including the approved model and reranker changes. This is an enterprise-oriented portfolio release, not a claim of production certification.

## 1. Objective and scope

Build a financial-document research assistant that answers with verifiable evidence, performs explicit calculations, asks for missing scope, and refuses unsupported requests. Demonstrate where agentic research and the financial graph help, and where they do not, using reproducible runs and honest failure analysis.

The deliverable is one focused financial application and its evaluation harness. Preserve the separate legal/FinanceBench assets but do not expand them in v0.2. Do not add providers, agents, databases, authentication frameworks, or UI polish solely to make the architecture look larger. Do not change expected answers to make the system pass.

The user explicitly excludes the 50-case hiring set from execution. Use the new 25-case diagnostic for the assessment. Older sets are reviewed for coverage and overlap only unless later authorized.

## 2. Actual corpus and evaluation assets

- Active financial index: 25 annual SEC filings, 8,419 chunks. The graph API exposes 786 nodes and 1,660 edges.
- The manifest includes Apple, Microsoft, Amazon, Alphabet, Meta, NVIDIA, Tesla, JPMorgan, Bank of America, Goldman Sachs, Walmart, Costco, Johnson & Johnson, Pfizer, UnitedHealth, Exxon Mobil, Chevron, Coca-Cola, PepsiCo, Procter & Gamble, Disney, Netflix, Boeing, Caterpillar, and Home Depot.
- New diagnostic: `p1-eval-harness/data/diagnostics/portfolio_v02/questions_25.jsonl`: 20 answerable cases, three refusals, two clarifications. Answerable evidence spans 11 companies; this is not coverage of all 25 companies.
- References and rubrics: `evidence_25.json` and `README.md` in the same directory. These include exact indexed passages, source URLs, hashes, calculation provenance, and nearest existing questions.
- Existing financial sets: 50 hiring cases and 45 multi-hop cases. Existing calibration: 52 labels, with no unanswerable-category examples. Legal set: 56 cases. FinanceBench's separate index is outside the active 25-document corpus.
- The new set is assistant-authored after examining existing cases. It is a diagnostic/development set, not an independently held-out benchmark and not a human-calibrated gold standard. Once used for fixes, keep calling it a regression/diagnostic set.

**Metadata defect:** Home Depot's inline-XBRL `DocumentFiscalYearFocus` is 2025, but the active index identifies it as `HD_2026_10K`. A period ending in calendar 2026 does not necessarily mean fiscal 2026. Correct this through an explicit versioned ingestion migration, not a blind rename of citations.

## 3. Approved model and retrieval profile

| Role | Model | Required behavior |
| --- | --- | --- |
| Synthesis | `google/gemini-3.8-flash` | Grounded final answer and exact source references |
| Planning | `openai/gpt-5.6-luna` | Scoped, deduplicated subquestions and explicit calculation requirements |
| Runtime/extraction | `qwen/qwen3.8-flash` | Bounded research/tool calls, extraction, runtime audit |
| Evaluation judge | `openai/gpt-5.6-luna` | Calibrated semantic scoring; never the only evidence of correctness |
| Embedding | `BAAI/bge-small-en-v1.5` | Keep current index for the first controlled comparison |
| Reranker | `BAAI/bge-reranker-v2-m3` | Apply the configured model consistently in all retrieval paths |

Provider compatibility established during smoke tests: omit unsupported `temperature` for Luna. Qwen structured calls require thinking disabled because Instructor forces tool selection, which its thinking mode rejects. Native tool-loop compatibility must be measured separately; passing one structured audit is insufficient.

Reranker selection has been repaired for the researcher's filtered/unfiltered searches and the standard pipeline's direct/decomposed searches. Switching configured rerankers replaces the cached model. The new model loaded locally and ranked a relevant synthetic passage above an irrelevant passage. This proves loading/basic behavior, not retrieval improvement.

## 4. Required architecture

Retain the existing package boundaries: P3 owns ingestion, retrieval, graph facts, orchestration and the application; P1 owns datasets, scoring, calibration, traces and reports.

A query follows these explicit states:

1. Validate and resolve scope: company, fiscal period(s), metric and desired operation.
2. Clarify if required scope is missing; otherwise form a deduplicated bounded plan.
3. Retrieve via hybrid search and the configured reranker; use graph facts only when their provenance and scope match.
4. Derive requested quantities using a deterministic calculator with typed inputs and units.
5. Synthesize an answer supported by retrieved or derived evidence.
6. Verify every material claim and citation. Retry within a fixed budget only when new evidence or a correctable issue exists.
7. Return exactly one outcome: `answered`, `clarification_needed`, `insufficient_evidence`, or `error`.

An audit failure after the retry limit must not return an ordinary successful answer. The current orchestrator can reach END with `verified=false`, an answer still present and `refused=false`; remove that ambiguity.

## 5. Implementation work packages

### P0-A — Scope, fiscal periods and provenance

Use a typed fiscal-period identity distinct from filing date and calendar year. Keep `source_document_id`, source hash, filing date, fiscal label, period-end date and parser/index versions. Validate against inline-XBRL fiscal metadata when present. Handle continuation fragments when reading XBRL dates.

For the Home Depot correction, produce an old-to-new citation mapping and rebuild affected index/graph artifacts with explicit versions. Identify impacted golden cases before changing labels; preserve old run artifacts.

**Acceptance:** every manifest filing has an existing file, a content hash and a reconciled fiscal identity. Tests distinguish Home Depot FY2025 ending in 2026 from Walmart/NVIDIA fiscal 2026. No unresolved citation references after migration.

### P0-B — Plans, calculations and answer states

Deduplicate subquestions, reject empty plans, and cap tool iterations and output tokens. A request to combine percentages must trigger calculation even if it lacks the existing keyword-list terms. The NVIDIA concentration case supplies 22% and 14%; refusing because the sum is not printed verbatim is an incorrect refusal.

Reconcile the synthesis prompt's permission to derive results with its later exact-copy/refusal instructions. Make supported calculation an explicit operation with evidence, rather than hoping the model resolves conflicting instructions. Do not attribute the observed refusals solely to the generation model without a controlled prompt/model comparison.

Represent derived evidence as operation, typed inputs, units, period/company scope, source chunk IDs and computed result. Distinguish percentage points from relative percent change; preserve uncertainty when inputs are rounded. The Tesla production/delivery difference is approximate, not an exact unit count.

Short-circuit clarification/out-of-corpus branches before unnecessary synthesis/audit calls. If verification fails, return an explicit unsuccessful outcome with diagnostic details; do not present unsupported prose as a verified answer.

**Acceptance:** deterministic tests cover addition, ratios, revenue deltas, negative segment losses, percentage-point differences, cross-company fiscal comparisons and rounded quantities. Missing company/year produces an actionable clarification. Audit exhaustion and invalid citations cannot produce a successful `answered` status.

### P0-C — Trustworthy evaluation

Pass the case rubric to the semantic scorer. Score each required claim and each necessary evidence source; do not award multi-part correctness merely because one expected number appears. Citation existence is different from citation support. A wrong answer containing the right number must fail.

Separate clarification from refusal scoring. `refused=true` is not evidence that an ambiguous question was handled correctly. Record both harness score and manual rubric adjudication on the 25-case diagnostic until scoring is corrected.

Calibrate Luna on the existing human labels, then add independently human-reviewed unanswerable, contradictory, numerical-scope and misleading-citation examples. Report agreement, Cohen's kappa, class-wise errors, missing-score rate and the actual number of judged cases. Do not treat API or parsing errors as substantive incorrect labels or silently omit them from denominators.

Remove hardcoded trace provenance labels such as `golden_verification: v1 proven` when the executed dataset is the new diagnostic. Save dataset hash and provenance classification instead.

The generated scorecard also contains a hardcoded paragraph about the old 50-case set. Generate this paragraph from the executed dataset metadata. Report metric coverage beside each average: the present graph run's 100% faithfulness average covers only five successful metric outputs, with eight parsing failures.

**Acceptance:** planted wrong unit, wrong company/year, swapped table columns, missing second claim, invented citation and generic refusal on ambiguity fail their rubrics. A recommended release threshold is at least 85% judge agreement and kappa 0.65 on a documented human sample; publish lower values if achieved and retain manual adjudication. These thresholds are targets, not current measurements.

### P0-D — Spend, retries and observability

Move temporary assessment logging/budget protections into a tested application-level request layer only in the implementation session. Cover plain completions, Instructor retries, native tool loops and P1 judging. Log each request before sending it, including role, actual model/provider, attempt, token cap and run/query identifiers. Never log keys or authorization headers.

Capture every attempt's tokens, reasoning tokens when reported, latency, error class and cost. Unknown cost is null/unknown, not zero. Aggregate planning, rewrite, graph extraction, synthesis, audit and judge costs without dropping nested calls or double-counting Instructor usage.

Implement per-request, per-query and per-run limits with reservations for in-flight calls. Retry transient 429/5xx responses with bounded backoff and server hints; fail fast for invalid request parameters and exhausted credit. Do not let SDK retries bypass accounting. Distinguish transport latency from model and retrieval latency.

Verify the observer/budget layer at startup and fail closed if unavailable. A temporary `PYTHONPATH` directory disappeared between assessment sessions; Python silently ignored it and the resumed agent attempt ran without its call ledger. Store production accounting in the application, not an optional temporary startup hook. The temporary observer uses only a process-local lock, so assessment jobs sharing its ledger must run sequentially; production needs atomic reservations across workers.

**Acceptance:** forced validation retry and rate-limit tests reconcile attempt totals with the ledger. A budget crossing stops before sending the next request. Cancellation writes a partial-run manifest. Error rows retain elapsed time and incurred costs. The fifth consecutive error must be persisted before a circuit breaker aborts.

### P1-A — Retrieval evidence and reranker comparison

Compare BGE-base and v2-m3 on identical candidate pools, embedding/index versions and the 20 answerable diagnostic cases. Report any-required-source recall@8, all-required-source recall@8, MRR/nDCG when relevance labels support them, and warm/cold latency. A single correct source is inadequate for multi-source questions.

Keep reranking separate from generation changes in the ablation. Record actual loaded reranker identity, model revision, top-k and candidate count. Do not infer model quality from a successful download or unrelated published benchmarks.

**Acceptance:** the configured reranker reaches direct, decomposed, filtered and retry searches. Report a complete comparison, including regressions and latency tradeoffs; prefer the model supported by evidence rather than declaring v2-m3 superior in advance.

### P1-B — Application and trace continuity

Make index paths resolve relative to project/config roots so the application can start from either repository root or P3. Propagate requested `top_k` or reject it explicitly. Persist the same query/trajectory identity from the HTTP request through orchestration and history. The current construction can create an orchestrator without its memory manager while the UI reads trajectories from memory.

Use one response contract across graph and agent strategies. Show verification status, citations and calculation provenance, and label any recorded demo data. For a public demo, constrain inputs and spend and provide an explicit access-control/deployment decision. Keep the present local assessment distinct from a production security claim.

**Acceptance:** real HTTP query, follow-up, clarification, unsupported request and failure paths return coherent statuses. A completed agent query has a retrievable non-empty trajectory. Concurrent requests do not share mutable query state. Blocking inference does not silently freeze all API work.

## 6. Reproducible release evidence

Each published run must include commit plus dirty-tree patch/hash, full resolved model profile, corpus/index/graph/reranker versions, dataset hash, UTC start/end times, exact command, per-call ledger, per-case traces, scorecard, error counts and missing-metric coverage.

Publish a graph-versus-agent comparison on the same 25 cases, plus manual adjudication for the multi-claim and clarification rubrics. Report correct answers, incorrect answers, incorrect refusals, correct refusals, actionable clarifications, errors and unsupported answers separately. Cite concrete failure cases and one measured improvement. Do not recycle the old 80-case or 50-case headline scores as results for this model profile.

Before claiming generalization, freeze a new independently reviewed set of unseen questions and preferably unseen filings. Do not tune on that set; the 25-case diagnostic remains useful for regression testing.

## 7. Handoff order and release gate

1. Read the assessment logs and reproduce the reported failures.
2. Fix P0-A through P0-D with focused tests and small commits.
3. Complete P1-A/P1-B and rerun the authorized diagnostic under an explicit budget.
4. Publish a concise architecture diagram, reproducible scorecard, honest failure analysis and a short real demonstration.

Recommended release gate: all relevant offline tests pass; zero successful answers with failed verification; all scope/clarification outcomes satisfy their rubrics; per-call cost reconciles; all 25 cases are accounted for, including errors; and every advertised metric links to a saved run. Do not conceal a poor accuracy number or missing metric to meet a deadline.

The intended resume claim is a verifiable system description followed by the actual measured results, corpus size and limitations. Avoid the unqualified phrase “production-grade” until production controls and operational evidence exist.

## 8. Assessment run results

### Completed graph diagnostic

Run: `p1-eval-harness/reports/v02-assessment/graph25/20260906-083613-2ae59379-hybrid_rerank_graph`. All 25 new cases completed; the 50 hiring cases were not executed.

| Measure | Observed result |
| --- | --- |
| Existing harness correctness | 17/25 (68%) |
| Assistant rubric review | 16/25 (64%); not independent human adjudication |
| Correct answers on answerable cases | 13/20 |
| Incorrect refusals on answerable cases | 7/20 |
| Correct out-of-corpus refusals | 3/3 |
| Actionable clarifications under the explicit rubric | 0/2 |
| Application case errors | 0/25 |
| Any annotated source retrieved, answerable cases | 17/20 |
| All annotated sources retrieved, answerable cases | 16/20 |
| Application latency p50 / p95 | 18.8s / 65.7s; local run, not a load test |
| API ledger | 123 requests; $0.28332826 reported cost; zero unknown-usage responses in this graph batch |

Exact annotated-source coverage is narrower than exhaustive semantic relevance: alternative passages can support the same fact. It is also not a controlled base-versus-v2 reranker ablation. The harness label “citation faithfulness” is based on citation matching and must not be presented as independently verified semantic support.

The assistant review differs from the harness on case 024: the system identifies missing company/year but does not ask for them, failing the dataset's explicit clarification rubric. Case 025 silently picks FY2024–FY2025 and fails both assessments. Review details: `p1-eval-harness/reports/v02-assessment/graph25_rubric_review.json`.

Failures 002, 003, 005, 006 and 018 cite available inputs in their refusal explanations but decline to derive the requested result. Case 016 fails the cross-company revenue-increase comparison. Case 017 reports missing Costco context, so investigate retrieval/decomposition coverage before changing synthesis. These are distinct failure modes; a blanket relaxation of refusal is inappropriate.

Complementary DeepEval coverage: faithfulness averages 1.0 on **5 successful outputs**, with **8 invalid-JSON errors**; answer relevancy averages 1.0 on 13 outputs; contextual precision averages approximately 0.883 on 13 outputs. These metrics were not measured on all 25 cases and Luna has not been recalibrated on human labels for this profile. Preserve the original scorecard as evidence of the reporting defect; do not publish its unqualified 100% headline.

### Agent attempt and limits

The `agent_react` comparison was attempted on the same 25 cases on September 7. Three completed case records contain upstream Qwen 429 errors; the fourth case was interrupted and 21 were unattempted. The repeated failures identify provider availability as a blocker. There is **no completed agent accuracy score or graph-versus-agent quality comparison** for this model profile.

Artifacts: `p1-eval-harness/reports/v02-assessment/agent25/console.log`, its timestamped results/traces, and `partial_run_status.json`. The temporary request observer was absent during this resumed attempt, so its total calls and cost are unknown. Harness error rows recording zero cost/latency do not establish zero spend or zero elapsed time. The observer was restored from the saved artifact and subsequent launches explicitly import it before starting.

Do not switch models merely to manufacture a completed comparison. After provider recovery, first run a bounded native-tool compatibility probe with no automatic retries, then complete the comparison with a verified ledger. Repeated 429s should result in a documented partial run, not 25 nominal quality failures.

### Verification and readiness

Offline tests after the reranker-routing repair: **169 P3 tests and 43 P1 tests passed**, one warning in each suite. The local reranker loaded and performed inference. At the time of that run, base-versus-v2 quality/latency comparison was unmeasured; see Section 10 for the subsequent controlled comparison.

HTTP GET checks passed for the application, presets, graph and history. A real browser-submitted Apple distribution-channel query returned HTTP 200 and rendered the correct 40% direct / 60% indirect answer with citation `AAPL_2025_10K:Item1:c002` and two verified claims. The UI showed 25.1 seconds; the single Gemini call reported $0.00488025. The browser rendered the graph and controls, with no captured browser console warnings/errors. These checks do not establish production availability, concurrent request safety, successful agent trajectories, or complete conversational-path coverage. Live query logs, DOM snapshot and screenshot are saved under `p1-eval-harness/reports/v02-assessment/http-live`.

The complete graph batch plus the recorded live UI call total **$0.28820851** in reported API cost. Earlier compatibility probes reported another $0.0015876, with two error responses lacking usage. The aborted September 7 agent attempt also has unknown spend; therefore **$0.28979611 is a known subtotal, not an exact total bill**. The saved ledger covers only the requests it observed.

The reproducibility bundle includes `assessment_manifest.json`, `assessed-working-tree.patch`, `assessment_call_observer.py`, API JSONL logs, console logs, original scorecards and per-case traces under `p1-eval-harness/reports/v02-assessment`. Reports are locally generated artifacts and may be Git-ignored; explicitly include a reviewed evidence bundle when publishing the portfolio.

**Architect's assessment:** about **6/10 as a portfolio engineering project**, and **3/10 for demonstrated enterprise operational readiness**. These are qualitative project ratings, not a rating of the owner or a prediction of hiring outcomes. There is substantial real work: local retrieval/reranking, graph provenance, tool orchestration, a UI and an evaluation harness. The gaps are material: unnecessary refusals, ambiguous-query handling, overstated metric coverage, provider reliability and incomplete accounting. The next release should prove one measured improvement and truthful failure reporting before expanding the architecture.

No implementation beyond the explicitly requested model/reranker work was added during this architectural assessment. The next coding session should follow the work packages above.

## 9. Updated assessment scope — partial execution

The user subsequently requested 25 questions from the existing enterprise set in addition to the original 25. The next assessment therefore uses `p1-eval-harness/data/diagnostics/portfolio_v02/assessment_50.jsonl`: 39 answerable cases, six refusals and five clarifications. The original 50-case hiring dataset remains excluded. All measured results in Section 8 still refer to the earlier 25-case diagnostic; they must not be relabeled as 50-case results.

The selected enterprise records retain their original IDs, wording and references. Selection details, known label-review requirements, source hashes and the complete question list are in `enterprise_selection.json` and `ASSESSMENT_50.md` beside the dataset. Report core-25 and enterprise-25 separately. Both are diagnostic/development sets, not independent holdouts.

Running all 50 questions through graph and agent strategies means 100 application runs, with additional requests for judging and compatibility checks. The agreed $2 assessment ceiling is unchanged; verify accounting, estimate cost from probes and preserve partial results if provider availability or budget prevents completion. No new paid execution was performed while preparing this selection.

## 10. Phase 2 evidence — September 9 continuation

The 50-case graph/agent assessment is partial and stopped after another Qwen upstream capacity error. Current coverage: graph 16 completed, one application parse error and 33 unattempted; agent one completed, one provider interruption and 48 unattempted. No enterprise application case has run. The phase reports $0.25548232 across 136 requests, plus $0.00326025 reserved for two responses lacking usage, against the unchanged $2 ceiling. See `p1-eval-harness/reports/phase2-assessment/ASSESSMENT.md` and `summary.json`. Its separate cumulative ledger and preserved attempts are under `p1-eval-harness/reports/phase2-assessment`; do not combine it with Section 8 to claim a completed 100-run comparison. Configuration, dataset, chunk corpus and graph hashes still matched the phase manifest on September 9. A single Qwen recovery request succeeded before resumption; completed cases were skipped and interrupted attempts preserved.

### Controlled local reranker comparison

All 39 answerable cases used identical original-query hybrid top-25 candidate pools, then top-eight results. No query decomposition, metadata filtering, graph expansion or answer generation was applied in this comparison.

| Group | Hybrid top eight: all annotated sources | Base reranker | V2-M3 reranker | Base / V2-M3 median reranking time |
| --- | --- | --- | --- | --- |
| Core diagnostic, 20 cases | 16/20 | 17/20 | 17/20 | 2.11s / 8.61s |
| Enterprise selection, 19 cases | 9/19 | 14/19 | 15/19 | 2.10s / 7.79s |

V2-M3 improved annotated all-source coverage on core 016 and enterprise 1011/1012, but missed the original annotations on core 015 and enterprise 1024. Targeted passage review found sufficient alternative inputs in both apparent regressions: Google Cloud revenues in `GOOGL_2025_10K:Item8:c036` and Costco net sales in `COST_2025_10K:Item7:c007`. Therefore these two annotation misses are not demonstrated evidence losses. See `reranker/regression_review.json`; this targeted review does not replace exhaustive relevance labeling. Its first-relevant-source reciprocal rank also improved in both groups. Core references identify exact chunks; enterprise references identify section prefixes. Neither annotation scheme is exhaustive semantic relevance. Local timings include first-query inference warmup and are not a production throughput test.

Architectural recommendation: retain a configurable reranker and favor the base model for a latency-sensitive local demo unless the marginal V2-M3 coverage gain improves end-to-end answers. This assessment keeps the approved V2-M3 profile unchanged. Evidence: `reranker/summary.json`, `reranker/hybrid_baseline.json`, frozen candidate pools, scores and model revisions in the phase report directory.

### Confirmed calculation-to-answer failure

On resumed core case 003, the math tool computed `(5323 - 4828) / 4828 * 100 = 10.2527` and explained the $495 million increase. The final generation path nevertheless refused because the dollar difference was not explicitly stated in the source. This isolates a synthesis/derivation policy failure after successful evidence retrieval and calculation. Repeated generation attempts did not repair it. Link this evidence to issue #7; do not treat it as a reranker failure or weaken unrelated refusal safeguards.

All paid requests are announced before dispatch. Application wall times include those notification waits and must not be published as ordinary production latency; the transport ledger records network latency separately and records notification wait duration from call 29 onward. Missing provider usage remains explicitly reserved rather than reported as zero cost.

### Judge scale contract defect — release blocker

The rendered correctness prompt simultaneously requests an integer score from 0 to 10 (DeepEval's contract) and a score from 0 to 1 (the application's final evaluation step). DeepEval normalizes by dividing by 10. An offline mock returning `score: 1` with a fully correct explanation reproduces a final `0.1` and `correct: false`. The paid PepsiCo core-008 result exhibits exactly that disagreement: its explanation confirms every required claim, while its stored score fails. Original raw API response content was not captured, so the reproduction establishes the contract defect and a plausible mechanism, not a verbatim reconstruction of that response.

Treat existing correctness aggregates as **original harness outputs requiring adjudication**, not trustworthy application accuracy. Do not multiply every score by ten: some responses already follow the 0–10 instruction. The coding session must unify the score contract, verify normalization with offline boundary fixtures, and recalibrate against independent labels before a new judge score is advertised. Preserve current raw answers for later rescoring. Evidence: `judge_scale_reproduction.json` and `judge_scale_prompt.txt` in the phase directory. Extend issue #3 with this defect.

### Agent evidence visibility and stopping behavior

The first completed agent application answer correctly reports Apple's 40% direct / 60% indirect distribution mix. Its researcher retrieved `AAPL_2025_10K:Item1:c002` at step zero, then continued searching through its six-step loop. The search tool exposes only the first 600 characters, while the two requested figures occur at offsets 1511 and 1519. Available tools are search, filing inventory and graph queries; there is no chunk-reading tool. The final generator receives the full evidence and answers correctly.

Add a bounded read-by-chunk-ID capability and an evidence-sufficiency stopping rule to the implementation backlog. This is an observed visibility gap and repeated-work pattern; measure the intervention before claiming a latency improvement. Do not expose arbitrary file reads or let the agent invent citation IDs. Preserve requested ticker/year scope, budget each call, and report search/read steps separately. Evidence: `researcher_evidence_visibility.json` and the original agent case-001 trace in the phase directory.
