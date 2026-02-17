"""Tests for provider interface and implementations."""

import pytest

from artifice.providers.provider import ProviderResponse
from artifice.providers.simulated import SimulatedProvider


@pytest.mark.asyncio
async def test_simulated_provider_basic():
    """Test that provider returns expected response format."""
    provider = SimulatedProvider()
    messages = [{"role": "user", "content": "Hello"}]
    response = await provider.send(messages)

    assert isinstance(response, ProviderResponse)
    assert response.text
    assert response.stop_reason


@pytest.mark.asyncio
async def test_simulated_provider_streaming():
    """Test that streaming callbacks work."""
    provider = SimulatedProvider(response_delay=0.001)
    chunks = []
    messages = [{"role": "user", "content": "Hello"}]

    response = await provider.send(messages, on_chunk=lambda c: chunks.append(c))

    assert len(chunks) > 0
    assert "".join(chunks) == response.text


@pytest.mark.asyncio
async def test_simulated_provider_thinking():
    """Test that thinking callbacks work."""
    provider = SimulatedProvider(response_delay=0.001)
    thinking_chunks = []
    messages = [{"role": "user", "content": "Hello"}]

    response = await provider.send(
        messages, on_thinking_chunk=lambda c: thinking_chunks.append(c)
    )

    # Default scenarios include thinking for "hello"
    assert len(thinking_chunks) > 0
    assert response.thinking
    assert "".join(thinking_chunks) == response.thinking


@pytest.mark.asyncio
async def test_simulated_provider_pattern_matching():
    """Test that pattern matching works."""
    provider = SimulatedProvider()

    # Test pattern matching
    messages = [{"role": "user", "content": "calculate 2+2"}]
    response = await provider.send(messages)
    assert "python" in response.text.lower()


@pytest.mark.asyncio
async def test_simulated_provider_custom_scenarios():
    """Test custom scenario configuration."""
    provider = SimulatedProvider()
    provider.configure_scenarios(
        [{"pattern": r"test", "response": "Test response", "thinking": "Test thinking"}]
    )

    messages = [{"role": "user", "content": "test"}]
    response = await provider.send(messages)

    assert response.text == "Test response"
    assert response.thinking == "Test thinking"


@pytest.mark.asyncio
async def test_simulated_provider_default_response():
    """Test default response for unknown patterns."""
    provider = SimulatedProvider()
    provider.set_default_response("Default response")
    provider.set_default_thinking("Default thinking")
    provider.configure_scenarios([])  # Clear all scenarios

    messages = [{"role": "user", "content": "unknown command"}]
    response = await provider.send(messages)

    assert response.text == "Default response"
    assert response.thinking == "Default thinking"
