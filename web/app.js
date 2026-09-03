// Master Portfolio Interactive Application Logic

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initQueryPlayground();
  initPipelineInspector();
});

// 1. Navigation Tab Switching
function initTabs() {
  const navBtns = document.querySelectorAll('.nav-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');

      navBtns.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const activeContent = document.getElementById(targetTab);
      if (activeContent) {
        activeContent.classList.add('active');
      }
    });
  });
}

// 2. Interactive Query Playground Data & Logic
const QUERY_DATABASE = {
  "What is the 3-year average net sales growth rate for Apple from FY2023 to FY2025?": {
    hybrid_rerank_graph: {
      answer: "Apple's total net sales were $383,285 million in FY2023, $391,035 million in FY2024, and $416,161 million in FY2025 (CAGR 4.2%/yr). Fact-graph injection supplied the endpoint pair + provenance chunks up front, so synthesis grounds the derived figure instead of refusing.",
      citations: ["AAPL_2025_10K:Item8:c000", "AAPL_2025_10K:Item8:c015", "graph:val:AAPL:net_sales:2023/2025"],
      confidence: "graph-grounded (illustrative demo)",
      latency: "illustrative",
      cost: "illustrative ($0.00 on free models)",
      math: "Grounded derived line: CAGR 4.20% from $383,285M → $416,161M"
    },
    hybrid_rerank: {

      answer: "Apple's total net sales were $383,285 million in FY2023, $391,035 million in FY2024, and $416,161 million in FY2025. The year-over-year growth rates were 2% for FY2024 compared to FY2023, and 6% for FY2025 compared to FY2024. The average of these two annual growth rates is 4%.",
      citations: ["AAPL_2025_10K:Item7:c003", "AAPL_2025_10K:Item8:c015", "AAPL_2025_10K:Item8:c000"],
      confidence: "0.815 (Gated OK)",
      latency: "4.1s",
      cost: "$0.0139",
      math: "Executed: (416161-383285)/383285 = 8.58%"
    },
    hybrid: {
      answer: "Net sales changed from $383,285 million in FY2023 to $416,161 million in FY2025 (~8.58% growth).",
      citations: ["AAPL_2025_10K:Item8:c015"],
      confidence: "0.742 (Gated OK)",
      latency: "3.0s",
      cost: "$0.0131",
      math: "Executed: (416161-383285)/383285 = 8.58%"
    },
    dense: {
      answer: "Apple reported total net sales of $416,161 million in fiscal 2025 compared to $391,035 million in 2024.",
      citations: ["AAPL_2025_10K:Item8:c015"],
      confidence: "0.680 (Gated OK)",
      latency: "2.9s",
      cost: "$0.0129",
      math: "None (Missed FY2023 chunk)"
    }
  },

  "Did Nvidia's gross margin percentage increase or decrease in FY2025 compared to FY2024?": {
    hybrid_rerank_graph: {
      answer: "Nvidia's gross margin percentage increased in FY2025 to 75.0%, up from 72.7% in FY2024 (a 2.3pp expansion) — graph-grounded from both endpoint facts.",
      citations: ["NVDA_2025_10K:Item7:c012", "NVDA_2025_10K:Item8:c004"],
      confidence: "graph-grounded (illustrative demo)",
      latency: "illustrative",
      cost: "illustrative ($0.00 on free models)",
      math: "Executed: 75.0 - 72.7 = +2.3pp margin expansion"
    },
    hybrid_rerank: {
      answer: "Nvidia's gross margin percentage increased in FY2025 to 75.0%, up from 72.7% in FY2024 (a 2.3% margin expansion).",
      citations: ["NVDA_2025_10K:Item7:c012", "NVDA_2025_10K:Item8:c004"],
      confidence: "0.892 (Gated OK)",
      latency: "3.8s",
      cost: "$0.0142",
      math: "Executed: 75.0 - 72.7 = +2.3% margin expansion"
    },
    hybrid: {
      answer: "Nvidia reported gross margin of 75.0% in FY2025 compared to 72.7% in FY2024.",
      citations: ["NVDA_2025_10K:Item7:c012"],
      confidence: "0.810 (Gated OK)",
      latency: "2.8s",
      cost: "$0.0130",
      math: "Executed: 75.0 - 72.7 = +2.3%"
    },
    dense: {
      answer: "Nvidia's gross margin was 75.0% in fiscal year 2025.",
      citations: ["NVDA_2025_10K:Item7:c012"],
      confidence: "0.710 (Gated OK)",
      latency: "2.7s",
      cost: "$0.0125",
      math: "None"
    }
  },

  "What is Google's market share in quantum computing according to its 2025 10-K?": {
    hybrid_rerank_graph: {
      answer: "REFUSED: no graph fact and no retrieved chunk support a market-share figure — the system asks for a scoped, answerable question instead of guessing. (Graph abstains on all unanswerables by design.)",
      citations: [],
      confidence: "refused — graph abstained (illustrative demo)",
      latency: "illustrative",
      cost: "illustrative ($0.00 on free models)",
      math: "None (Refused before LLM call)"
    },
    hybrid_rerank: {
      answer: "REFUSED: The retrieved SEC 10-K context does not contain market share percentages for quantum computing. Low retrieval confidence threshold triggered (0.210 < 0.450 min_confidence). Refusal logged to reports/refusals.jsonl.",
      citations: [],
      confidence: "0.210 (REFUSED - Gated OK)",
      latency: "0.8s",
      cost: "$0.0000",
      math: "None (Refused before LLM call)"
    },
    hybrid: {
      answer: "REFUSED: low retrieval confidence: 0.210 < 0.450 threshold.",
      citations: [],
      confidence: "0.210 (REFUSED - Gated OK)",
      latency: "0.7s",
      cost: "$0.0000",
      math: "None"
    },
    dense: {
      answer: "REFUSED: low retrieval confidence: 0.190 < 0.450 threshold.",
      citations: [],
      confidence: "0.190 (REFUSED - Gated OK)",
      latency: "0.6s",
      cost: "$0.0000",
      math: "None"
    }
  },

  "What operating loss did Boeing's Commercial Airplanes segment report in fiscal year 2025?": {
    hybrid_rerank_graph: {
      answer: "Boeing's Commercial Airplanes segment reported an operating loss of $7,079 million in FY2025 (vs a $1,635 million loss in FY2024) — segment figure, graph-grounded with provenance chunks.",
      citations: ["BA_2025_10K:Item8:c018", "BA_2025_10K:Item8:c019"],
      confidence: "graph-grounded (illustrative demo)",
      latency: "illustrative",
      cost: "illustrative ($0.00 on free models)",
      math: "Grounded: segment loss $7,079M (FY2025)"
    },
    hybrid_rerank: {
      answer: "Boeing's Commercial Airplanes segment reported an operating loss of $7,079 million in fiscal year 2025 (compared to an operating loss of $1,635 million in fiscal year 2024).",
      citations: ["BA_2025_10K:Item8:c018", "BA_2025_10K:Item8:c019"],
      confidence: "0.865 (Gated OK)",
      latency: "4.2s",
      cost: "$0.0135",
      math: "Executed: Loss of $7,079 million"
    },
    hybrid: {
      answer: "Commercial Airplanes segment operating loss was $(7,079) million in 2025.",
      citations: ["BA_2025_10K:Item8:c018"],
      confidence: "0.790 (Gated OK)",
      latency: "3.1s",
      cost: "$0.0128",
      math: "None"
    },
    dense: {
      answer: "Commercial Airplanes reported total segment loss in 2025.",
      citations: ["BA_2025_10K:Item8:c018"],
      confidence: "0.650 (Gated OK)",
      latency: "2.8s",
      cost: "$0.0120",
      math: "None"
    }
  }
};

function initQueryPlayground() {
  const chips = document.querySelectorAll('.query-chip');
  const input = document.getElementById('query-input');
  const strategySelect = document.getElementById('strategy-select');
  const runBtn = document.getElementById('run-query-btn');

  chips.forEach(chip => {
    chip.addEventListener('click', () => {
      chips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      const q = chip.getAttribute('data-query');
      input.value = q;
      updateResults(q, strategySelect.value);
    });
  });

  strategySelect.addEventListener('change', () => {
    updateResults(input.value, strategySelect.value);
  });

  runBtn.addEventListener('click', () => {
    updateResults(input.value, strategySelect.value);
  });
}

function updateResults(query, strategy) {
  const outputText = document.getElementById('query-output-text');
  const citationsList = document.getElementById('citations-list');
  const resStrat = document.getElementById('res-strategy');
  const resConf = document.getElementById('res-confidence');
  const resLat = document.getElementById('res-latency');
  const resCost = document.getElementById('res-cost');
  const resMath = document.getElementById('res-math');

  const match = QUERY_DATABASE[query] || QUERY_DATABASE["What is the 3-year average net sales growth rate for Apple from FY2023 to FY2025?"];
  const res = match[strategy] || match["hybrid_rerank"];

  outputText.innerHTML = res.answer;
  resStrat.innerText = strategy;
  resConf.innerText = res.confidence;
  resLat.innerText = res.latency;
  resCost.innerText = res.cost;
  resMath.innerText = res.math;

  citationsList.innerHTML = '';
  if (res.citations && res.citations.length > 0) {
    res.citations.forEach(c => {
      const badge = document.createElement('span');
      badge.className = 'cite-badge';
      badge.innerText = c;
      citationsList.appendChild(badge);
    });
  } else {
    const badge = document.createElement('span');
    badge.className = 'cite-badge';
    badge.innerText = 'None (Refused)';
    citationsList.appendChild(badge);
  }
}

// 3. 6-Stage Pipeline Inspector Data & Logic
const PIPELINE_STEPS = {
  1: {
    title: "Stage 1: User Query & Intent Detection",
    module: "src/ragfilings/domains/financial/query_decompose.py",
    description: "The incoming question is analyzed for financial calculation keywords (e.g. growth rate, CAGR, margin delta, multi-year comparison). If detected, the system flags the query for decomposition and Python math execution.",
    code: `def needs_decomposition(query: str) -> bool:
    q_lower = query.lower()
    return any(kw in q_lower for kw in ("growth rate", "cagr", "average", "margin delta"))`
  },
  2: {
    title: "Stage 2: Multi-Hop Query Decomposition",
    module: "src/ragfilings/domains/financial/query_decompose.py",
    description: "Decomposes a single complex question into discrete, single-point retrieval sub-queries targeting SEC 10-K Item 7/8 tables across separate fiscal years.",
    code: `def decompose_query(query: str, cfg: dict) -> list[str]:
    # Returns [ "Apple FY2023 net sales Item 8", "Apple FY2025 net sales Item 8" ]
    messages = [{"role": "system", "content": "Output JSON array of sub-queries"}]
    return [query] + json.loads(complete(messages))`
  },
  3: {
    title: "Stage 3: Hybrid Retrieval & CrossEncoder Reranking",
    module: "src/ragfilings/retrieval.py",
    description: "First-pass candidate retrieval combines Dense vectors (bge-small-en-v1.5) + BM25 sparse keywords via RRF (Reciprocal Rank Fusion, top 25). Then a CrossEncoder rescores and extracts top high-precision context chunks. Measured: ranker swaps move v1 accuracy only a few points (noise) — the graph is the ~30pp signal.",
    code: `def hybrid_rerank(query: str, top_k=6):
    hits = rrf_merge(dense_search(query), bm25_search(query), top_n=25)
    scores = reranker.predict([(query, h['text']) for h in hits])
    return sorted_by_score(hits)[:top_k]`
  },
  4: {
    title: "Stage 4: Safe Python Financial Math Tool",
    module: "src/ragfilings/domains/financial/math_tool.py",
    description: "Extracts exact figures from retrieved 10-K chunks, generates a Python math expression, and executes it via safe AST parsing to eliminate LLM calculation errors.",
    code: `def compute_financial_math(query, chunks):
    # Safely executes AST math: (416161 - 383285) / 383285 * 100
    expr = extract_math_expression(query, chunks)
    return safe_ast_eval(expr)  # Returns 8.58%`
  },
  5: {
    title: "Stage 5: Grounded Claim Verification Pass",
    module: "src/ragfilings/domains/financial/verification.py",
    description: "Re-finds every numerical claim in the model's generated answer against the cited 10-K chunks using regex figure matching ($416.2B vs $416,161M). One corrective retry is issued if any claim fails.",
    code: `def verify(answer_text: str, cited_chunks: list[dict]) -> dict:
    claims = extract_claims(answer_text)
    for c in claims:
        c["found"] = check_in_chunks(c, cited_chunks)
    return {"verified": all(c["found"] for c in claims)}`
  },
  6: {
    title: "Stage 6: Cited Output & Harness Scoring",
    module: "p1-eval-harness/src/harness/metrics/engine.py + judge.py",
    description: "Outputs the final grounded answer with [chunk_id] citations. Every case is scored by the eval harness: deterministic numeric matching with variation rules + refusal/ambiguity matrix, complemented by a calibrated G-Eval judge (88.5% human agreement). Full trajectory traces land in reports/evals/<run>/ — see the scorecards section.",
    code: `return {
    "answer": text, "citations": cited_ids,
    "trace": {"retrieval": hits, "graph_rescue": outcome, "usage": usage}
}`
  }
};

function initPipelineInspector() {
  const stepBtns = document.querySelectorAll('.step-btn');
  const title = document.getElementById('step-title');
  const moduleTag = document.getElementById('step-module-tag');
  const desc = document.getElementById('step-desc');
  const code = document.getElementById('step-code');

  stepBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      stepBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const stepNum = btn.getAttribute('data-step');
      const info = PIPELINE_STEPS[stepNum];

      if (info) {
        title.innerText = info.title;
        moduleTag.innerText = info.module;
        desc.innerHTML = info.description;
        code.innerHTML = `<code>${escapeHtml(info.code)}</code>`;
      }
    });
  });
}

function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
