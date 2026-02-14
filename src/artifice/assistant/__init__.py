"""Module with provider/assistant architecture."""

from typing import Callable

import os

from ..config import ArtificeConfig

# Core interfaces
from .common import AssistantBase as AssistantBase

# Assistant class (universal conversation manager)
from .assistant import Assistant as Assistant

# Provider implementations
from ..providers.anthropic import AnthropicProvider as AnthropicProvider
from ..providers.ollama import OllamaProvider as OllamaProvider
from ..providers.openai import OpenAICompatibleProvider as OpenAICompatibleProvider

from .copilot import CopilotAssistant as CopilotAssistant
from .simulated import (
    SimulatedAssistant as SimulatedAssistant,
)


def create_assistant(
    config: ArtificeConfig, on_connect: Callable | None = None
) -> AssistantBase | None:
    if not config.assistants or not config.assistant:
        raise Exception("No assistant selected in configuration")

    assistant = config.assistants.get(config.assistant)
    if assistant is None:
        raise Exception(f"Unknown assistant: {config.assistant}")

    provider = assistant.get("provider")
    model = assistant.get("model")
    thinking_budget = assistant.get("thinking_budget")

    if config.thinking_budget is not None:
        thinking_budget = config.thinking_budget

    if provider is None:
        return None
    if provider.lower() == "ollama":
        return Assistant(
            provider=OllamaProvider(
                model=model,
                thinking_budget=thinking_budget,
                on_connect=on_connect,
            ),
            system_prompt=config.system_prompt,
        )
    elif provider.lower() == "huggingface":
        assistant = Assistant(
            provider=OpenAICompatibleProvider(
                base_url="https://router.huggingface.co/v1",
                api_key=os.environ["HF_TOKEN"],
                model=model,
                on_connect=on_connect,
            ),
            system_prompt=config.system_prompt,
            openai_format=True,
        )
        return assistant
    elif provider.lower() == "anthropic":
        return Assistant(
            provider=AnthropicProvider(
                model=model,
                thinking_budget=thinking_budget,
                on_connect=on_connect,
            ),
            system_prompt=config.system_prompt,
        )
    elif provider.lower() == "copilot":
        return CopilotAssistant(
            model=model, system_prompt=config.system_prompt, on_connect=on_connect
        )
    elif provider.lower() == "simulated":
        assistant = SimulatedAssistant(response_delay=0.005, on_connect=on_connect)
        assistant.default_scenarios_and_response()
        return assistant
    else:
        raise Exception(f"Unsupported provider {provider}")
