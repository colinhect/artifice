"""Tests for SimulatedAgent, ScriptedAgent, EchoAgent."""

import asyncio
import pytest
from artifice.agent import SimulatedAgent, ScriptedAgent, EchoAgent


class TestSimulatedAgentPatternMatching:
    @pytest.mark.asyncio
    async def test_pattern_match(self):
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios(
            [
                {"pattern": r"hello|hi", "response": "greeting!"},
                {"pattern": r"math|calc", "response": "calculating!"},
            ]
        )
        resp = await agent.send("hello there")
        assert resp.text == "greeting!"

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self):
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios(
            [
                {"pattern": r"hello", "response": "matched!"},
            ]
        )
        resp = await agent.send("HELLO WORLD")
        assert resp.text == "matched!"

    @pytest.mark.asyncio
    async def test_no_match_uses_default(self):
        agent = SimulatedAgent(response_delay=0)
        agent.set_default_response("no match")
        agent.configure_scenarios(
            [
                {"pattern": r"specific", "response": "found!"},
            ]
        )
        resp = await agent.send("something else")
        assert resp.text == "no match"

    @pytest.mark.asyncio
    async def test_first_matching_pattern_wins(self):
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios(
            [
                {"pattern": r"test", "response": "first"},
                {"pattern": r"test", "response": "second"},
            ]
        )
        resp = await agent.send("test")
        assert resp.text == "first"


class TestSimulatedAgentSequential:
    @pytest.mark.asyncio
    async def test_sequential_scenarios(self):
        """Scenarios without patterns are used sequentially."""
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios(
            [
                {"response": "first"},
                {"response": "second"},
                {"response": "third"},
            ]
        )
        r1 = await agent.send("anything")
        r2 = await agent.send("anything")
        r3 = await agent.send("anything")
        assert r1.text == "first"
        assert r2.text == "second"
        assert r3.text == "third"

    @pytest.mark.asyncio
    async def test_sequential_exhausted_uses_default(self):
        agent = SimulatedAgent(response_delay=0)
        agent.set_default_response("fallback")
        agent.configure_scenarios([{"response": "only one"}])
        await agent.send("first")
        resp = await agent.send("second")
        assert resp.text == "fallback"


class TestSimulatedAgentStreaming:
    @pytest.mark.asyncio
    async def test_streaming_chunks(self):
        agent = SimulatedAgent(response_delay=0)
        agent.set_default_response("hello world")
        agent.configure_scenarios([])
        chunks = []
        await agent.send("test", on_chunk=lambda c: chunks.append(c))
        assert "".join(chunks) == "hello world"

    @pytest.mark.asyncio
    async def test_streaming_matches_response(self):
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios([{"pattern": r"test", "response": "abc"}])
        chunks = []
        resp = await agent.send("test", on_chunk=lambda c: chunks.append(c))
        assert "".join(chunks) == resp.text


class TestSimulatedAgentHistory:
    @pytest.mark.asyncio
    async def test_conversation_history_tracked(self):
        agent = SimulatedAgent(response_delay=0)
        agent.set_default_response("reply")
        agent.configure_scenarios([])
        await agent.send("hello")
        history = agent.get_conversation_history()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "reply"}

    @pytest.mark.asyncio
    async def test_clear(self):
        agent = SimulatedAgent(response_delay=0)
        agent.set_default_response("reply")
        agent.configure_scenarios([])
        await agent.send("hello")
        agent.clear()
        assert agent.get_conversation_history() == []

    @pytest.mark.asyncio
    async def test_reset_clears_history_and_index(self):
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios([{"response": "a"}, {"response": "b"}])
        await agent.send("x")
        agent.reset()
        assert agent.messages == []
        assert agent.current_scenario_index == 0


class TestScriptedAgent:
    @pytest.mark.asyncio
    async def test_follows_script_order(self):
        agent = ScriptedAgent(
            script=[
                {"response": "step 1"},
                {"response": "step 2"},
                {"response": "step 3"},
            ],
            response_delay=0,
        )
        r1 = await agent.send("anything")
        r2 = await agent.send("anything")
        r3 = await agent.send("anything")
        assert r1.text == "step 1"
        assert r2.text == "step 2"
        assert r3.text == "step 3"

    @pytest.mark.asyncio
    async def test_script_exhausted(self):
        agent = ScriptedAgent(script=[{"response": "only"}], response_delay=0)
        await agent.send("first")
        resp = await agent.send("second")
        assert resp.text == "[Script completed]"


class TestThinkingSimulation:
    @pytest.mark.asyncio
    async def test_thinking_with_scenario(self):
        """SimulatedAgent streams thinking text before response when configured."""
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios(
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
        resp = await agent.send(
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
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios(
            [{"pattern": r"test", "response": "ok", "thinking": "thinking..."}]
        )
        resp = await agent.send("test", on_chunk=None, on_thinking_chunk=None)
        assert resp.text == "ok"

    @pytest.mark.asyncio
    async def test_default_thinking(self):
        """Default thinking is used when no scenario matches."""
        agent = SimulatedAgent(response_delay=0)
        agent.set_default_response("default reply")
        agent.set_default_thinking("default thinking")
        agent.configure_scenarios([])

        thinking_chunks = []
        resp = await agent.send(
            "unknown", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )

        assert "".join(thinking_chunks) == "default thinking"
        assert resp.text == "default reply"

    @pytest.mark.asyncio
    async def test_scenario_without_thinking(self):
        """Scenarios without thinking field don't stream thinking."""
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios([{"pattern": r"test", "response": "reply only"}])

        thinking_chunks = []
        resp = await agent.send(
            "test", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )

        assert thinking_chunks == []
        assert resp.text == "reply only"

    @pytest.mark.asyncio
    async def test_scripted_agent_thinking(self):
        """ScriptedAgent supports thinking in script entries."""
        agent = ScriptedAgent(
            script=[
                {"response": "step 1", "thinking": "analyzing..."},
                {"response": "step 2"},
            ],
            response_delay=0,
        )

        thinking_chunks = []
        r1 = await agent.send(
            "anything", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )
        assert "".join(thinking_chunks) == "analyzing..."
        assert r1.text == "step 1"

        thinking_chunks.clear()
        r2 = await agent.send(
            "anything", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )
        assert thinking_chunks == []
        assert r2.text == "step 2"

    @pytest.mark.asyncio
    async def test_echo_agent_thinking(self):
        """EchoAgent can optionally stream thinking before echoing."""
        agent = EchoAgent(prefix="", thinking_text="considering...")
        agent.response_delay = 0

        thinking_chunks = []
        resp = await agent.send(
            "hi", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )

        assert "".join(thinking_chunks) == "considering..."
        assert resp.text == "hi"

    @pytest.mark.asyncio
    async def test_add_scenario_with_thinking(self):
        """add_scenario method supports thinking parameter."""
        agent = SimulatedAgent(response_delay=0)
        agent.configure_scenarios([])
        agent.add_scenario(
            response="answer", pattern=r"question", thinking="pondering..."
        )

        thinking_chunks = []
        resp = await agent.send(
            "question", on_thinking_chunk=lambda c: thinking_chunks.append(c)
        )

        assert "".join(thinking_chunks) == "pondering..."
        assert resp.text == "answer"


class TestEchoAgent:
    @pytest.mark.asyncio
    async def test_echoes_input(self):
        agent = EchoAgent(prefix="Echo: ")
        agent.response_delay = 0
        resp = await agent.send("test message")
        assert resp.text == "Echo: test message"

    @pytest.mark.asyncio
    async def test_custom_prefix(self):
        agent = EchoAgent(prefix=">> ")
        agent.response_delay = 0
        resp = await agent.send("hello")
        assert resp.text == ">> hello"

    @pytest.mark.asyncio
    async def test_echo_streaming(self):
        agent = EchoAgent(prefix="")
        agent.response_delay = 0
        chunks = []
        await agent.send("abc", on_chunk=lambda c: chunks.append(c))
        assert "".join(chunks) == "abc"


class TestSimulatedAgentCancellation:
    @pytest.mark.asyncio
    async def test_cancellation_stops_streaming(self):
        """Cancelling the task should stop streaming immediately."""
        agent = SimulatedAgent(response_delay=0.01)
        agent.set_default_response("x" * 1000)
        agent.configure_scenarios([])

        chunks = []

        async def run_and_cancel():
            task = asyncio.create_task(
                agent.send("test", on_chunk=lambda c: chunks.append(c))
            )
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_and_cancel()

        assert len(chunks) > 0
        assert len(chunks) < 1000

    @pytest.mark.asyncio
    async def test_cancellation_raises_cancelled_error(self):
        """Cancelling should properly raise CancelledError."""
        agent = SimulatedAgent(response_delay=0.01)
        agent.set_default_response("x" * 10000)
        agent.configure_scenarios([])

        task = asyncio.create_task(agent.send("test", on_chunk=lambda c: None))
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_cancellation_during_thinking(self):
        """Cancelling during thinking should stop immediately."""
        agent = SimulatedAgent(response_delay=0.01)
        agent.configure_scenarios([{"response": "answer", "thinking": "x" * 1000}])

        thinking_chunks = []

        async def run_and_cancel():
            task = asyncio.create_task(
                agent.send(
                    "test", on_thinking_chunk=lambda c: thinking_chunks.append(c)
                )
            )
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await run_and_cancel()

        assert len(thinking_chunks) > 0
        assert len(thinking_chunks) < 1000
