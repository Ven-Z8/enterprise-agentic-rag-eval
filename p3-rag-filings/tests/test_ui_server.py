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
        json={"query": "Analyze NVIDIA total revenue trajectory across FY2023, FY2024, and FY2025."},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "tables" in data
    assert len(data["tables"]) > 0
    assert data["tables"][0]["headers"] == ["Total revenue", "2025", "2024", "2023"]
