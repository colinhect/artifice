"""Simulated AI agent for testing and development."""

import asyncio
import logging
from typing import Any, Callable, Optional

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
        system_prompt: Optional[str] = None,
        on_connect: Optional[Callable] = None,
        response_delay: float = 0.05,
    ):
        """Initialize the simulated agent.

        Args:
            system_prompt: System prompt (not used by simulated agent but kept for API compatibility)
            on_connect: Optional callback called on initialization
            response_delay: Delay between streaming chunks (seconds) to simulate typing
        """
        self.system_prompt = system_prompt
        self.response_delay = response_delay
        self.conversation_history: list[dict[str, Any]] = []

        # Configuration for responses
        self.scenarios: list[dict[str, Any]] = []
        self.current_scenario_index = 0
        self.default_response = "I'm a simulated AI agent. I can be configured with custom responses."

        if on_connect:
            on_connect("Artifice")

    def configure_scenarios(self, scenarios: list[dict[str, Any]]) -> None:
        """Configure the agent with predefined scenarios.

        Each scenario is a dict with:
        - 'response': str - The text response to stream
        - 'pattern': str - Optional regex pattern to match against prompts

        Example:
            agent.configure_scenarios([
                {
                    'pattern': r'hello|hi',
                    'response': 'Hello! How can I help you today?'
                },
                {
                    'pattern': r'calculate|sum',
                    'response': 'Let me calculate that for you.\\n\\n```python\\nresult = 2 + 2\\nprint(result)\\n```',
                }
            ])
        """
        self.scenarios = scenarios
        self.current_scenario_index = 0

    def add_scenario(self, response: str, pattern: Optional[str] = None) -> None:
        """Add a single scenario to the configuration.

        Args:
            response: The text response to stream
            pattern: Optional regex pattern to match against prompts
        """
        self.scenarios.append({
            'response': response,
            'pattern': pattern
        })

    def set_default_response(self, response: str) -> None:
        """Set the default response when no scenarios match."""
        self.default_response = response

    def _find_matching_scenario(self, prompt: str) -> Optional[dict[str, Any]]:
        """Find a scenario that matches the given prompt."""
        import re

        # First, try to match patterns
        for scenario in self.scenarios:
            pattern = scenario.get('pattern')
            if pattern:
                if re.search(pattern, prompt, re.IGNORECASE):
                    return scenario

        # No pattern matched, try sequential scenarios (those without patterns)
        scenarios_without_patterns = [s for s in self.scenarios if not s.get('pattern')]
        if self.current_scenario_index < len(scenarios_without_patterns):
            scenario = scenarios_without_patterns[self.current_scenario_index]
            self.current_scenario_index += 1
            return scenario

        return None

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> AgentResponse:
        """Send a prompt to the simulated agent.

        Args:
            prompt: The user's prompt
            on_chunk: Optional callback for streaming response chunks

        Returns:
            AgentResponse with the simulated response
        """
        # Add prompt to conversation history
        self.conversation_history.append({
            'role': 'user',
            'content': prompt
        })
        logger.info(f"[SimulatedAgent] Sending prompt: {prompt}")

        # Find matching scenario
        scenario = self._find_matching_scenario(prompt)

        if scenario:
            response_text = scenario['response']
        else:
            response_text = self.default_response

        # Stream the response text
        if on_chunk:
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self.response_delay)

        # Add assistant response to history
        self.conversation_history.append({
            'role': 'assistant',
            'content': response_text
        })
        logger.info(f"[SimulatedAgent] Received response ({len(response_text)} chars): {response_text}")

        return AgentResponse(
            text=response_text,
            stop_reason="end_turn"
        )

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
        system_prompt: Optional[str] = None,
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
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> AgentResponse:
        """Send a prompt and return the next scripted response."""
        # Always use the next scenario in order, ignore pattern matching
        if self.current_scenario_index < len(self.scenarios):
            scenario = self.scenarios[self.current_scenario_index]
            self.current_scenario_index += 1

            # Temporarily set as the only scenario for parent method
            original_scenarios = self.scenarios
            original_index = self.current_scenario_index
            self.scenarios = [scenario]
            self.current_scenario_index = 0

            result = await super().send_prompt(prompt, on_chunk)

            # Restore original state
            self.scenarios = original_scenarios
            self.current_scenario_index = original_index
            return result
        else:
            # Script exhausted
            return AgentResponse(
                text="[Script completed]",
                stop_reason="end_turn"
            )


class EchoAgent(SimulatedAgent):
    """A simple agent that echoes back the user's input with optional formatting."""

    def __init__(
        self,
        prefix: str = "You said: ",
        system_prompt: Optional[str] = None,
    ):
        """Initialize the echo agent.

        Args:
            prefix: Prefix to add before echoing the input
            system_prompt: System prompt (for API compatibility)
        """
        super().__init__(system_prompt)
        self.prefix = prefix

    async def send_prompt(
        self,
        prompt: str,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> AgentResponse:
        """Echo the prompt back with the configured prefix."""
        logger.info(f"[EchoAgent] Sending prompt: {prompt}")
        response_text = f"{self.prefix}{prompt}"

        if on_chunk:
            for char in response_text:
                on_chunk(char)
                await asyncio.sleep(self.response_delay)

        logger.info(f"[EchoAgent] Received response ({len(response_text)} chars): {response_text}")
        return AgentResponse(
            text=response_text,
            stop_reason="end_turn"
        )
