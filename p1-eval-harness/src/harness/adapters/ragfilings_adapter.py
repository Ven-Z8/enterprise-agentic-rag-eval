"""Adapter connecting p3-rag-filings to the Domain-Adaptive Agent Eval Harness.

Protocol for the new runner: `run_case(case, strategy, refusal_log=None)`
returns the target system's raw result dict (answer, citations, hits,
verification, refused, usage, latency, graph_rescue, ...) unchanged, so the
harness scoring engine sees exactly what the system produced.

Requires the `ragfilings` package — either installed in the same venv or
available as the sibling `../p3-rag-filings` checkout (auto-bootstrapped).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

P3_ROOT = Path(__file__).resolve().parents[4] / "p3-rag-filings"

try:
    import ragfilings  # noqa: F401
except ImportError:
    _p3_src = P3_ROOT / "src"
    if _p3_src.exists() and str(_p3_src) not in sys.path:
        sys.path.insert(0, str(_p3_src))


class RAGFilingsAdapter:
    """Runs the p3-rag-filings ask() pipeline for harness scoring.

    The pipeline is domain-agnostic; the domain pack (prompts, fact layer,
    claim semantics) is selected with ``domain``. Each pack owns its own
    index — the financial pack uses the corpus index from config.toml, other
    packs expose an ``index_dir``.
    """

    name = "ragfilings-v1"

    def __init__(self, config_path: str | None = None, domain: str = "financial"):
        from ragfilings import config as cfg_mod
        from ragfilings import retrieval

        if config_path is None:
            config_path = str(P3_ROOT / "config.toml")
        self.cfg = cfg_mod.load(config_path)
        self.domain = domain

        from ragfilings.domains import get_pack

        pack = get_pack(domain)
        index_path = Path(getattr(pack, "index_dir", None) or self.cfg["embedding"]["index_dir"])
        if not index_path.is_absolute():
            index_path = P3_ROOT / index_path
        self.index = retrieval.load_index(str(index_path), self.cfg["embedding"]["model"])

    @property
    def model_name(self) -> str:
        return self.cfg.get("generation", {}).get("model", "")

    def run_case(
        self,
        case: dict[str, Any],
        strategy: str = "hybrid_rerank",
        refusal_log: str | Path | None = None,
    ) -> dict[str, Any]:
        from ragfilings.pipeline import ask

        return ask(
            case["input"],
            self.cfg,
            index=self.index,
            strategy=strategy,
            refusal_log=refusal_log,
            domain=self.domain,
        )
