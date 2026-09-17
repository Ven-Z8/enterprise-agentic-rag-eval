"""Tests for FastAPI UI server endpoints."""

from fastapi.testclient import TestClient

from ragfilings.ui.server import app

client = TestClient(app)


def test_ui_index_endpoint():
    res = client.get("/")
    assert res.status_code == 200
    assert "RAGFILINGS" in res.text
    assert "PIPELINE STAGES" in res.text


def test_ui_presets_endpoint():
    res = client.get("/api/presets")
    assert res.status_code == 200
    data = res.json()
    assert "presets" in data
    assert len(data["presets"]) == 10
    # Check that presets contain complex questions
    assert any("CAGR" in p["title"] for p in data["presets"])
    assert any("Gross Margin" in p["title"] for p in data["presets"])


def test_ui_history_endpoint():
    res = client.get("/api/history")
    assert res.status_code == 200
    data = res.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


def test_ui_graph_endpoint():
    res = client.get("/api/graph")
    assert res.status_code == 200
    data = res.json()
    assert "nodes" in data
    assert "links" in data
    assert "stats" in data


def test_ui_query_endpoint(monkeypatch):
    # Mock ask() to test query endpoint serialization, table parsing, and chart data
    def mock_ask(*args, **kwargs):
        return {
            "session_id": "test_sess_123",
            "answer": "NVIDIA total revenue was $130,497M in FY2025 [NVDA_2025_10K:Item8:c001].",
            "refused": False,
            "citations": ["NVDA_2025_10K:Item8:c001"],
            "confidence": 0.95,
            "latency_ms": 120.0,
            "usage": {"cost_usd": 0.0001, "calls": 1},
            "hits": [
                {
                    "chunk": {
                        "id": "NVDA_2025_10K:Item8:c001",
                        "ticker": "NVDA",
                        "section": "Item8",
                        "text": "Total revenue | 2025 | 2024 | 2023\nTotal revenue | $130,497 | $60,922 | $26,974",
                    },
                    "score": 0.95,
                }
            ],
        }

    from ragfilings.ui import server

    monkeypatch.setattr(server, "ask", mock_ask)

    res = client.post(
        "/api/query",
        json={
            "query": "Analyze NVIDIA total revenue trajectory across FY2023, FY2024, and FY2025."
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "tables" in data
    assert len(data["tables"]) > 0
    assert data["tables"][0]["headers"] == ["Total revenue", "2025", "2024", "2023"]


def test_ui_query_ticker_word_boundaries_no_false_match(monkeypatch):
    """Ensure words like 'balance' and 'category' do not false-trigger BA or CAT tickers."""
    from ragfilings.ui import server

    recorded_args = {}

    def mock_ask(*args, **kwargs):
        recorded_args.update(kwargs)
        return {
            "session_id": "sess_boundary_test",
            "answer": "Answer without ticker match.",
            "refused": False,
            "citations": [],
            "confidence": 0.9,
            "latency_ms": 50.0,
            "usage": {},
            "hits": [],
        }

    monkeypatch.setattr(server, "ask", mock_ask)

    res = client.post(
        "/api/query",
        json={
            "query": "Explain balance sheet category classifications in general accounting.",
            "top_k": 12,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert recorded_args.get("top_k") == 12
    assert recorded_args.get("memory") is not None
    # No chart_data should be produced for BA or CAT from substring collision
    assert data.get("chart_data") is None


def test_ui_query_honest_fallback_metric_label(monkeypatch):
    """Ensure falling back to Revenue is honestly labeled in chart title, never masquerading."""
    from ragfilings.ui import server

    def mock_ask(*args, **kwargs):
        return {
            "session_id": "sess_chart_test",
            "answer": "Apple operating income discussion.",
            "refused": False,
            "citations": [],
            "confidence": 0.95,
            "latency_ms": 80.0,
            "usage": {},
            "hits": [],
        }

    class MockGraphEngine:
        def get_metric_history(self, ticker, metric):
            if metric == "Operating Income":
                return []
            if metric in ("Total Revenue", "Net Sales"):
                return [
                    {"fiscal_year": 2024, "value": 383285},
                    {"fiscal_year": 2025, "value": 391035},
                ]
            return []

    monkeypatch.setattr(server, "ask", mock_ask)
    monkeypatch.setattr(server, "_graph_engine", MockGraphEngine())

    res = client.post(
        "/api/query",
        json={"query": "What was Apple's operating income trend over the last two years?"},
    )
    assert res.status_code == 200
    data = res.json()
    chart = data.get("chart_data")
    assert chart is not None
    assert chart["ticker"] == "AAPL"
    assert "Alternative History, Operating Income unavailable" in chart["title"]
    assert "Alternative History, Operating Income unavailable" in chart["metric"]


def test_ui_domains_endpoint():
    res = client.get("/api/domains")
    assert res.status_code == 200
    data = res.json()
    assert "domains" in data
    assert len(data["domains"]) == 3
    domain_ids = [d["id"] for d in data["domains"]]
    assert "financial" in domain_ids
    assert "legal" in domain_ids
    assert "biomedical" in domain_ids
    for d in data["domains"]:
        assert "eval_score" in d
        assert "geval_kappa" in d
        assert "cost" in d
        assert "latency" in d


def test_ui_presets_multi_domain():
    # Legal presets
    res_legal = client.get("/api/presets?domain=legal")
    assert res_legal.status_code == 200
    data_legal = res_legal.json()
    assert "presets" in data_legal
    assert len(data_legal["presets"]) >= 2
    assert any("Indemnity" in p["title"] or "Arbitration" in p["title"] for p in data_legal["presets"])

    # Biomedical presets
    res_bio = client.get("/api/presets?domain=biomedical")
    assert res_bio.status_code == 200
    data_bio = res_bio.json()
    assert "presets" in data_bio
    assert len(data_bio["presets"]) >= 2
    assert any("EGFR" in p["title"] or "BRCA1" in p["title"] for p in data_bio["presets"])


def test_ui_graph_multi_domain():
    # Legal graph
    res_legal = client.get("/api/graph?domain=legal")
    assert res_legal.status_code == 200
    data_legal = res_legal.json()
    assert "nodes" in data_legal
    assert "links" in data_legal
    assert any(n["id"] == "MSA" for n in data_legal["nodes"])

    # Biomedical graph
    res_bio = client.get("/api/graph?domain=biomedical")
    assert res_bio.status_code == 200
    data_bio = res_bio.json()
    assert "nodes" in data_bio
    assert "links" in data_bio
    assert any(n["id"] == "EGFR" for n in data_bio["nodes"])


def test_ui_static_assets():
    res_css = client.get("/styles.css")
    assert res_css.status_code == 200
    assert "cockpit-workspace" in res_css.text

    res_js = client.get("/js/app.js")
    assert res_js.status_code == 200
    assert "DOMAIN_PACKS" in res_js.text or "handleRunQuery" in res_js.text


def test_ui_query_enriched_citations_and_proof(monkeypatch):
    from ragfilings.ui import server

    def mock_ask(*args, **kwargs):
        return {
            "session_id": "test_enriched_sess",
            "answer": "Apple net sales was $391,035M in FY2024.",
            "refused": False,
            "verified": True,
            "citations": ["AAPL_FY24_Item8_001"],
            "confidence": 0.98,
            "latency_ms": 1100.0,
            "usage": {"cost_usd": 0.005},
            "math_result": {
                "expression": "391035 / 383285",
                "result_value": 1.0202,
            },
            "hits": [
                {
                    "chunk": {
                        "id": "AAPL_FY24_Item8_001",
                        "ticker": "AAPL",
                        "section": "Item 8",
                        "text": "Total net sales were $391,035 million in fiscal 2024.",
                        "doc_name": "AAPL-10K-FY24.pdf",
                    },
                    "score": 0.98,
                }
            ],
        }

    monkeypatch.setattr(server, "ask", mock_ask)

    res = client.post(
        "/api/query",
        json={"query": "What was Apple net sales in FY2024?", "domain": "financial"},
    )
    assert res.status_code == 200
    data = res.json()
    # Check enriched citations
    assert len(data["citations"]) == 1
    cite = data["citations"][0]
    assert isinstance(cite, dict)
    assert cite["id"] == "AAPL_FY24_Item8_001"
    assert "AAPL" in cite["label"]
    assert "391,035" in cite["text"]
    assert cite["doc"] == "AAPL-10K-FY24.pdf"

    # Check verification payload
    assert "verification" in data
    ver = data["verification"]
    assert "Safe Python AST" in ver["engine"]
    assert "compute_metric" in ver["code"]
    assert ver["output"] == "Audit Passed"

    # Check trajectory
    assert "trajectory" in data
    assert len(data["trajectory"]) == 6
    stage_names = [t["name"] for t in data["trajectory"]]
    assert "Lead Orchestrator" in stage_names
    assert "Tri-Hybrid Retrieval" in stage_names
    assert "Auditor Guardrail" in stage_names


def test_ui_evals_endpoint():
    res = client.get("/api/evals")
    assert res.status_code == 200
    data = res.json()
    assert "pillars" in data
    assert len(data["pillars"]) == 7
    pillar_names = [p["name"] for p in data["pillars"]]
    assert any("Enterprise-50" in n for n in pillar_names)
    assert any("FinanceBench" in n for n in pillar_names)
    assert any("ConvFinQA" in n for n in pillar_names)
    assert any("CUAD" in n for n in pillar_names)
    assert any("LegalBench" in n for n in pillar_names)
    assert any("Isaacus" in n for n in pillar_names)
    assert any("PubMedQA" in n for n in pillar_names)

    assert "canonical_cases" in data
    assert len(data["canonical_cases"]) >= 10
    assert any(c["case_id"] == "v02-25-001" for c in data["canonical_cases"])


def test_ui_solo_folder_configuration():
    from ragfilings.ui import server

    assert server.STATIC_DIR.name == "cockpit-ui"
    assert server.STATIC_DIR.exists()
    assert (server.STATIC_DIR / "index.html").exists()
    assert (server.STATIC_DIR / "styles.css").exists()
    assert (server.STATIC_DIR / "js" / "app.js").exists()


