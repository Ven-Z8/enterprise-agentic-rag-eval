# RAGFilings — Universal Agentic Cockpit UI

Production-ready, multi-domain agentic AI workbench built on the **Design System Inspired by Cisco** visual direction.

---

## 🚀 Quickstart (Running the UI Standalone)

You can launch the frontend immediately with zero build steps or npm installations:

### Option A: Python Built-in Server
```bash
cd /Volumes/VeN/FreeLance-Potfolio/cockpit-ui
python3 -m http.server 3000
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### Option B: Node / npx
```bash
npx serve /Volumes/VeN/FreeLance-Potfolio/cockpit-ui -p 3000
```

### Option C: Direct Browser Open
Simply double-click [`index.html`](file:///Volumes/VeN/FreeLance-Potfolio/cockpit-ui/index.html) to open in Chrome, Firefox, or Safari.

---

## 🔌 Connecting to Your FastAPI Backend

The UI includes an intelligent **Dual-Mode API Bridge** (`js/api-client.js`). When your FastAPI backend is running on the same host (e.g. at `http://localhost:8000`), the cockpit automatically detects it and streams live queries, graphs, and trajectories.

To run your backend:
```bash
cd /Volumes/VeN/FreeLance-Potfolio/rag-engine
uv run python -m ragfilings.ui.server
```

When connected, the top telemetry pill dynamically switches to:
`● FastAPI Connected`

See [`API_CONTRACT.md`](./API_CONTRACT.md) for full JSON schemas, endpoint specifications, and integration examples.

---

## 📁 Folder Structure

```
cockpit-ui/
├── index.html          # Semantic HTML5 cockpit workspace
├── styles.css          # Cisco Design System styling (Dark trust #0f1720, Cisco Blue #049fd9)
├── API_CONTRACT.md     # Complete REST API specification for backend connection
├── README.md           # This guide
└── js/
    ├── app.js          # Master controller, tab router, event bindings & simulation runner
    ├── domain-packs.js # Domain registry (Financial, Legal, Biomedical, + custom packs)
    ├── graph-engine.js # 2D physics-based force-directed knowledge graph (drag & spring tension)
    └── api-client.js   # Dual-mode backend bridge (auto-detects live FastAPI /api/ vs offline)
```

---

## 🌟 Key Capabilities

1. **True Multi-Domain Skill Pack Architecture**  
   - **Financial (SEC 10-K)**: Safe Python AST financial math, multi-year CAGR, parsed balance sheet tables, Item 7/8 citations.
   - **Legal (Commercial Contracts)**: 913 defined-term extraction, indemnity-vs-liability cap conflict matrix, Delaware law precedent.
   - **Biomedical (PubMed + PubChem)**: EGFR T790M Osimertinib mechanism, NCBI PUG-REST validation, AlphaFold pLDDT scores.
   - **+ Dynamic Pack Loader**: Register any future domain at runtime via the "+ Add Domain Pack" modal.

2. **Cisco Design System Compliance**  
   - Core Palette: `#0f1720` (Dark canvas), `#049fd9` (Cisco Blue accent), `#ffffff` (Text main), `#39393b` (Borders & dividers), `#f5f6f6` (Surfaces).
   - Uniform 8px border-radius across all panels, buttons, cards, pills, and modals.
   - Typography: `Inter` for UI and `JetBrains Mono` for AST math formulas, chunk hashes, and code blocks.

3. **Interactive Force-Directed Knowledge Graph**  
   - 2D Canvas physics simulation with spring relaxation, node repulsion, and drag-and-drop mechanics.
   - Entity filtering by ticker/company name (`AAPL`, `MSFT`, `NVDA`, `ALL`).

4. **Multi-Agent Parallel DAG Animation**  
   - Visualizes Stage 1 (Lead Orchestrator) branching into parallel Stage 2 (Tri-Hybrid Retrieval) & Stage 3 (Table Extraction), converging into Stage 4 (Safe Python AST), Stage 5 (Synthesis Specialist), and Stage 6 (Auditor Guardrail).

5. **Deep-Link Evidence Drawer**  
   - Clicking any citation `[1]`, `[2]` or chunk card slides open an evidence inspector showing the verified ground truth excerpt with SHA-256 integrity indicator.
