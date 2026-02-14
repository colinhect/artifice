from typing import Callable

from ..config import ArtificeConfig
from .common import AgentResponse as AgentResponse
from .common import AgentBase as AgentBase
from .claude import ClaudeAgent as ClaudeAgent
from .ollama import OllamaAgent as OllamaAgent
from .copilot import CopilotAgent as CopilotAgent
from .simulated import (
    SimulatedAgent as SimulatedAgent,
    ScriptedAgent as ScriptedAgent,
    EchoAgent as EchoAgent,
)


def create_agent(
    config: ArtificeConfig, on_connect: Callable | None = None
) -> AgentBase | None:
    if not config.models or not config.model:
        raise Exception("No model selected in configuration")

    model = config.models.get(config.model)
    if model is None:
        raise Exception(f"Unknown model: {model}")

    provider = model.get("provider")
    model_name = model.get("model")
    thinking_budget = model.get("thinking_budget")

    if config.thinking_budget is not None:
        thinking_budget = config.thinking_budget

    if provider is None:
        return None
    if provider.lower() == "ollama":
        return OllamaAgent(
            model=model_name,
            system_prompt=config.system_prompt,
            thinking_budget=thinking_budget,
            on_connect=on_connect,
        )
    elif provider.lower() == "anthropic":
        return ClaudeAgent(
            model=model_name,
            system_prompt=config.system_prompt,
            thinking_budget=thinking_budget,
            on_connect=on_connect,
        )
    elif provider.lower() == "copilot":
        return CopilotAgent(
            model=model_name, system_prompt=config.system_prompt, on_connect=on_connect
        )
    elif provider.lower() == "simulated":
        agent = SimulatedAgent(response_delay=0.001, on_connect=on_connect)
        agent.default_scenarios_and_response()
        return agent
    else:
        raise Exception(f"Unsupported agent provider {provider}")
