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
