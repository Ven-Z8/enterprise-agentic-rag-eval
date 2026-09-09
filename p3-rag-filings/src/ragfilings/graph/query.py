"""Back-compat shim: the financial graph query engine moved to
`ragfilings.domains.financial.query`. Import from there in new code."""

from ..domains.financial.query import (
    GraphQueryEngine,  # noqa: F401
    _canon_metric,  # noqa: F401
)
