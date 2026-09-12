import os
import unittest
from unittest.mock import MagicMock, patch

from ragfilings.retrieval import _rerank_openrouter, Index


class TestRerankOpenrouter(unittest.TestCase):
    def test_rerank_openrouter_success(self):
        fake_resp_body = (
            b'{"model":"cohere/rerank-v3.5","results":['
            b'{"index":1,"relevance_score":0.95},'
            b'{"index":0,"relevance_score":0.12}'
            b']}'
        )
        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_resp_body
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            scores = _rerank_openrouter(
                query="test query",
                documents=["doc 0", "doc 1"],
                model="cohere/rerank-v3.5",
                api_key="sk-fake-key",
            )
            self.assertEqual(len(scores), 2)
            self.assertAlmostEqual(scores[0], 0.12)
            self.assertAlmostEqual(scores[1], 0.95)

    def test_rerank_openrouter_missing_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                _rerank_openrouter(
                    query="test",
                    documents=["doc1"],
                    api_key=None,
                )

    def test_rerank_fallback_on_error(self):
        # When cloud rerank throws, search() should fall back to local BGE
        chunks = [
            {"id": "c1", "text": "chunk 1", "company": "Apple", "ticker": "AAPL", "fiscal_year": 2023},
            {"id": "c2", "text": "chunk 2", "company": "Apple", "ticker": "AAPL", "fiscal_year": 2023},
        ]
        import numpy as np
        from rank_bm25 import BM25Okapi

        embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        bm25 = BM25Okapi([["chunk", "1"], ["chunk", "2"]])
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[1.0, 0.0]], dtype=np.float32)

        index = Index(chunks=chunks, embeddings=embeddings, bm25=bm25, model=mock_model)

        mock_local_reranker = MagicMock()
        mock_local_reranker.predict.return_value = [0.5, 0.8]

        with patch("ragfilings.retrieval._rerank_openrouter", side_effect=RuntimeError("API error")):
            with patch("ragfilings.retrieval._get_reranker", return_value=mock_local_reranker):
                hits = index.search(
                    query="chunk 2",
                    strategy="hybrid_rerank",
                    top_k=2,
                    reranker_name="cohere/rerank-v3.5",
                    rerank_candidates=2,
                )
                self.assertEqual(len(hits), 2)
                # chunk 2 got higher local score (0.8)
                self.assertEqual(hits[0]["chunk"]["id"], "c2")
