"""Financial domain pack — SEC 10-K filings.

Fact layer: deterministic table parsing into a typed fact graph
(Company → Year → Metric → Value with chunk provenance). Scope agent:
ticker/metric/fiscal-year rescue + deterministic clarifications. Claim
semantics: monetary / percentage figures with unit scaling. Derivation tool:
safe Python financial math.

Measured (all-free, accuracy-only): v1-50 96.0% (48/50, 2026-09-03),
enterprise 95.6% (43/45) — see docs/graph_augmentation_v1.md for the frozen
v1-80 stage ladder (97.5%).
"""

from .pack import FinancialPack

PACK = FinancialPack()

__all__ = ["PACK", "FinancialPack"]
