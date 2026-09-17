/**
 * RAGFilings — Backend API Client & Dual-Mode Bridge
 * Seamlessly interfaces with the FastAPI backend (/api/*) when online,
 * or gracefully runs simulated domain-pack golden executions when running offline/preview.
 */

(function () {
  let backendOnline = false;
  let currentSessionId = null;

  async function checkHealth() {
    try {
      const controller = new AbortController();
      const id = setTimeout(() => controller.abort(), 1200);
      const res = await fetch('/api/presets', { signal: controller.signal });
      clearTimeout(id);
      backendOnline = res.ok;
    } catch {
      backendOnline = false;
    }
    notifyStatus(backendOnline);
    return backendOnline;
  }

  function notifyStatus(online) {
    window.dispatchEvent(new CustomEvent('rag-backend-status', { detail: { online } }));
  }

  async function getSessionId() {
    if (currentSessionId) return currentSessionId;
    try {
      const res = await fetch('/api/session/new', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        currentSessionId = data.session_id;
        return currentSessionId;
      }
    } catch {
      // Fallback local session
    }
    currentSessionId = `session_${Math.random().toString(36).substring(2, 9)}`;
    return currentSessionId;
  }

  async function fetchDomains() {
    try {
      const res = await fetch('/api/domains');
      if (res.ok) {
        const data = await res.json();
        if (data.domains && data.domains.length > 0) {
          data.domains.forEach(d => {
            if (window.DOMAIN_PACKS && window.DOMAIN_PACKS[d.id]) {
              window.DOMAIN_PACKS[d.id].name = d.name || window.DOMAIN_PACKS[d.id].name;
              window.DOMAIN_PACKS[d.id].badge = d.badge || window.DOMAIN_PACKS[d.id].badge;
              window.DOMAIN_PACKS[d.id].evalScore = d.eval_score || window.DOMAIN_PACKS[d.id].evalScore;
              window.DOMAIN_PACKS[d.id].gevalKappa = d.geval_kappa || window.DOMAIN_PACKS[d.id].gevalKappa;
              window.DOMAIN_PACKS[d.id].cost = d.cost || window.DOMAIN_PACKS[d.id].cost;
              window.DOMAIN_PACKS[d.id].latency = d.latency || window.DOMAIN_PACKS[d.id].latency;
            }
          });
          backendOnline = true;
          notifyStatus(true);
          return data.domains;
        }
      }
    } catch {
      // Offline fallback
    }
    return null;
  }

  async function fetchPresets(domainKey) {
    try {
      const url = domainKey ? `/api/presets?domain=${encodeURIComponent(domainKey)}` : '/api/presets';
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (data.presets && data.presets.length > 0) {
          backendOnline = true;
          notifyStatus(true);
          return data.presets.map((p, idx) => ({
            id: p.id || `q_${idx}`,
            title: p.title || p.query.substring(0, 40),
            snippet: p.category ? `Category: ${p.category}` : p.query.substring(0, 80),
            query: p.query,
            badges: [p.ticker || p.badge || 'Domain Case', 'Live Backend']
          }));
        }
      }
    } catch {
      // Offline fallback
    }

    const pack = window.DOMAIN_PACKS[domainKey] || window.DOMAIN_PACKS.financial;
    return pack.presets || [];
  }

  async function fetchHistory(domainKey) {
    try {
      const res = await fetch('/api/history?limit=10');
      if (res.ok) {
        const data = await res.json();
        if (data.sessions && data.sessions.length > 0) {
          return data.sessions.map(s => ({
            q: s.query,
            time: `${(s.latency_ms / 1000).toFixed(1)}s · $${(s.cost_usd || 0).toFixed(4)}`,
            verified: s.verified
          }));
        }
      }
    } catch {
      // Offline fallback
    }

    return [
      { q: `${domainKey.toUpperCase()} multi-hop benchmark #1`, time: '2m ago', verified: true },
      { q: `${domainKey.toUpperCase()} ratio comparison trial`, time: '14m ago', verified: true },
      { q: `${domainKey.toUpperCase()} baseline golden set run`, time: '1h ago', verified: true }
    ];
  }

  async function fetchGraph(domainKey, ticker) {
    try {
      let url = domainKey ? `/api/graph?domain=${encodeURIComponent(domainKey)}` : '/api/graph';
      if (ticker && ticker !== 'ALL') {
        url += `&ticker=${encodeURIComponent(ticker)}`;
      }
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        if (data.nodes && data.nodes.length > 0) {
          return {
            nodes: data.nodes.map(n => ({
              id: n.id,
              label: n.label || n.id,
              type: (n.type || 'entity').toLowerCase(),
              ticker: n.ticker,
              value: n.value,
              fiscal_year: n.fiscal_year
            })),
            links: (data.links || []).map(l => ({
              source: l.source,
              target: l.target,
              relation: l.relation || 'RELATES_TO'
            }))
          };
        }
      }
    } catch {
      // Offline fallback
    }

    const pack = window.DOMAIN_PACKS[domainKey] || window.DOMAIN_PACKS.financial;
    return pack.graph;
  }

  async function executeQuery({ query, strategy = 'hybrid_rerank_graph', domain = 'financial', topK = 8 }) {
    const sessionId = await getSessionId();

    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          strategy,
          top_k: topK,
          session_id: sessionId,
          domain
        })
      });

      if (res.ok) {
        const liveData = await res.json();
        backendOnline = true;
        notifyStatus(true);
        return {
          isLive: true,
          title: `Analysis: ${query.substring(0, 60)}`,
          answer: liveData.answer || liveData.refusal_reason || (liveData.verified ? 'Analysis complete.' : 'The requested query could not be verified against the filing corpus.'),
          refusalReason: liveData.refusal_reason,
          citations: (liveData.citations || []).map((c, i) => ({
            label: typeof c === 'string' ? c : (c.label || `Citation [${i + 1}]`),
            text: c.text || '',
            doc: c.doc || ''
          })),
          verified: liveData.verified !== false,
          confidence: liveData.confidence !== undefined ? liveData.confidence : 0.95,
          latencyMs: liveData.latency_ms || 1200,
          costUsd: liveData.usage?.cost_usd || 0.007,
          proof: (liveData.verification && (liveData.verification.code || liveData.math_result)) ? {
            title: liveData.verification.title || 'DETERMINISTIC VERIFICATION PROOF',
            code: typeof liveData.verification === 'string' ? liveData.verification : (liveData.verification.code || JSON.stringify(liveData.verification, null, 2)),
            engine: liveData.verification.engine || 'Safe Logic Verifier',
            output: liveData.verification.output || (liveData.verified ? 'Audit Passed' : 'Refused / Unverified'),
            confidence: String(liveData.confidence !== undefined ? liveData.confidence : '0.95')
          } : null,
          table: (liveData.tables && liveData.tables.length > 0 && liveData.tables[0].headers && liveData.tables[0].rows && liveData.tables[0].rows.length > 0) ? [
            liveData.tables[0].headers,
            ...liveData.tables[0].rows
          ] : null,
          tableTitle: (liveData.tables && liveData.tables.length > 0) ? (liveData.tables[0].title || 'EXTRACTED STATEMENT TABLE') : null,
          chartData: (liveData.chart_data && liveData.chart_data.labels && liveData.chart_data.labels.length > 0 && liveData.chart_data.values && liveData.chart_data.values.length > 0) ? {
            title: liveData.chart_data.title || `${liveData.chart_data.metric || 'Metric'} Trajectory`,
            metric: liveData.chart_data.metric || 'Metric',
            labels: liveData.chart_data.labels,
            datasets: [{
              label: liveData.chart_data.metric || 'Value',
              values: liveData.chart_data.values
            }]
          } : null,
          chunks: (liveData.hits || []).map(h => ({
            tag: `${h.section || 'Chunk'} · Score: ${h.score?.toFixed(3) || '0.90'}`,
            score: `${(h.score * 100).toFixed(1)}% BGE`,
            text: h.text || ''
          })),
          trajectory: liveData.trajectory || []
        };
      }
    } catch (err) {
      // Backend request error
    }

    backendOnline = false;
    notifyStatus(false);

    return {
      isLive: false,
      error: true,
      title: `Connection Offline: ${query.substring(0, 50)}`,
      answer: 'Unable to communicate with the backend server at http://127.0.0.1:8000/. Please verify FastAPI is running.',
      citations: [],
      verified: false,
      confidence: 0.0,
      latencyMs: 0,
      costUsd: 0.0,
      proof: null,
      table: null,
      chartData: null,
      chunks: [],
      trajectory: []
    };
  }

  async function fetchEvals() {
    try {
      const res = await fetch('/api/evals');
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Offline fallback
    }
    return null;
  }

  window.ApiClient = {
    checkHealth,
    fetchDomains,
    fetchPresets,
    fetchHistory,
    fetchGraph,
    fetchEvals,
    executeQuery
  };
})();
