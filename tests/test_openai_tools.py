"""Tests for OpenAI-compatible provider tool call support."""

from __future__ import annotations

import json

from artifice.providers.openai import _tool_calls_to_xml, OpenAICompatibleProvider
from artifice.providers.provider import ProviderResponse


# ---------------------------------------------------------------------------
# Unit tests for _tool_calls_to_xml helper
# ---------------------------------------------------------------------------


def test_tool_calls_to_xml_python():
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "python", "arguments": json.dumps({"code": "print(1+1)"})},
        }
    ]
    xml = _tool_calls_to_xml(tool_calls)
    assert "<python>" in xml
    assert "print(1+1)" in xml
    assert "</python>" in xml
    assert "<shell>" not in xml


def test_tool_calls_to_xml_shell():
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "shell", "arguments": json.dumps({"command": "ls -la"})},
        }
    ]
    xml = _tool_calls_to_xml(tool_calls)
    assert "<shell>" in xml
    assert "ls -la" in xml
    assert "</shell>" in xml
    assert "<python>" not in xml


def test_tool_calls_to_xml_multiple():
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "python", "arguments": json.dumps({"code": "x = 1"})},
        },
        {
            "id": "call_2",
            "type": "function",
            "function": {"name": "shell", "arguments": json.dumps({"command": "echo hi"})},
        },
    ]
    xml = _tool_calls_to_xml(tool_calls)
    assert "<python>" in xml
    assert "x = 1" in xml
    assert "<shell>" in xml
    assert "echo hi" in xml


def test_tool_calls_to_xml_empty():
    assert _tool_calls_to_xml([]) == ""


def test_tool_calls_to_xml_unknown_tool():
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "unknown_tool", "arguments": "{}"},
        }
    ]
    xml = _tool_calls_to_xml(tool_calls)
    assert xml == ""


def test_tool_calls_to_xml_bad_json():
    """Malformed JSON in arguments should not raise; bad call is skipped."""
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "python", "arguments": "NOT JSON"},
        }
    ]
    # Should not raise; code will be empty string
    xml = _tool_calls_to_xml(tool_calls)
    # python block still created but code is empty
    assert "<python>" in xml


def test_provider_use_tools_flag():
    """OpenAICompatibleProvider stores use_tools correctly."""
    p_with = OpenAICompatibleProvider(
        base_url="http://localhost", api_key="x", model="m", use_tools=True
    )
    p_without = OpenAICompatibleProvider(
        base_url="http://localhost", api_key="x", model="m"
    )
    assert p_with.use_tools is True
    assert p_without.use_tools is False


def test_provider_response_has_tool_calls_xml_field():
    """ProviderResponse accepts tool_calls_xml."""
    r = ProviderResponse(text="hello", tool_calls_xml="<python>\nprint(1)\n</python>\n")
    assert r.tool_calls_xml is not None
    assert "<python>" in r.tool_calls_xml


def test_provider_response_tool_calls_xml_defaults_none():
    r = ProviderResponse(text="hello")
    assert r.tool_calls_xml is None
