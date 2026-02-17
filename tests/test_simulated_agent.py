"""Tests for simulated assistants - pattern matching, scripted sequences, echo."""

import asyncio
import pytest
from artifice.assistant.simulated import (
    SimulatedAssistant,
    ScriptedAssistant,
    EchoAssistant,
)


class TestSimulatedAssistantPatternMatching:
    @pytest.mark.asyncio
    async def test_pattern_match(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios(
            [
                {"pattern": r"hello|hi", "response": "greeting!"},
                {"pattern": r"math|calc", "response": "calculating!"},
            ]
        )
        resp = await assistant.send_prompt("hello there")
        assert resp.text == "greeting!"

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios(
            [
                {"pattern": r"hello", "response": "matched!"},
            ]
        )
        resp = await assistant.send_prompt("HELLO WORLD")
        assert resp.text == "matched!"

    @pytest.mark.asyncio
    async def test_no_match_uses_default(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.set_default_response("no match")
        assistant.configure_scenarios(
            [
                {"pattern": r"specific", "response": "found!"},
            ]
        )
        resp = await assistant.send_prompt("something else")
        assert resp.text == "no match"

    @pytest.mark.asyncio
    async def test_first_matching_pattern_wins(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios(
            [
                {"pattern": r"test", "response": "first"},
                {"pattern": r"test", "response": "second"},
            ]
        )
        resp = await assistant.send_prompt("test")
        assert resp.text == "first"


class TestSimulatedAssistantSequential:
    @pytest.mark.asyncio
    async def test_sequential_scenarios(self):
        """Scenarios without patterns are used sequentially."""
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios(
            [
                {"response": "first"},
                {"response": "second"},
                {"response": "third"},
            ]
        )
        r1 = await assistant.send_prompt("anything")
        r2 = await assistant.send_prompt("anything")
        r3 = await assistant.send_prompt("anything")
        assert r1.text == "first"
        assert r2.text == "second"
        assert r3.text == "third"

    @pytest.mark.asyncio
    async def test_sequential_exhausted_uses_default(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.set_default_response("fallback")
        assistant.configure_scenarios([{"response": "only one"}])
        await assistant.send_prompt("first")
        resp = await assistant.send_prompt("second")
        assert resp.text == "fallback"


class TestSimulatedAssistantStreaming:
    @pytest.mark.asyncio
    async def test_streaming_chunks(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.set_default_response("hello world")
        chunks = []
        await assistant.send_prompt("test", on_chunk=lambda c: chunks.append(c))
        # Should stream character by character
        assert "".join(chunks) == "hello world"

    @pytest.mark.asyncio
    async def test_streaming_matches_response(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios([{"pattern": r"test", "response": "abc"}])
        chunks = []
        resp = await assistant.send_prompt("test", on_chunk=lambda c: chunks.append(c))
        assert "".join(chunks) == resp.text


class TestSimulatedAssistantHistory:
    @pytest.mark.asyncio
    async def test_conversation_history_tracked(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.set_default_response("reply")
        await assistant.send_prompt("hello")
        history = assistant.get_conversation_history()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "reply"}

    @pytest.mark.asyncio
    async def test_clear_conversation(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.set_default_response("reply")
        await assistant.send_prompt("hello")
        assistant.clear_conversation()
        assert assistant.get_conversation_history() == []

    @pytest.mark.asyncio
    async def test_reset_clears_history_and_index(self):
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios([{"response": "a"}, {"response": "b"}])
        await assistant.send_prompt("x")
        assistant.reset()
        assert assistant.conversation_history == []
        assert assistant.current_scenario_index == 0


class TestScriptedAssistant:
    @pytest.mark.asyncio
    async def test_follows_script_order(self):
        assistant = ScriptedAssistant(
            script=[
                {"response": "step 1"},
                {"response": "step 2"},
                {"response": "step 3"},
            ],
            response_delay=0,
        )
        r1 = await assistant.send_prompt("anything")
        r2 = await assistant.send_prompt("anything")
        r3 = await assistant.send_prompt("anything")
        assert r1.text == "step 1"
        assert r2.text == "step 2"
        assert r3.text == "step 3"

    @pytest.mark.asyncio
    async def test_script_exhausted(self):
        assistant = ScriptedAssistant(script=[{"response": "only"}], response_delay=0)
        await assistant.send_prompt("first")
        resp = await assistant.send_prompt("second")
        assert resp.text == "[Script completed]"


class TestThinkingSimulation:
    @pytest.mark.asyncio
    async def test_thinking_with_scenario(self):
        """SimulatedAssistant streams thinking text before response when configured."""
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios(
            [
                {
                    "pattern": r"test",
                    "response": "final answer",
                    "thinking": "let me think...",
                }
            ]
        )

        thinking_chunks = []
        response_chunks = []
        resp = await assistant.send_prompt(
            "test",
            on_chunk=lambda c: response_chunks.append(c),
            on_thinking_chunk=lambda c: thinking_chunks.append(c),
        )

        assert "".join(thinking_chunks) == "let me think..."
        assert "".join(response_chunks) == "final answer"
        assert resp.text == "final answer"

    @pytest.mark.asyncio
    async def test_thinking_without_callback_doesnt_error(self):
        """Thinking text configured but no callback provided - should not error."""
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios(
            [{"pattern": r"test", "response": "ok", "thinking": "thinking..."}]
        )
        resp = await assistant.send_prompt(
            "test", on_chunk=None, on_thinking_chunk=None
        )
        assert resp.text == "ok"

    @pytest.mark.asyncio
    async def test_default_thinking(self):
        """Default thinking is used when no scenario matches."""
        assistant = SimulatedAssistant(response_delay=0)
        assistant.set_default_response("default reply")
        assistant.set_default_thinking("default thinking")

        thinking_chunks = []
        resp = await assistant.send_prompt(
            "unknown", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )

        assert "".join(thinking_chunks) == "default thinking"
        assert resp.text == "default reply"

    @pytest.mark.asyncio
    async def test_scenario_without_thinking(self):
        """Scenarios without thinking field don't stream thinking."""
        assistant = SimulatedAssistant(response_delay=0)
        assistant.configure_scenarios([{"pattern": r"test", "response": "reply only"}])

        thinking_chunks = []
        resp = await assistant.send_prompt(
            "test", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )

        assert thinking_chunks == []
        assert resp.text == "reply only"

    @pytest.mark.asyncio
    async def test_scripted_assistant_thinking(self):
        """ScriptedAssistant supports thinking in script entries."""
        assistant = ScriptedAssistant(
            script=[
                {"response": "step 1", "thinking": "analyzing..."},
                {"response": "step 2"},
            ],
            response_delay=0,
        )

        thinking_chunks = []
        r1 = await assistant.send_prompt(
            "anything", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )
        assert "".join(thinking_chunks) == "analyzing..."
        assert r1.text == "step 1"

        thinking_chunks.clear()
        r2 = await assistant.send_prompt(
            "anything", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )
        assert thinking_chunks == []  # No thinking for step 2
        assert r2.text == "step 2"

    @pytest.mark.asyncio
    async def test_echo_assistant_thinking(self):
        """EchoAssistant can optionally stream thinking before echoing."""
        assistant = EchoAssistant(prefix="", thinking_text="considering...")
        assistant.response_delay = 0

        thinking_chunks = []
        resp = await assistant.send_prompt(
            "hi", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )

        assert "".join(thinking_chunks) == "considering..."
        assert resp.text == "hi"

    @pytest.mark.asyncio
    async def test_add_scenario_with_thinking(self):
        """add_scenario method supports thinking parameter."""
        assistant = SimulatedAssistant(response_delay=0)
        assistant.add_scenario(
            response="answer", pattern=r"question", thinking="pondering..."
        )

        thinking_chunks = []
        resp = await assistant.send_prompt(
            "question", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )

        assert "".join(thinking_chunks) == "pondering..."
        assert resp.text == "answer"


class TestEchoAssistant:
    @pytest.mark.asyncio
    async def test_echoes_input(self):
        assistant = EchoAssistant(prefix="Echo: ", system_prompt=None)
        assistant.response_delay = 0
        resp = await assistant.send_prompt("test message")
        assert resp.text == "Echo: test message"

    @pytest.mark.asyncio
    async def test_custom_prefix(self):
        assistant = EchoAssistant(prefix=">> ")
        assistant.response_delay = 0
        resp = await assistant.send_prompt("hello")
        assert resp.text == ">> hello"

    @pytest.mark.asyncio
    async def test_echo_streaming(self):
        assistant = EchoAssistant(prefix="")
        assistant.response_delay = 0
        chunks = []
        await assistant.send_prompt("abc", on_chunk=lambda c: chunks.append(c))
        assert "".join(chunks) == "abc"


class TestSimulatedAssistantCancellation:
    @pytest.mark.asyncio
    async def test_cancellation_stops_streaming(self):
        """Cancelling the task should stop streaming immediately."""
        assistant = SimulatedAssistant(response_delay=0.01)
        # Use a long response so there's time to cancel
        assistant.set_default_response("x" * 1000)

        chunks = []

        async def run_and_cancel():
            task = asyncio.create_task(
                assistant.send_prompt("test", on_chunk=lambda c: chunks.append(c))
            )
            # Let it start streaming
            await asyncio.sleep(0.05)
            # Cancel the task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_and_cancel()

        # Should have received some chunks but not all 1000
        assert len(chunks) > 0
        assert len(chunks) < 1000

    @pytest.mark.asyncio
    async def test_cancellation_raises_cancelled_error(self):
        """Cancelling should properly raise CancelledError."""
        assistant = SimulatedAssistant(response_delay=0.01)
        # Use a very long response to ensure we can cancel before completion
        assistant.set_default_response("x" * 10000)

        task = asyncio.create_task(
            assistant.send_prompt("test", on_chunk=lambda c: None)
        )
        # Give it a tiny bit of time to start
        await asyncio.sleep(0.05)
        # Cancel the task
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_cancellation_during_thinking(self):
        """Cancelling during thinking should stop immediately."""
        assistant = SimulatedAssistant(response_delay=0.01)
        assistant.configure_scenarios([{"response": "answer", "thinking": "x" * 1000}])

        thinking_chunks = []

        async def run_and_cancel():
            task = asyncio.create_task(
                assistant.send_prompt(
                    "test", on_thinking_chunk=lambda c: thinking_chunks.append(c)
                )
            )
            # Let thinking start
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_and_cancel()

        # Should have received some thinking but not all
        assert len(thinking_chunks) > 0
        assert len(thinking_chunks) < 1000
