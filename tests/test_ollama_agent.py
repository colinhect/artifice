"""Tests for Ollama agent thinking/reasoning support."""

import pytest
from unittest.mock import MagicMock, patch
from artifice.agent.ollama import OllamaAgent


class TestOllamaAgentThinking:
    @pytest.mark.asyncio
    async def test_thinking_tags_extracted(self):
        """Thinking content in <think> tags is extracted and separated."""
        agent = OllamaAgent(model="test-model")

        # Mock the Ollama client
        mock_client = MagicMock()
        mock_stream = [
            {"message": {"content": "<think>reasoning here</think>"}},
            {"message": {"content": "final answer"}},
            {"done": True, "done_reason": "stop"},
        ]
        mock_client.chat.return_value = iter(mock_stream)

        with patch.object(agent, '_get_client', return_value=mock_client):
            thinking_chunks = []
            response_chunks = []

            resp = await agent.send_prompt(
                "test prompt",
                on_chunk=lambda c: response_chunks.append(c),
                on_thinking_chunk=lambda c: thinking_chunks.append(c)
            )

            assert "".join(thinking_chunks) == "reasoning here"
            assert "".join(response_chunks) == "final answer"
            assert resp.text == "final answer"
            assert resp.thinking == "reasoning here"

    @pytest.mark.asyncio
    async def test_thinking_tag_variations(self):
        """Different thinking tag types (<think>, <thinking>, <reasoning>) are all recognized."""
        agent = OllamaAgent(model="test-model")

        mock_client = MagicMock()
        mock_stream = [
            {"message": {"content": "<thinking>thought 1</thinking>"}},
            {"message": {"content": "<reasoning>thought 2</reasoning>"}},
            {"message": {"content": "answer"}},
            {"done": True, "done_reason": "stop"},
        ]
        mock_client.chat.return_value = iter(mock_stream)

        with patch.object(agent, '_get_client', return_value=mock_client):
            thinking_chunks = []

            resp = await agent.send_prompt(
                "test",
                on_thinking_chunk=lambda c: thinking_chunks.append(c)
            )

            assert "".join(thinking_chunks) == "thought 1thought 2"
            assert resp.text == "answer"
            assert resp.thinking == "thought 1thought 2"

    @pytest.mark.asyncio
    async def test_mixed_thinking_and_text(self):
        """Content can have thinking tags mixed with regular text."""
        agent = OllamaAgent(model="test-model")

        mock_client = MagicMock()
        mock_stream = [
            {"message": {"content": "intro <think>thinking</think> middle "}},
            {"message": {"content": "<reasoning>more thinking</reasoning> end"}},
            {"done": True, "done_reason": "stop"},
        ]
        mock_client.chat.return_value = iter(mock_stream)

        with patch.object(agent, '_get_client', return_value=mock_client):
            thinking_chunks = []
            response_chunks = []

            resp = await agent.send_prompt(
                "test",
                on_chunk=lambda c: response_chunks.append(c),
                on_thinking_chunk=lambda c: thinking_chunks.append(c)
            )

            assert "".join(thinking_chunks) == "thinkingmore thinking"
            assert "".join(response_chunks) == "intro  middle  end"
            assert resp.thinking == "thinkingmore thinking"

    @pytest.mark.asyncio
    async def test_no_thinking_tags(self):
        """Responses without thinking tags work normally."""
        agent = OllamaAgent(model="test-model")

        mock_client = MagicMock()
        mock_stream = [
            {"message": {"content": "just a "}},
            {"message": {"content": "regular response"}},
            {"done": True, "done_reason": "stop"},
        ]
        mock_client.chat.return_value = iter(mock_stream)

        with patch.object(agent, '_get_client', return_value=mock_client):
            thinking_chunks = []
            response_chunks = []

            resp = await agent.send_prompt(
                "test",
                on_chunk=lambda c: response_chunks.append(c),
                on_thinking_chunk=lambda c: thinking_chunks.append(c)
            )

            assert thinking_chunks == []
            assert "".join(response_chunks) == "just a regular response"
            assert resp.text == "just a regular response"
            assert resp.thinking is None

    @pytest.mark.asyncio
    async def test_thinking_without_callback(self):
        """Thinking tags work even when no callback is provided."""
        agent = OllamaAgent(model="test-model")

        mock_client = MagicMock()
        mock_stream = [
            {"message": {"content": "<think>reasoning</think>answer"}},
            {"done": True, "done_reason": "stop"},
        ]
        mock_client.chat.return_value = iter(mock_stream)

        with patch.object(agent, '_get_client', return_value=mock_client):
            resp = await agent.send_prompt("test")

            assert resp.text == "answer"
            assert resp.thinking == "reasoning"

    @pytest.mark.asyncio
    async def test_multiline_thinking(self):
        """Thinking tags can contain multiline content."""
        agent = OllamaAgent(model="test-model")

        mock_client = MagicMock()
        mock_stream = [
            {"message": {"content": "<think>line 1\nline 2\nline 3</think>answer"}},
            {"done": True, "done_reason": "stop"},
        ]
        mock_client.chat.return_value = iter(mock_stream)

        with patch.object(agent, '_get_client', return_value=mock_client):
            resp = await agent.send_prompt("test")

            assert resp.thinking == "line 1\nline 2\nline 3"
            assert resp.text == "answer"

    @pytest.mark.asyncio
    async def test_thinking_split_across_chunks(self):
        """Thinking tags that are split across chunks are handled correctly."""
        agent = OllamaAgent(model="test-model")

        mock_client = MagicMock()
        # Tag is split across multiple chunks
        mock_stream = [
            {"message": {"content": "<thi"}},
            {"message": {"content": "nk>reasoning"}},
            {"message": {"content": " content</think>answer"}},
            {"done": True, "done_reason": "stop"},
        ]
        mock_client.chat.return_value = iter(mock_stream)

        with patch.object(agent, '_get_client', return_value=mock_client):
            resp = await agent.send_prompt("test")

            assert resp.thinking == "reasoning content"
            assert resp.text == "answer"
