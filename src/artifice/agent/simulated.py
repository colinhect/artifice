"""Simulated AI agent for testing and development."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .common import AgentBase, AgentResponse

logger = logging.getLogger(__name__)


class SimulatedAgent(AgentBase):
    """A simulated AI agent that can be configured with predefined responses.

    This agent is useful for:
    - Testing the agent interaction flow without API costs
    - Development and debugging
    - Creating reproducible test scenarios
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        on_connect: Callable | None = None,
        response_delay: float = 0.05,
    ):
        """Initialize the simulated agent.

        Args:
            system_prompt: System prompt (not used by simulated agent but kept for API compatibility)
            on_connect: Optional callback called on initialization
            response_delay: Delay between streaming chunks (seconds) to simulate typing
        """
        self.system_prompt = system_prompt
        self.on_connect = on_connect
        self.response_delay = response_delay
        self.conversation_history: list[dict[str, Any]] = []

        # Configuration for responses
        self.scenarios: list[dict[str, Any]] = []
        self.current_scenario_index = 0
        self.default_response = (
            "I'm a simulated AI agent. I can be configured with custom responses."
        )
        self.default_thinking: str | None = None

    def default_scenarios_and_response(self):
        self.configure_scenarios(
            [
                {
                    "pattern": r"hello|hi|hey",
                    "response": "Hello! I'm a **simulated** agent. How can I help you today?",
                    "thinking": "The user is greeting me. I should respond in a friendly manner and offer to help.",
                },
                {
                    "pattern": r"blank",
                    "response": '```python\nimport time\ntime.sleep(3)\nresult = 10 + 5\nprint(f"The result is: {result}")\n```\n\nI can help with that calculation!\n\n```python\nresult = 10 + 5\nprint(f"The result is: {result}")\n```\n\nThere it is, leave it or not',
                    "thinking": "Let me think about this problem. I need to write some Python code to demonstrate a calculation with a delay.",
                },
                {
                    "pattern": r"calculate|math|sum|add",
                    "response": 'I can help with that calculation!\n\n```python\nresult = 10 + 5\nprint(f"The result is: {result}")\n```\n\nI can help with that calculation!\n\n```python\nresult = 10 + 5\nprint(f"The result is: {result}")\n```\n\nThere it is, leave it or not',
                    "thinking": "The user wants me to perform a calculation. I should write Python code to compute the result and display it clearly.",
                },
                {
                    "pattern": r"goodbye|bye|exit",
                    "response": "Goodbye! Thanks for chatting with me.",
                    "thinking": "The user is saying goodbye. I should acknowledge and thank them for the conversation.",
                },
            ]
        )
        self.set_default_response(
            "I'm not sure how to respond to that. Try asking about math or saying hello!"
        )
        self.set_default_thinking(
            "Hmm, I'm not sure how to respond to this. Let me think about what the user might be asking for."
        )

    def configure_scenarios(self, scenarios: list[dict[str, Any]]) -> None:
        """Configure the agent with predefined scenarios.

        Each scenario is a dict with:
        - 'response': str - The text response to stream
        - 'pattern': str - Optional regex pattern to match against prompts
        - 'thinking': str - Optional thinking text to stream before response

        Example:
            agent.configure_scenarios([
                {
                    'pattern': r'hello|hi',
                    'response': 'Hello! How can I help you today?',
                    'thinking': 'The user is greeting me. I should respond politely.'
                },
                {
                    'pattern': r'calculate|sum',
                    'response': 'Let me calculate that for you.\\n\\n```python\\nresult = 2 + 2\\nprint(result)\\n```',
                    'thinking': 'I need to write Python code to perform this calculation.'
                }
            ])
        """
        self.scenarios = scenarios
        self.current_scenario_index = 0

    def add_scenario(
        self, response: str, pattern: str | None = None, thinking: str | None = None
    ) -> None:
        """Add a single scenario to the configuration.

        Args:
            response: The text response to stream
            pattern: Optional regex pattern to match against prompts
            thinking: Optional thinking text to stream before response
        """
        scenario = {"response": response, "pattern": pattern}
        if thinking is not None:
            scenario["thinking"] = thinking
        self.scenarios.append(scenario)

    def set_default_response(self, response: str) -> None:
        """Set the default response when no scenarios match."""
        self.default_response = response

    def set_default_thinking(self, thinking: str | None) -> None:
        """Set the default thinking text when no scenarios match."""
        self.default_thinking = thinking

    def _find_matching_scenario(self, prompt: str) -> dict[str, Any] | None:
        """Find a scenario that matches the given prompt."""
        import re

        # First, try to match patterns
        for scenario in self.scenarios:
            pattern = scenario.get("pattern")
            if pattern:
                if re.search(pattern, prompt, re.IGNORECASE):
                    return scenario

        # No pattern matched, try sequential scenarios (those without patterns)
        scenarios_without_patterns = [s for s in self.scenarios if not s.get("pattern")]
        if self.current_scenario_index < len(scenarios_without_patterns):
            scenario = scenarios_without_patterns[self.current_scenario_index]
            self.current_scenario_index += 1
            return scenario

        return None

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse:
        """Send a prompt to the simulated agent.

        Args:
            prompt: The user's prompt
            on_chunk: Optional callback for streaming response chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            AgentResponse with the simulated response
        """
        if self.on_connect:
            self.on_connect("Artifice")
            self.on_connect = None
        # await asyncio.sleep(2)
        # Add prompt to conversation history
        self.conversation_history.append({"role": "user", "content": prompt})
        logger.info(f"[SimulatedAgent] Sending prompt: {prompt}")

        # Find matching scenario
        scenario = self._find_matching_scenario(prompt)

        if scenario:
            response_text = scenario["response"]
            thinking_text = scenario.get("thinking")
        else:
            response_text = self.default_response
            thinking_text = self.default_thinking

        # Stream thinking text if available
        if thinking_text and on_thinking_chunk:
            logger.info(
                f"[SimulatedAgent] Streaming thinking ({len(thinking_text)} chars)"
            )
            for char in thinking_text:
                on_thinking_chunk(char)
                await asyncio.sleep(self.response_delay)

        # Stream the response text
        if on_chunk:
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self.response_delay)

        # Add assistant response to history
        self.conversation_history.append(
            {"role": "assistant", "content": response_text}
        )
        logger.info(
            f"[SimulatedAgent] Received response ({len(response_text)} chars): {response_text}"
        )

        return AgentResponse(text=response_text, stop_reason="end_turn")

    def reset(self) -> None:
        """Reset the agent's conversation history and scenario index."""
        self.conversation_history.clear()
        self.current_scenario_index = 0

    def clear_conversation(self) -> None:
        """Clear the conversation history (alias for reset without resetting scenario index)."""
        self.conversation_history.clear()

    def get_conversation_history(self) -> list[dict[str, Any]]:
        """Get the conversation history."""
        return self.conversation_history.copy()


class ScriptedAgent(SimulatedAgent):
    """A simulated agent that follows a predefined script of interactions.

    This is useful for creating demos or tutorials where you want to show
    a specific sequence of interactions.
    """

    def __init__(
        self,
        script: list[dict[str, Any]],
        system_prompt: str | None = None,
        response_delay: float = 0.05,
    ):
        """Initialize the scripted agent.

        Args:
            script: List of script entries, each with 'response'
            system_prompt: System prompt (for API compatibility)
            response_delay: Delay between streaming chunks
        """
        super().__init__(system_prompt=system_prompt, response_delay=response_delay)
        self.configure_scenarios(script)

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse:
        """Send a prompt and return the next scripted response."""
        if self.current_scenario_index < len(self.scenarios):
            scenario = self.scenarios[self.current_scenario_index]
            response_text = scenario["response"]
            thinking_text = scenario.get("thinking")
            self.current_scenario_index += 1
        else:
            response_text = "[Script completed]"
            thinking_text = None

        # Stream thinking text if available
        if thinking_text and on_thinking_chunk:
            for char in thinking_text:
                on_thinking_chunk(char)
                await asyncio.sleep(self.response_delay)

        # Stream response text
        if on_chunk:
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self.response_delay)

        self.conversation_history.append({"role": "user", "content": prompt})
        self.conversation_history.append(
            {"role": "assistant", "content": response_text}
        )

        return AgentResponse(text=response_text, stop_reason="end_turn")


class EchoAgent(SimulatedAgent):
    """A simple agent that echoes back the user's input with optional formatting."""

    def __init__(
        self,
        prefix: str = "You said: ",
        system_prompt: str | None = None,
        thinking_text: str | None = None,
    ):
        """Initialize the echo agent.

        Args:
            prefix: Prefix to add before echoing the input
            system_prompt: System prompt (for API compatibility)
            thinking_text: Optional thinking text to stream before echoing
        """
        super().__init__(system_prompt)
        self.prefix = prefix
        self.echo_thinking = thinking_text

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Callable[[str], None] | None = None,
        on_thinking_chunk: Callable[[str], None] | None = None,
    ) -> AgentResponse:
        """Echo the prompt back with the configured prefix."""
        logger.info(f"[EchoAgent] Sending prompt: {prompt}")
        response_text = f"{self.prefix}{prompt}"

        # Stream thinking text if configured
        if self.echo_thinking and on_thinking_chunk:
            for char in self.echo_thinking:
                on_thinking_chunk(char)
                await asyncio.sleep(self.response_delay)

        # Stream response text
        if on_chunk:
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self.response_delay)

        logger.info(
            f"[EchoAgent] Received response ({len(response_text)} chars): {response_text}"
        )
        return AgentResponse(text=response_text, stop_reason="end_turn")
