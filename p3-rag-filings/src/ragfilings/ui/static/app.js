/**
 * RAGFilings Intelligence — Enterprise Light-Theme Client Controller
 * 3-Panel Agentic Graph RAG Cockpit (live backend: /api/*)
 */

let financialChartInstance = null;
let allGraphNodes = [];
let allGraphLinks = [];
let selectedCompanyFilter = "ALL";
let currentSessionId = null; // conversational session id

document.addEventListener("DOMContentLoaded", () => {
  initPresets();
  initHistory();
  initKnowledgeGraph();
  setupEventListeners();
  startNewConversation(false); // create a session id (don't clear thread on load)
});

function setupEventListeners() {
  const btnRun = document.getElementById("btn-run-query");
  const queryInput = document.getElementById("query-input");
  const presetSelect = document.getElementById("preset-select");
  const btnRefreshHistory = document.getElementById("btn-refresh-history");
  const btnNewConversation = document.getElementById("btn-new-conversation");
  const graphFilter = document.getElementById("graph-company-filter");

  btnRun.addEventListener("click", () => {
    const q = queryInput.value.trim();
    if (q) executeQuery(q);
  });

  // Chat-style: Enter sends, Shift+Enter newline.
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const q = queryInput.value.trim();
      if (q) executeQuery(q);
    }
  });

  presetSelect.addEventListener("change", (e) => {
    const selectedId = e.target.value;
    if (!selectedId) return;
    const opt = e.target.selectedOptions[0];
    const query = opt.getAttribute("data-query");
    const ticker = opt.getAttribute("data-ticker");
    if (query) {
      queryInput.value = query;
      if (ticker && graphFilter) {
        graphFilter.value = ticker;
        selectedCompanyFilter = ticker;
        filterAndDrawGraph();
      }
      executeQuery(query);
    }
  });

  if (graphFilter) {
    graphFilter.addEventListener("change", (e) => {
      selectedCompanyFilter = e.target.value;
      filterAndDrawGraph();
    });
  }

  btnRefreshHistory.addEventListener("click", initHistory);

  if (btnNewConversation) {
    btnNewConversation.addEventListener("click", () => startNewConversation(true));
  }
}

// -----------------------------------------------------------------------------
// Conversation session management
// -----------------------------------------------------------------------------
async function startNewConversation(clearThread) {
  try {
    const res = await fetch("/api/session/new", { method: "POST" });
    const data = await res.json();
    currentSessionId = data.session_id;
  } catch (err) {
    currentSessionId = null;
  }
  if (clearThread) {
    const thread = document.getElementById("chat-thread");
    thread.innerHTML =
      '<p class="placeholder-msg" id="chat-placeholder">New conversation started. Ask a question — follow-ups stay in context.</p>';
    hideEvidencePanels();
  }
}

function hideEvidencePanels() {
  ["math-card", "tables-card", "visuals-card", "chunks-card"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = "none";
  });
  const cit = document.getElementById("citations-container");
  if (cit) cit.style.display = "none";
  const verifiedBadge = document.getElementById("verified-shield-badge");
  if (verifiedBadge) verifiedBadge.style.display = "none";
}

function appendUserBubble(text) {
  const thread = document.getElementById("chat-thread");
  const ph = document.getElementById("chat-placeholder");
  if (ph) ph.remove();
  const bubble = document.createElement("div");
  bubble.className = "chat-msg chat-user";
  bubble.innerHTML = `<div class="chat-bubble">${formatMarkdownAnswer(text)}</div>`;
  thread.appendChild(bubble);
  thread.scrollTop = thread.scrollHeight;
}

function appendAssistantBubble(data, rewritten) {
  const thread = document.getElementById("chat-thread");
  const bubble = document.createElement("div");
  bubble.className = "chat-msg chat-assistant";

  let re = "";
  if (rewritten && rewritten.trim() && rewritten.trim() !== (data.query || "").trim()) {
    re = `<div class="chat-rewritten" title="Follow-up resolved against the conversation">↳ Interpreted as: ${escapeHtml(rewritten)}</div>`;
  }

  let body;
  if (data.refused) {
    body = `<div class="chat-refusal">${escapeHtml(data.refusal_reason || data.answer || "I can't verify that from the filings.")}</div>`;
  } else {
    body = formatMarkdownAnswer(data.answer || "");
  }

  const meta = `<div class="chat-meta">${(data.latency_ms / 1000).toFixed(1)}s · $${(data.usage?.cost_usd || 0).toFixed(4)} · conf ${(data.confidence * 100).toFixed(0)}%${data.refused ? " · REFUSED" : ""}</div>`;

  bubble.innerHTML = `<div class="chat-bubble">${re}${body}${meta}</div>`;
  thread.appendChild(bubble);
  thread.scrollTop = thread.scrollHeight;
}

// -----------------------------------------------------------------------------
// Presets Loader (10 Serious Financial Benchmark Questions)
// -----------------------------------------------------------------------------
async function initPresets() {
  const select = document.getElementById("preset-select");
  try {
    const res = await fetch("/api/presets");
    const data = await res.json();
    if (data.presets && data.presets.length > 0) {
      select.innerHTML = '<option value="" disabled selected>Select a financial benchmark question...</option>';
      data.presets.forEach((p, idx) => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.innerText = `${idx + 1}. [${p.category}] ${p.title}`;
        opt.setAttribute("data-query", p.query);
        opt.setAttribute("data-ticker", p.ticker);
        select.appendChild(opt);
      });
    }
  } catch (err) {
    console.error("Failed to load presets:", err);
  }
}

// -----------------------------------------------------------------------------
// History Loader (SQLite Durable Memory)
// -----------------------------------------------------------------------------
async function initHistory() {
  const list = document.getElementById("history-list");
  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    if (data.sessions && data.sessions.length > 0) {
      list.innerHTML = "";
      data.sessions.forEach((s) => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.innerHTML = `
          <div class="history-query-text">${escapeHtml(s.query)}</div>
          <div class="history-meta-row">
            <span>${(s.latency_ms / 1000).toFixed(1)}s · $${(s.cost_usd || 0).toFixed(4)}</span>
            <span style="color: ${s.verified ? 'var(--accent-emerald)' : 'var(--accent-rose)'}">${s.verified ? 'Verified' : 'Refused'}</span>
          </div>
        `;
        item.addEventListener("click", () => {
          document.getElementById("query-input").value = s.query;
          executeQuery(s.query);
        });
        list.appendChild(item);
      });
    } else {
      list.innerHTML = '<div class="empty-placeholder">No saved sessions yet.</div>';
    }
  } catch (err) {
    list.innerHTML = '<div class="empty-placeholder">Failed to load memory history.</div>';
  }
}

// -----------------------------------------------------------------------------
// Knowledge Graph Viewer Canvas (Multi-Company & Subgraph Support)
// -----------------------------------------------------------------------------
async function initKnowledgeGraph() {
  try {
    const res = await fetch("/api/graph");
    const data = await res.json();
    allGraphNodes = data.nodes || [];
    allGraphLinks = data.links || [];
    filterAndDrawGraph();
  } catch (err) {
    console.error("Failed to load graph data:", err);
  }
}

function filterAndDrawGraph() {
  let displayNodes = [];
  let displayLinks = [];

  if (selectedCompanyFilter === "ALL") {
    // Show top company hub nodes across the 25 SEC filings
    const companyNodes = allGraphNodes.filter(n => n.type === "Entity" && n.id.startsWith("company:")).slice(0, 15);
    const companyIds = new Set(companyNodes.map(c => c.id));
    
    // Add sample connected metric nodes
    const metricNodes = allGraphNodes.filter(n => n.type === "Entity" && !n.id.startsWith("company:") && companyIds.has(`company:${n.ticker}`)).slice(0, 25);
    displayNodes = [...companyNodes, ...metricNodes];

    const displayIds = new Set(displayNodes.map(d => d.id));
    displayLinks = allGraphLinks.filter(l => displayIds.has(l.source) && displayIds.has(l.target)).slice(0, 35);
  } else {
    // Show selected company ego subgraph
    const ticker = selectedCompanyFilter.toUpperCase();
    displayNodes = allGraphNodes.filter(n => n.ticker === ticker || n.id === `company:${ticker}`).slice(0, 30);
    const displayIds = new Set(displayNodes.map(d => d.id));
    displayLinks = allGraphLinks.filter(l => displayIds.has(l.source) && displayIds.has(l.target));
  }

  drawKnowledgeGraphCanvas(displayNodes, displayLinks);
}

function drawKnowledgeGraphCanvas(nodes, links) {
  const canvas = document.getElementById("knowledge-graph-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);

  if (!nodes || nodes.length === 0) {
    // No graph data from the backend — render nothing rather than fake nodes.
    const canvas = document.getElementById("knowledge-graph-canvas");
    if (canvas) {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.font = "12px Inter, sans-serif";
      ctx.fillStyle = "#94a3b8";
      ctx.textAlign = "center";
      ctx.fillText("Graph unavailable — build it with `ragfilings graph`", canvas.width / 2, canvas.height / 2);
    }
    return;
  }

  // Layout nodes around center
  const cx = width / 2;
  const cy = height / 2;
  const r = Math.min(width, height) * 0.36;

  nodes.forEach((n, i) => {
    if (nodes.length === 1) {
      n.x = cx;
      n.y = cy;
    } else {
      const angle = (i / nodes.length) * 2 * Math.PI;
      const radiusOffset = (i % 2 === 0) ? r : r * 0.65;
      n.x = cx + radiusOffset * Math.cos(angle);
      n.y = cy + radiusOffset * Math.sin(angle);
    }
  });

  const nodeMap = {};
  nodes.forEach(n => { nodeMap[n.id] = n; });

  // Draw Links
  ctx.strokeStyle = "rgba(148, 163, 184, 0.35)";
  ctx.lineWidth = 1;
  links.forEach(l => {
    const src = nodeMap[l.source] || nodeMap[l.source?.id];
    const tgt = nodeMap[l.target] || nodeMap[l.target?.id];
    if (src && tgt) {
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.stroke();
    }
  });

  // Draw Nodes
  nodes.forEach(n => {
    let color = "#4f46e5"; // Indigo default
    let size = 5;
    const isCompany = n.id.startsWith("company:") || n.type === "Company";

    if (isCompany) {
      color = "#4f46e5"; // Company Hub Indigo
      size = 8;
    } else if (n.id.includes("Net") || n.id.includes("Revenue") || n.id.includes("Gross")) {
      color = "#059669"; // Metric Emerald
      size = 6;
    } else if (n.fiscal_year || n.id.includes("202")) {
      color = "#d97706"; // Year Amber
      size = 5;
    } else {
      color = "#0284c7"; // Section Cyan
      size = 5;
    }

    // Outer ring
    ctx.beginPath();
    ctx.arc(n.x, n.y, size + 2, 0, 2 * Math.PI);
    ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
    ctx.fill();

    // Inner node body
    ctx.beginPath();
    ctx.arc(n.x, n.y, size, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();

    // Node Label
    ctx.font = isCompany ? "bold 9px Inter, sans-serif" : "8px Inter, sans-serif";
    ctx.fillStyle = isCompany ? "#0f172a" : "#64748b";
    ctx.textAlign = "center";
    let label = n.label || n.id;
    if (label.startsWith("company:")) label = label.replace("company:", "");
    if (label.startsWith("filing:")) label = label.replace("filing:", "");
    if (label.length > 11) label = label.slice(0, 9) + "..";
    ctx.fillText(label, n.x, n.y + size + 10);
  });
}

// -----------------------------------------------------------------------------
// Live Pipeline-Stage Progress Indicator (timer-driven animation;
// ground truth is the Execution Trace Log rendered from /api/query)
// -----------------------------------------------------------------------------
async function executeQuery(query) {
  const strategy = document.getElementById("strategy-select").value;
  const btnRun = document.getElementById("btn-run-query");
  const queryInput = document.getElementById("query-input");
  const overallStatus = document.getElementById("swarm-overall-status");
  const stepIndicator = document.getElementById("swarm-step-indicator");
  const citationsContainer = document.getElementById("citations-container");
  const mathCard = document.getElementById("math-card");
  const tablesCard = document.getElementById("tables-card");
  const visualsCard = document.getElementById("visuals-card");
  const chunksCard = document.getElementById("chunks-card");
  const thread = document.getElementById("chat-thread");

  btnRun.disabled = true;
  queryInput.value = "";
  appendUserBubble(query);

  // Typing indicator bubble
  const typing = document.createElement("div");
  typing.className = "chat-msg chat-assistant";
  typing.id = "chat-typing";
  typing.innerHTML = '<div class="chat-bubble chat-typing-bubble">Reasoning over SEC filings &amp; the knowledge graph…</div>';
  thread.appendChild(typing);
  thread.scrollTop = thread.scrollHeight;

  overallStatus.innerText = "Running pipeline";
  overallStatus.className = "header-tag active";
  stepIndicator.innerText = "Step 1: Orchestrating & Planning...";
  hideEvidencePanels();

  resetDagNodes();
  setDagNodeState("node-orchestrator", "state-orchestrator", "running");

  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, strategy, top_k: 8, session_id: currentSessionId }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Query execution failed");
    if (data.session_id) currentSessionId = data.session_id;

    typing.remove();

    // Complete DAG Nodes according to actual execution path
    if (data.refused) {
      setDagNodeState("node-orchestrator", "state-orchestrator", "done");
      setDagNodeState("node-researcher", "state-researcher", (data.hits && data.hits.length > 0) ? "done" : "skipped");
      setDagNodeState("node-doc-analyst", "state-doc-analyst", "skipped");
      setDagNodeState("node-data-analyst", "state-data-analyst", "skipped");
      setDagNodeState("node-synthesis", "state-synthesis", "skipped");
      setDagNodeState("node-auditor", "state-auditor", "skipped");
      overallStatus.innerText = "Refused";
      overallStatus.className = "header-tag";
      stepIndicator.innerText = "Refused — query out of scope or low confidence";
    } else {
      setDagNodeState("node-orchestrator", "state-orchestrator", "done");
      setDagNodeState("node-researcher", "state-researcher", "done");
      setDagNodeState("node-doc-analyst", "state-doc-analyst", (data.tables && data.tables.length > 0) ? "done" : "skipped");
      setDagNodeState("node-data-analyst", "state-data-analyst", (data.math_result) ? "done" : "skipped");
      setDagNodeState("node-synthesis", "state-synthesis", "done");
      const hasVerification = data.verification && (data.verification.verified || (Array.isArray(data.verification.claims) && data.verification.claims.length > 0));
      setDagNodeState("node-auditor", "state-auditor", hasVerification ? "done" : "skipped");
      overallStatus.innerText = "Complete";
      overallStatus.className = "header-tag";
      stepIndicator.innerText = "Done — see trace log";
    }

    // Assistant chat bubble (answer or refusal/clarification)
    appendAssistantBubble(data, data.rewritten_query);

    // 1. Render Metadata Chips
    document.getElementById("chip-latency").innerText = `Latency: ${(data.latency_ms / 1000).toFixed(2)}s`;
    document.getElementById("chip-cost").innerText = `Cost: $${(data.usage?.cost_usd || 0.0).toFixed(4)}`;
    document.getElementById("chip-confidence").innerText = `Confidence: ${(data.confidence * 100).toFixed(0)}%`;

    // 2. Verified badge — reflects the numeric-claim verification pass,
    // not a blanket stamp.
    const verifiedBadge = document.getElementById("verified-shield-badge");
    const claimsChecked = data.verification && Array.isArray(data.verification.claims)
      ? data.verification.claims.length : 0;
    if (data.refused) {
      verifiedBadge.innerText = "REFUSED / CLARIFY";
      verifiedBadge.className = "audit-badge refused";
      verifiedBadge.style.display = "inline-flex";
    } else if (data.verification && data.verification.verified) {
      verifiedBadge.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
        </svg>
        <span>AUDITED &amp; VERIFIED (${claimsChecked} claims)</span>
      `;
      verifiedBadge.className = "audit-badge verified";
      verifiedBadge.style.display = "inline-flex";
    } else {
      verifiedBadge.innerText = "ANSWERED · CLAIMS UNVERIFIED — CHECK CHUNKS";
      verifiedBadge.className = "audit-badge refused";
      verifiedBadge.style.display = "inline-flex";
    }

    // 3. Citations
    if (data.citations && data.citations.length > 0) {
      const citList = document.getElementById("citations-list");
      citList.innerHTML = "";
      data.citations.forEach(c => {
        const chip = document.createElement("span");
        chip.className = "citation-chip";
        chip.innerText = c;
        chip.addEventListener("click", () => focusChunk(c));
        citList.appendChild(chip);
      });
      citationsContainer.style.display = "block";
    }

    // 4. AST Math Proof
    if (data.math_result) {
      document.getElementById("math-expression").innerText = data.math_result.expression || "--";
      document.getElementById("math-formatted").innerText = data.math_result.formatted || "--";
      document.getElementById("math-explanation").innerText = data.math_result.explanation || "--";
      mathCard.style.display = "block";
    }

    // 5. Filing tables (regex table parse of retrieved chunks)
    if (data.tables && data.tables.length > 0) {
      renderFilingTables(data.tables);
      tablesCard.style.display = "block";
    }

    // 6. Dynamic Financial Chart (Render only when real metric trajectory exists)
    if (data.chart_data && data.chart_data.labels && data.chart_data.values && data.chart_data.values.length > 0) {
      renderFinancialChart(data.chart_data);
      visualsCard.style.display = "block";
    } else {
      visualsCard.style.display = "none";
    }

    // 7. Chunks Accordion
    if (data.hits && data.hits.length > 0) {
      renderChunksAccordion(data.hits);
      chunksCard.style.display = "block";
    }

    // 8. Trajectory Trace
    if (data.trajectory) {
      renderTrajectoryStream(data.trajectory);
    }

    // Refresh history
    initHistory();

  } catch (err) {
    typing.remove();
    appendAssistantBubble({ refused: true, refusal_reason: `Execution error: ${err.message}`, query, latency_ms: 0, usage: {}, confidence: 0 }, null);
    setDagNodeState("node-orchestrator", "state-orchestrator", "error");
    ["researcher", "doc-analyst", "data-analyst", "synthesis", "auditor"].forEach(name => {
      setDagNodeState(`node-${name}`, `state-${name}`, "idle");
    });
    overallStatus.innerText = "Error";
    overallStatus.className = "header-tag";
    stepIndicator.innerText = "Execution failed";
    const verifiedBadge = document.getElementById("verified-shield-badge");
    if (verifiedBadge) verifiedBadge.style.display = "none";
  } finally {
    btnRun.disabled = false;
    queryInput.focus();
  }
}

// -----------------------------------------------------------------------------
// Component Renderers & Helpers
// -----------------------------------------------------------------------------
function resetDagNodes() {
  ["orchestrator", "researcher", "doc-analyst", "data-analyst", "synthesis", "auditor"].forEach(name => {
    const node = document.getElementById(`node-${name}`);
    const state = document.getElementById(`state-${name}`);
    if (node) node.className = node.classList.contains("node-parallel") ? "dag-node node-parallel" : "dag-node";
    if (state) {
      state.className = "node-state-pill idle";
      state.innerText = "IDLE";
    }
  });
}

function setDagNodeState(nodeId, stateId, state) {
  const node = document.getElementById(nodeId);
  const pill = document.getElementById(stateId);
  if (!node || !pill) return;

  const isParallel = node.classList.contains("node-parallel");
  if (state === "running") {
    node.className = isParallel ? "dag-node node-parallel active-running" : "dag-node active-running";
    pill.className = "node-state-pill running";
    pill.innerText = "RUNNING";
  } else if (state === "done") {
    node.className = isParallel ? "dag-node node-parallel active-done" : "dag-node active-done";
    pill.className = "node-state-pill done";
    pill.innerText = "DONE";
  } else if (state === "error") {
    node.className = isParallel ? "dag-node node-parallel active-error" : "dag-node active-error";
    pill.className = "node-state-pill error";
    pill.innerText = "ERROR";
  } else if (state === "skipped") {
    node.className = isParallel ? "dag-node node-parallel" : "dag-node";
    pill.className = "node-state-pill skipped";
    pill.innerText = "SKIPPED";
  } else {
    node.className = isParallel ? "dag-node node-parallel" : "dag-node";
    pill.className = "node-state-pill idle";
    pill.innerText = "IDLE";
  }
}

function formatMarkdownAnswer(text) {
  if (!text) return "";
  let html = escapeHtml(text);
  // Bold phrases / numbers
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Formatted citations
  html = html.replace(/\[([A-Z0-9_:\.]+)\]/g, '<span class="citation-chip" onclick="focusChunk(\'$1\')">[$1]</span>');
  return `<p>${html.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>')}</p>`;
}

function renderFilingTables(tables) {
  const container = document.getElementById("tables-container");
  container.innerHTML = "";
  if (!tables || tables.length === 0) return;

  tables.forEach(t => {
    const block = document.createElement("div");
    block.className = "extracted-table-block";

    if (t.headers && t.rows && t.rows.length > 0) {
      let tableHtml = `
        <div class="table-block-header">
          <span class="table-block-title">${escapeHtml(t.title || 'Extracted SEC Filing Table')}</span>
          <span class="citation-chip" onclick="focusChunk('${t.chunk_id}')">[${escapeHtml(t.chunk_id)}]</span>
        </div>
        <table class="filing-table">
          <thead>
            <tr>
              ${t.headers.map((h, i) => `<th style="${i > 0 ? 'text-align: right;' : 'text-align: left;'}">${escapeHtml(h)}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
      `;
      t.rows.forEach(row => {
        tableHtml += `
          <tr>
            ${row.map((cell, idx) => `
              <td style="${idx > 0 ? 'text-align: right; font-family: var(--font-mono); font-size: 11px;' : 'font-weight: 500; font-size: 12px;'}">
                ${escapeHtml(cell)}
              </td>
            `).join('')}
          </tr>
        `;
      });
      tableHtml += `</tbody></table>`;
      block.innerHTML = tableHtml;
      container.appendChild(block);
    } else if (t.text) {
      // Fallback for raw text
      const lines = t.text.split("\n").filter(l => l.includes("|"));
      if (lines.length > 0) {
        let tableHtml = `<table class="filing-table">`;
        lines.forEach((line, idx) => {
          const cells = line.split("|").map(c => c.trim()).filter(c => c.length > 0);
          if (cells.length > 0) {
            if (idx === 0) {
              tableHtml += `<thead><tr>${cells.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead><tbody>`;
            } else {
              tableHtml += `<tr>${cells.map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`;
            }
          }
        });
        tableHtml += `</tbody></table>`;
        block.innerHTML = tableHtml;
        container.appendChild(block);
      }
    }
  });
}

function renderFinancialChart(chartData) {
  if (!chartData || !chartData.labels || !chartData.values) return;

  const canvas = document.getElementById("financial-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (financialChartInstance) {
    financialChartInstance.destroy();
  }

  const labels = chartData.labels;
  const values = chartData.values;
  const chartTitle = chartData.title || "Financial Metric Trajectory";

  document.getElementById("chart-card-title").innerText = chartTitle;

  financialChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [{
        label: chartTitle,
        data: values,
        backgroundColor: "rgba(79, 70, 229, 0.15)",
        borderColor: "#4f46e5",
        borderWidth: 1.5,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0f172a",
          titleColor: "#ffffff",
          bodyColor: "#c7d2fe",
          borderColor: "#e2e8f0",
          borderWidth: 1,
          padding: 8,
        }
      },
      scales: {
        x: {
          grid: { color: "#f1f5f9" },
          ticks: { color: "#64748b", font: { family: "Inter", size: 11 } }
        },
        y: {
          grid: { color: "#f1f5f9" },
          ticks: { color: "#64748b", font: { family: "JetBrains Mono", size: 10 } }
        }
      }
    }
  });
}

function renderChunksAccordion(hits) {
  const container = document.getElementById("chunks-list");
  document.getElementById("chunks-count").innerText = `${hits.length} Chunks`;
  container.innerHTML = "";
  hits.forEach(h => {
    const item = document.createElement("div");
    item.className = "chunk-card-item";
    item.id = `chunk-card-${h.id}`;
    item.innerHTML = `
      <div class="chunk-meta-header">
        <strong>${escapeHtml(h.id)}</strong>
        <span>Score: ${h.score.toFixed(3)} · Section: ${escapeHtml(h.section || 'General')}</span>
      </div>
      <div class="chunk-text-box">${escapeHtml(h.text)}</div>
    `;
    container.appendChild(item);
  });
}

function renderTrajectoryStream(steps) {
  const container = document.getElementById("trajectory-log-list");
  document.getElementById("traj-step-count").innerText = `${steps.length} Steps`;
  container.innerHTML = "";
  steps.forEach(s => {
    const stepEl = document.createElement("div");
    stepEl.className = "traj-row";
    stepEl.innerHTML = `
      <div class="traj-row-header">
        <span>Step ${s.step_index} · ${escapeHtml(s.agent_name)}</span>
        <span style="color: var(--accent-indigo); font-weight: 500;">${escapeHtml(s.action)}</span>
      </div>
      <div class="traj-row-payload">${escapeHtml(JSON.stringify(s.payload))}</div>
    `;
    container.appendChild(stepEl);
  });
}

function focusChunk(chunkId) {
  const el = document.getElementById(`chunk-card-${chunkId}`);
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.style.borderColor = "var(--accent-indigo)";
    el.style.background = "var(--accent-indigo-light)";
    setTimeout(() => {
      el.style.borderColor = "var(--border-subtle)";
      el.style.background = "var(--bg-subtle)";
    }, 2000);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
