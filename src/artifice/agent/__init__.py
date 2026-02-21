"""Backward compatibility re-export for agent module."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from artifice.agent.client import Agent, AgentResponse
from artifice.agent.providers import (
    AnyLLMProvider,
    Provider,
    StreamChunk,
    TokenUsage,
)
from artifice.agent.simulated import EchoAgent, ScriptedAgent, SimulatedAgent
from artifice.agent.tools.base import TOOLS, ToolCall, ToolDef, execute_tool_call

if TYPE_CHECKING:
    from collections.abc import Callable

    from artifice.core.config import ArtificeConfig

__all__ = [
    "Agent",
    "AgentResponse",
    "AnyLLMProvider",
    "EchoAgent",
    "execute_tool_call",
    "Provider",
    "ScriptedAgent",
    "SimulatedAgent",
    "StreamChunk",
    "ToolCall",
    "ToolDef",
    "TokenUsage",
    "TOOLS",
]

logger = logging.getLogger(__name__)


def create_agent(
    config: ArtificeConfig, on_connect: Callable | None = None
) -> Agent | SimulatedAgent | None:
    """Instantiate an agent from the user's configuration."""
    if not config.agents or not config.agent:
        error = "No agent selected in configuration"
        raise ValueError(error)

    definition = config.agents.get(config.agent)
    if definition is None:
        error = f"Unknown agent: {config.agent!r}"
        raise ValueError(error)

    provider = definition.get("provider")
    model = definition.get("model")

    logger.info(
        "Creating agent %r (provider=%s, model=%s)",
        config.agent,
        provider,
        model,
    )

    if provider and provider.lower() == "simulated":
        agent = SimulatedAgent(
            system_prompt=config.system_prompt,
            on_connect=on_connect,
        )
        agent.configure_defaults()
        return agent

    if model is None:
        error = f"Agent {config.agent!r} requires a 'model' key in its definition"
        raise ValueError(error)

    # Resolve API key
    api_key: str | None = definition.get("api_key")
    if api_key is None:
        env_var = definition.get("api_key_env")
        if env_var:
            api_key = os.environ.get(env_var)

    system_prompt = definition.get("system_prompt", config.system_prompt)

    # Parse tools list (new format) with backward compat for use_tools bool
    tools: list[str] | None = definition.get("tools")
    if tools is None and definition.get("use_tools"):
        tools = ["*"]

    base_url: str | None = definition.get("base_url")
    # provider here is the any-llm provider override (not "simulated")
    llm_provider: str | None = (
        provider if provider and provider.lower() != "simulated" else None
    )

    return Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        api_key=api_key,
        provider_name=llm_provider,
        base_url=base_url,
        on_connect=on_connect,
    )
