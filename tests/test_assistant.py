"""Tests for the Assistant class."""

import pytest

from artifice.assistant import Assistant, SimulatedProvider


@pytest.mark.asyncio
async def test_assistant_manages_history():
    """Test that assistant maintains conversation history."""
    provider = SimulatedProvider(response_delay=0.001)
    assistant = Assistant(provider=provider)

    await assistant.send_prompt("First message")
    assert len(assistant.messages) == 2  # user + assistant
    assert assistant.messages[0]["role"] == "user"
    assert assistant.messages[1]["role"] == "assistant"

    await assistant.send_prompt("Second message")
    assert len(assistant.messages) == 4  # 2 turns


@pytest.mark.asyncio
async def test_assistant_clear_conversation():
    """Test that clear_conversation works."""
    provider = SimulatedProvider(response_delay=0.001)
    assistant = Assistant(provider=provider)

    await assistant.send_prompt("Hello")
    assert len(assistant.messages) > 0

    assistant.clear_conversation()
    assert len(assistant.messages) == 0


@pytest.mark.asyncio
async def test_multiple_assistants_share_provider():
    """Test that multiple assistants can use same provider."""
    provider = SimulatedProvider(response_delay=0.001)
    assistant1 = Assistant(provider=provider, system_prompt="You are helpful")
    assistant2 = Assistant(provider=provider, system_prompt="You are concise")

    await assistant1.send_prompt("Hello")
    await assistant2.send_prompt("Hello")

    # Each maintains separate history
    assert len(assistant1.messages) == 2
    assert len(assistant2.messages) == 2

    # But share the same provider instance
    assert assistant1.provider is assistant2.provider


@pytest.mark.asyncio
async def test_assistant_system_prompt():
    """Test that system prompt is passed to provider."""
    provider = SimulatedProvider(response_delay=0.001)
    assistant = Assistant(provider=provider, system_prompt="Test system prompt")

    assert assistant.system_prompt == "Test system prompt"

    await assistant.send_prompt("Hello")
    # System prompt is passed but not stored in messages (provider-specific)
    assert len(assistant.messages) == 2


@pytest.mark.asyncio
async def test_assistant_streaming():
    """Test that streaming callbacks are passed through."""
    provider = SimulatedProvider(response_delay=0.001)
    assistant = Assistant(provider=provider)

    chunks = []
    thinking_chunks = []

    response = await assistant.send_prompt(
        "Hello",
        on_chunk=lambda c: chunks.append(c),
        on_thinking_chunk=lambda c: thinking_chunks.append(c),
    )

    assert len(chunks) > 0
    assert "".join(chunks) == response.text
    assert len(thinking_chunks) > 0


@pytest.mark.asyncio
async def test_assistant_error_handling():
    """Test that errors from provider are handled."""
    provider = SimulatedProvider(response_delay=0.001)

    # Create a provider that returns an error
    async def error_send(*args, **kwargs):
        from artifice.providers.provider import ProviderResponse

        return ProviderResponse(text="", error="Test error")

    provider.send = error_send
    assistant = Assistant(provider=provider)

    response = await assistant.send_prompt("Hello")
    assert response.error == "Test error"
    assert response.text == ""


@pytest.mark.asyncio
async def test_assistant_empty_prompt():
    """Test that empty prompts are handled correctly."""
    provider = SimulatedProvider(response_delay=0.001)
    assistant = Assistant(provider=provider)

    # Empty prompt should not be added to history
    await assistant.send_prompt("")
    # Still gets response, but no user message added
    assert len(assistant.messages) <= 1  # Only assistant response (if any)

    # Whitespace-only prompt should also be ignored
    await assistant.send_prompt("   ")
    assert len(assistant.messages) <= 2
