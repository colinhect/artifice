""" module with provider/assistant architecture.

This module exports both the new provider/assistant classes and the
backward-compatible  classes.
"""

from typing import Callable

import os

from ..config import ArtificeConfig

# Core interfaces
from .common import AssistantBase as AssistantBase
from .common import AssistantResponse as AssistantResponse
from .provider import ProviderBase as ProviderBase
from .provider import ProviderResponse as ProviderResponse

# Assistant class (universal conversation manager)
from .assistant import Assistant as Assistant

# Provider implementations
from .providers.anthropic import AnthropicProvider as AnthropicProvider
from .providers.ollama import OllamaProvider as OllamaProvider
from .providers.openai import OpenAICompatibleProvider as OpenAICompatibleProvider
from .providers.copilot import CopilotProvider as CopilotProvider
from .providers.simulated import SimulatedProvider as SimulatedProvider

from .copilot import CopilotAssistant as CopilotAssistant
from .simulated import (
    SimulatedAssistant as SimulatedAssistant,
)


def create_assistant(
    config: ArtificeConfig, on_connect: Callable | None = None
) -> AssistantBase | None:
    if not config.models or not config.model:
        raise Exception("No model selected in configuration")

    model = config.models.get(config.model)
    if model is None:
        raise Exception(f"Unknown model: {config.model}")

    provider = model.get("provider")
    model_name = model.get("model")
    thinking_budget = model.get("thinking_budget")

    if config.thinking_budget is not None:
        thinking_budget = config.thinking_budget

    if provider is None:
        return None
    if provider.lower() == "ollama":
        return Assistant(
            provider=OllamaProvider(
                model=model_name,
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
                model=model_name,
                on_connect=on_connect,
            ),
            system_prompt=config.system_prompt,
            openai_format=True
        )
        return assistant
    elif provider.lower() == "anthropic":
        return Assistant(
            provider=AnthropicProvider(
                model=model_name,
                thinking_budget=thinking_budget,
                on_connect=on_connect,
            ),
            system_prompt=config.system_prompt,
        )
    elif provider.lower() == "copilot":
        return CopilotAssistant(
            model=model_name, system_prompt=config.system_prompt, on_connect=on_connect
        )
    elif provider.lower() == "simulated":
        assistant = SimulatedAssistant(response_delay=0.001, on_connect=on_connect)
        assistant.default_scenarios_and_response()
        return assistant
    else:
        raise Exception(f"Unsupported provider {provider}")
