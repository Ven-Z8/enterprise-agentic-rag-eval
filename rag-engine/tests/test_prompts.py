"""Tests for Centralized Prompt Registry."""

import pytest

from ragfilings.prompts import PromptRegistry, load_prompt


def test_prompt_registry_loads_synthesis_template():
    prompt = PromptRegistry.get_system_synthesis()
    assert "SEC 10-K" in prompt
    assert "[brackets]" in prompt


def test_prompt_registry_formats_verification_retry():
    retry = PromptRegistry.get_verification_retry(["$999M", "50%"])
    assert "$999M, 50%" in retry
    assert "Verification failed" in retry


def test_prompt_registry_loads_math_and_decompose():
    math_p = PromptRegistry.get_math_tool()
    assert "mathematical expression" in math_p

    dec_p = PromptRegistry.get_query_decompose()
    assert "sub_query" in dec_p


def test_prompt_registry_loads_agent_templates():
    plan_p = PromptRegistry.get_planner()
    assert "Planner" in plan_p and "{inventory}" in plan_p

    res_p = PromptRegistry.get_researcher()
    assert "search_filings" in res_p

    audit_p = PromptRegistry.get_auditor()
    assert "Auditor" in audit_p and "UNVERIFIED" in audit_p


def test_load_prompt_convenience_function():
    prompt = load_prompt("synthesis")
    assert "JSON object" in prompt


def test_missing_prompt_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        PromptRegistry.get_raw("non_existent_prompt_template_xyz")
