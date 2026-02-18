"""Tests for the Agent class."""

import pytest

from artifice.agent import SimulatedAgent


@pytest.mark.asyncio
async def test_agent_manages_history():
    """Test that agent maintains conversation history."""
    agent = SimulatedAgent(response_delay=0.001)

    await agent.send("First message")
    assert len(agent.messages) == 2  # user + agent
    assert agent.messages[0]["role"] == "user"
    assert agent.messages[1]["role"] == "assistant"

    await agent.send("Second message")
    assert len(agent.messages) == 4  # 2 turns


@pytest.mark.asyncio
async def test_agent_clear():
    """Test that clear() works."""
    agent = SimulatedAgent(response_delay=0.001)

    await agent.send("Hello")
    assert len(agent.messages) > 0

    agent.clear()
    assert len(agent.messages) == 0


@pytest.mark.asyncio
async def test_multiple_agents_independent_history():
    """Test that multiple agents maintain separate history."""
    agent1 = SimulatedAgent(system_prompt="You are helpful")
    agent2 = SimulatedAgent(system_prompt="You are concise")

    agent1.configure_scenarios([{"response": "agent1 reply"}])
    agent2.configure_scenarios([{"response": "agent2 reply"}])

    await agent1.send("Hello")
    await agent2.send("Hello")

    assert len(agent1.messages) == 2
    assert len(agent2.messages) == 2
    assert agent1 is not agent2


@pytest.mark.asyncio
async def test_agent_system_prompt():
    """Test that system prompt is stored."""
    agent = SimulatedAgent(system_prompt="Test system prompt")
    assert agent.system_prompt == "Test system prompt"
    await agent.send("Hello")
    assert len(agent.messages) == 2


@pytest.mark.asyncio
async def test_agent_streaming():
    """Test that streaming callbacks are passed through."""
    agent = SimulatedAgent(response_delay=0.001)
    agent.set_default_response("hello world")

    chunks = []
    thinking_chunks = []

    response = await agent.send(
        "Hello",
        on_chunk=lambda c: chunks.append(c),
        on_thinking_chunk=lambda c: thinking_chunks.append(c),
    )

    assert len(chunks) > 0
    assert "".join(chunks) == response.text


@pytest.mark.asyncio
async def test_agent_error_handling():
    """Test that errors in agent.send are returned as AgentResponse.error."""
    from artifice.agent import AgentResponse

    agent = SimulatedAgent(response_delay=0.001)

    # Patch send to simulate an error

    async def erroring_send(*args, **kwargs):
        return AgentResponse(text="", error="Test error")

    agent.send = erroring_send

    response = await agent.send("Hello")
    assert response.error == "Test error"
    assert response.text == ""


@pytest.mark.asyncio
async def test_agent_empty_prompt():
    """Test that empty prompts are not added to history."""
    agent = SimulatedAgent(response_delay=0.001)
    agent.set_default_response("reply")

    await agent.send("")
    assert all(m["role"] != "user" for m in agent.messages)

    await agent.send("   ")
    assert all(m["content"] != "   " for m in agent.messages)


@pytest.mark.asyncio
async def test_agent_tool_result():
    """Test that add_tool_result appends a tool message."""
    agent = SimulatedAgent()
    agent.add_tool_result("call_123", "output text")
    assert any(
        m.get("role") == "tool" and m.get("tool_call_id") == "call_123"
        for m in agent.messages
    )
