---
name: legal
display_name: Commercial Contracts & Legal Clauses
description: Analyzes commercial agreements (CUAD), indemnification, termination, governing law, and defined terms with verbatim grounding.
domain: legal
activation_keywords:
  - contract
  - agreement
  - indemnification
  - termination
  - clause
  - governing law
  - breach
  - warranty
  - liability cap
  - confidentiality
tools:
  - defined_term_rescue
verification_type: verbatim_quote
version: 1.0.0
---

# Commercial Contracts & Legal Clause Domain Skill

This skill provides expert legal contract interpretation, clause extraction, defined term resolution, and verbatim claim verification over commercial agreements (based on the Contract Understanding Atticus Dataset / CUAD).

## Capabilities
1. **Verbatim Clause Extraction**: Reproduces operative clause text exactly as written without paraphrasing legal terms of art.
2. **Defined Term Resolution**: Binds capitalized legal definitions against Section 1 / Definitions sections.
3. **Single Agreement Scope**: Prevents mixing clauses across distinct contracts unless explicitly comparing agreements.
4. **Strict Grounding & Refusal**: Refuses queries when a requested clause (e.g. non-compete, change of control) is not present in the agreement.
