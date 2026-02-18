"""Module with provider/assistant architecture."""

import logging
from typing import Callable

import os

from ..config import ArtificeConfig

# Core interfaces
from .common import AssistantBase as AssistantBase

# Assistant class (universal conversation manager)
from .assistant import Assistant as Assistant

# Provider implementations
from ..providers.anyllm import AnyLLMProvider as AnyLLMProvider
from .simulated import (
    SimulatedAssistant as SimulatedAssistant,
)

logger = logging.getLogger(__name__)


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
    logger.info(
        "Creating assistant %r (provider=%s, model=%s)",
        config.assistant,
        provider,
        model,
    )

    if provider is None:
        return None
    elif provider.lower() == "huggingface":
        use_tools = bool(assistant.get("use_tools", False))
        assistant = Assistant(
            provider=AnyLLMProvider(
                provider="huggingface",
                api_key=os.environ["HF_TOKEN"],
                model=model,
                on_connect=on_connect,
                use_tools=use_tools,
            ),
            system_prompt=config.system_prompt,
            openai_format=True,
        )
        return assistant
    elif provider.lower() == "simulated":
        assistant = SimulatedAssistant(response_delay=0.0005, on_connect=on_connect)
        assistant.default_scenarios_and_response()
        return assistant
    else:
        raise Exception(f"Unsupported provider {provider}")
