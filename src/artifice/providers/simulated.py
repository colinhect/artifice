"""Simulated provider for testing."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Optional

from .provider import ProviderBase, ProviderResponse

logger = logging.getLogger(__name__)


class SimulatedProvider(ProviderBase):
    """Simulated provider for testing without API costs.

    Can be configured with predefined scenarios that match patterns or
    respond sequentially.
    """

    def __init__(
        self,
        on_connect: Callable | None = None,
        response_delay: float = 0.05,
    ):
        """Initialize simulated provider.

        Args:
            on_connect: Optional callback called on initialization
            response_delay: Delay between streaming chunks (seconds) to simulate typing
        """
        self.on_connect = on_connect
        self.response_delay = response_delay

        # Configuration for responses
        self.scenarios: list[dict[str, Any]] = []
        self.current_scenario_index = 0
        self.default_response = (
            "I'm a simulated AI . I can be configured with custom responses."
        )
        self.default_thinking: str | None = None

        # Set up default scenarios
        self._setup_default_scenarios()

    def _setup_default_scenarios(self):
        """Set up default test scenarios."""
        self.scenarios = [
            {
                "pattern": r"hello|hi|hey",
                "response": "Hello! I'm a **simulated** . How can I help you today?",
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
        self.default_response = "I'm not sure how to respond to that. Try asking about math or saying hello!"
        self.default_thinking = "Hmm, I'm not sure how to respond to this. Let me think about what the user might be asking for."

    def configure_scenarios(self, scenarios: list[dict[str, Any]]) -> None:
        """Configure the provider with predefined scenarios.

        Each scenario is a dict with:
        - 'response': str - The text response to stream
        - 'pattern': str - Optional regex pattern to match against prompts
        - 'thinking': str - Optional thinking text to stream before response
        """
        self.scenarios = scenarios
        self.current_scenario_index = 0

    def set_default_response(self, response: str) -> None:
        """Set the default response when no scenarios match."""
        self.default_response = response

    def set_default_thinking(self, thinking: str | None) -> None:
        """Set the default thinking text when no scenarios match."""
        self.default_thinking = thinking

    def _find_matching_scenario(self, prompt: str) -> dict[str, Any] | None:
        """Find a scenario that matches the given prompt."""
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

    async def send(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
        on_chunk: Optional[Callable] = None,
        on_thinking_chunk: Optional[Callable] = None,
    ) -> ProviderResponse:
        """Send messages to simulated provider and stream response.

        Args:
            messages: Full conversation history
            system_prompt: Optional system prompt (ignored for simulation)
            on_chunk: Optional callback for streaming text chunks
            on_thinking_chunk: Optional callback for streaming thinking chunks

        Returns:
            ProviderResponse with the simulated response
        """
        if self.on_connect:
            self.on_connect("Artifice")
            self.on_connect = None

        # Extract last user message
        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                prompt = msg.get("content", "")
                break

        logger.info(f"[SimulatedProvider] Processing prompt: {prompt}")

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
                f"[SimulatedProvider] Streaming thinking ({len(thinking_text)} chars)"
            )
            for char in thinking_text:
                on_thinking_chunk(char)
                await asyncio.sleep(self.response_delay)

        # Stream the response text
        if on_chunk:
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self.response_delay)

        logger.info(
            f"[SimulatedProvider] Response complete ({len(response_text)} chars)"
        )

        return ProviderResponse(
            text=response_text,
            stop_reason="end_turn",
            thinking=thinking_text,
        )
