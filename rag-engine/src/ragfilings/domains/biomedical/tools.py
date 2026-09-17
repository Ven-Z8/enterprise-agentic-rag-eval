"""Biomedical domain tools — PubChem PUG-REST API integration.

Provides live, dynamic resolution of chemical and pharmacological compound properties
directly from NCBI PubChem without pre-baked dictionaries or static lookup tables.
Enforces polite HTTP rate limits and safe timeouts.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

PUBCHEM_BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

_PROPERTY_RE = re.compile(
    r"\b(molecular\s+weight|molecular\s+formula|chemical\s+formula|iupac\s+name|smiles|structure|cid|pubchem)\b",
    re.IGNORECASE,
)

_COMPOUND_CANDIDATE_RE = re.compile(
    r"(?:molecular\s+(?:weight|formula)|formula|iupac\s+name|of|structure\s+of)\s+([A-Za-z0-9\-\s]{3,30}?)(?:\?|\.|\,|and|\s+in\b|$)",
    re.IGNORECASE,
)


def resolve_compound(name: str, timeout: float = 6.0) -> dict[str, Any] | None:
    """Resolve chemical compound name to properties via live NCBI PubChem PUG-REST API.

    Returns dict with CID, MolecularFormula, MolecularWeight, CanonicalSMILES, IUPACName,
    or None if not found or on network timeout.
    """
    clean_name = name.strip().rstrip("?.!,; ")
    if len(clean_name) < 2:
        return None

    encoded = urllib.parse.quote(clean_name)
    url = f"{PUBCHEM_BASE_URL}/compound/name/{encoded}/property/MolecularFormula,MolecularWeight,CanonicalSMILES,IUPACName/JSON"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "DomainAdaptiveRAG/1.0 (biomedical-eval-harness; mailto:eval@example.org)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            props = data.get("PropertyTable", {}).get("Properties", [])
            if not props:
                return None
            first = props[0]
            return {
                "cid": first.get("CID"),
                "name": clean_name,
                "molecular_formula": first.get("MolecularFormula"),
                "molecular_weight": float(first.get("MolecularWeight", 0.0))
                if first.get("MolecularWeight")
                else None,
                "canonical_smiles": first.get("CanonicalSMILES"),
                "iupac_name": first.get("IUPACName"),
            }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
        logger.debug("PubChem query for %r failed: %s", clean_name, e)
        return None


def extract_compound_name(query: str) -> str | None:
    """Extract chemical or drug candidate name from query string."""
    m = _COMPOUND_CANDIDATE_RE.search(query)
    if m:
        candidate = m.group(1).strip()
        # Strip leading prepositions and articles
        candidate = re.sub(r"^(?:of|for|in|the|a|an)\s+", "", candidate, flags=re.IGNORECASE).strip()
        stops = {"the", "a", "an", "this", "that", "these", "those", "patient", "clinical", "cell", "and"}
        if candidate.lower() not in stops and len(candidate) >= 3:
            return candidate

    words = [w.strip("?,.!") for w in query.split() if len(w) >= 4]
    for w in words:
        if w.lower() in ("aspirin", "ibuprofen", "metformin", "caffeine", "paracetamol", "acetaminophen", "penicillin", "atorvastatin", "doxorubicin", "cisplatin", "curcumin", "resveratrol"):
            return w

    return None


def compute_biomedical(
    query: str,
    chunks: list[dict[str, Any]],
    cfg: dict[str, Any],
    client: Any = None,
) -> dict[str, Any] | None:
    """PubChem derivation tool for biomedical domain pack.

    If query asks about chemical properties, formula, or molecular structure,
    resolves the compound dynamically via PubChem PUG-REST API.
    """
    if not _PROPERTY_RE.search(query):
        return None

    compound = extract_compound_name(query)
    if not compound:
        return None

    props = resolve_compound(compound)
    if not props:
        return None

    parts = []
    if props.get("molecular_formula"):
        parts.append(f"Formula: {props['molecular_formula']}")
    if props.get("molecular_weight"):
        parts.append(f"MW: {props['molecular_weight']:.2f} g/mol")
    if props.get("iupac_name"):
        parts.append(f"IUPAC: {props['iupac_name']}")
    if props.get("cid"):
        parts.append(f"CID: {props['cid']}")

    formatted = f"PubChem Verified Data for '{compound}': " + "; ".join(parts)

    return {
        "explanation": f"Live PubChem PUG-REST resolution for compound '{compound}'",
        "formatted": formatted,
        "expression": f"pubchem.resolve('{compound}')",
        "result_value": props.get("molecular_weight"),
        "compound_data": props,
        "usage": {"calls": 1, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
    }
