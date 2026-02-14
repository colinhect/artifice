"""Simulated AI agent for testing and development (backward compatibility wrapper)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .assistant import Assistant
from .common import AgentBase, AgentResponse
from .providers.simulated import SimulatedProvider

logger = logging.getLogger(__name__)


class SimulatedAgent(AgentBase):
    """A simulated AI agent that can be configured with predefined responses.

    This is a backward compatibility wrapper that delegates to Assistant + SimulatedProvider.

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
        self._provider = SimulatedProvider(
            on_connect=on_connect,
            response_delay=response_delay,
        )
        # Don't set up default scenarios by default (backward compatibility)
        self._provider.scenarios = []
        self._provider.default_response = (
            "I'm a simulated AI agent. I can be configured with custom responses."
        )
        self._provider.default_thinking = None

        self._assistant = Assistant(provider=self._provider, system_prompt=system_prompt)

    def default_scenarios_and_response(self):
        """Configure default test scenarios."""
        self._provider._setup_default_scenarios()

    def configure_scenarios(self, scenarios: list[dict[str, Any]]) -> None:
        """Configure the agent with predefined scenarios.

        Each scenario is a dict with:
        - 'response': str - The text response to stream
        - 'pattern': str - Optional regex pattern to match against prompts
        - 'thinking': str - Optional thinking text to stream before response
        """
        self._provider.configure_scenarios(scenarios)

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
        self._provider.scenarios.append(scenario)

    def set_default_response(self, response: str) -> None:
        """Set the default response when no scenarios match."""
        self._provider.set_default_response(response)

    def set_default_thinking(self, thinking: str | None) -> None:
        """Set the default thinking text when no scenarios match."""
        self._provider.set_default_thinking(thinking)

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
        return await self._assistant.send_prompt(prompt, on_chunk, on_thinking_chunk)

    def reset(self) -> None:
        """Reset the agent's conversation history and scenario index."""
        self._assistant.clear_conversation()
        self._provider.current_scenario_index = 0

    def clear_conversation(self) -> None:
        """Clear the conversation history (alias for reset without resetting scenario index)."""
        self._assistant.clear_conversation()

    def get_conversation_history(self) -> list[dict[str, Any]]:
        """Get the conversation history."""
        return self._assistant.messages.copy()

    @property
    def messages(self):
        """Expose messages for any code that accesses agent.messages."""
        return self._assistant.messages

    @property
    def conversation_history(self):
        """Alias for messages (backward compatibility)."""
        return self._assistant.messages

    @property
    def current_scenario_index(self):
        """Expose current_scenario_index for backward compatibility."""
        return self._provider.current_scenario_index

    @property
    def scenarios(self):
        """Expose scenarios for backward compatibility."""
        return self._provider.scenarios


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
        if self._provider.current_scenario_index < len(self._provider.scenarios):
            scenario = self._provider.scenarios[self._provider.current_scenario_index]
            response_text = scenario["response"]
            thinking_text = scenario.get("thinking")
            self._provider.current_scenario_index += 1
        else:
            response_text = "[Script completed]"
            thinking_text = None

        # Stream thinking text if available
        if thinking_text and on_thinking_chunk:
            for char in thinking_text:
                on_thinking_chunk(char)
                await asyncio.sleep(self._provider.response_delay)

        # Stream response text
        if on_chunk:
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self._provider.response_delay)

        self._assistant.messages.append({"role": "user", "content": prompt})
        self._assistant.messages.append(
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
                await asyncio.sleep(self._provider.response_delay)

        # Stream response text
        if on_chunk:
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self._provider.response_delay)

        logger.info(
            f"[EchoAgent] Received response ({len(response_text)} chars): {response_text}"
        )
        return AgentResponse(text=response_text, stop_reason="end_turn")
