"""Back-compat shim: the financial fact-graph builder moved to
`ragfilings.domains.financial.builder`. Import from there in new code."""

from ..domains.financial.builder import (  # noqa: F401
    _CELL_DECORATIONS,
    _FOOTNOTE_RE,
    _METRIC_PHRASES,
    _NUM_RE,
    _YEAR_RE,
    KNOWN_METRICS,
    FinancialGraphBuilder,
    _match_metric,
    _parse_cell,
    _table_blocks,
)
