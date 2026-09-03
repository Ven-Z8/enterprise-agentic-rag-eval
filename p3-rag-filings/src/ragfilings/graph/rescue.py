"""Back-compat shim: the financial scope agent moved to
`ragfilings.domains.financial.rescue`. Import from there in new code."""

from ..domains.financial.rescue import (  # noqa: F401
    GraphRescue,
    RescueOutcome,
    RescueQuery,
    _derived_values,
    _find_years,
    _format_fact,
    _strip_years,
    load_company_aliases,
    load_company_names,
    load_excluded_facts,
)
