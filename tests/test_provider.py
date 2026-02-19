"""Tests for SimulatedAgent (replaces old SimulatedProvider tests)."""

import pytest

from artifice.agent import SimulatedAgent, AgentResponse


@pytest.mark.asyncio
async def test_simulated_agent_basic():
    """Test that SimulatedAgent returns expected response format."""
    agent = SimulatedAgent()
    agent.set_default_response("Hello back!")
    agent.configure_scenarios([])

    response = await agent.send("Hello")

    assert isinstance(response, AgentResponse)
    assert response.text == "Hello back!"


@pytest.mark.asyncio
async def test_simulated_agent_streaming():
    """Test that streaming callbacks work."""
    agent = SimulatedAgent(response_delay=0.001)
    agent.set_default_response("Hello World")
    agent.configure_scenarios([])

    chunks = []
    response = await agent.send("Hello", on_chunk=lambda c: chunks.append(c))

    assert len(chunks) > 0
    assert "".join(chunks) == response.text


@pytest.mark.asyncio
async def test_simulated_agent_thinking():
    """Test that thinking callbacks work."""
    agent = SimulatedAgent(response_delay=0.001)
    agent.configure_scenarios([{"response": "answer", "thinking": "thinking..."}])

    thinking_chunks = []
    response = await agent.send(
        "Hello", on_thinking_chunk=lambda c: thinking_chunks.append(c)
    )

    assert len(thinking_chunks) > 0
    assert response.thinking is not None
    assert "".join(thinking_chunks) == response.thinking


@pytest.mark.asyncio
async def test_simulated_agent_pattern_matching():
    """Test that pattern matching works."""
    agent = SimulatedAgent()
    agent.configure_scenarios(
        [{"pattern": r"calculat", "response": "Here's a python calculation"}]
    )

    response = await agent.send("calculate 2+2")
    assert "python" in response.text.lower()


@pytest.mark.asyncio
async def test_simulated_agent_custom_scenarios():
    """Test custom scenario configuration."""
    agent = SimulatedAgent()
    agent.configure_scenarios(
        [{"pattern": r"test", "response": "Test response", "thinking": "Test thinking"}]
    )

    response = await agent.send("test")

    assert response.text == "Test response"
    assert response.thinking == "Test thinking"


@pytest.mark.asyncio
async def test_simulated_agent_default_response():
    """Test default response for unknown patterns."""
    agent = SimulatedAgent()
    agent.set_default_response("Default response")
    agent.set_default_thinking("Default thinking")
    agent.configure_scenarios([])

    response = await agent.send("unknown command")

    assert response.text == "Default response"
    assert response.thinking == "Default thinking"


@pytest.mark.asyncio
async def test_simulated_agent_tool_calls():
    """Test that XML tool calls in responses are extracted as ToolCall objects."""
    agent = SimulatedAgent()
    agent.configure_scenarios(
        [{"response": "Let me run this.\n\n<python>\nprint('hi')\n</python>\n\nDone."}]
    )

    response = await agent.send("run something")

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "python"
    assert "print('hi')" in response.tool_calls[0].display_text
    # Prose should not contain the XML tags
    assert "<python>" not in response.text
