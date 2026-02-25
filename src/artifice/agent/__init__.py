"""Agent module: client, providers, tools, and configuration resolution."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from artifice.agent.client import Agent, AgentResponse
from artifice.agent.providers import (
    AnyLLMProvider,
    CopilotProvider,
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
    "AgentConfig",
    "AgentResponse",
    "AnyLLMProvider",
    "CopilotProvider",
    "EchoAgent",
    "execute_tool_call",
    "Provider",
    "resolve_agent_config",
    "ScriptedAgent",
    "SimulatedAgent",
    "StreamChunk",
    "ToolCall",
    "ToolDef",
    "TokenUsage",
    "TOOLS",
]

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Resolved agent configuration extracted from user config."""

    model: str
    api_key: str | None
    provider: str | None
    base_url: str | None
    system_prompt: str | None
    tools: list[str] | None


def resolve_agent_config(
    config: ArtificeConfig, agent_name: str | None = None
) -> AgentConfig:
    """Extract and validate agent settings from the user configuration.

    Args:
        config: The loaded ArtificeConfig.
        agent_name: Override agent name (defaults to config.agent).

    Returns:
        An AgentConfig with all fields resolved.

    Raises:
        ValueError: If the agent cannot be resolved.
    """
    name = agent_name or config.agent
    if not name or not config.agents:
        msg = "No agent specified. Use --agent or configure a default agent."
        raise ValueError(msg)

    definition = config.agents.get(name)
    if definition is None:
        msg = f"Unknown agent: {name!r}"
        raise ValueError(msg)

    model = definition.get("model")
    if not model:
        msg = f"Agent {name!r} has no model defined"
        raise ValueError(msg)

    api_key: str | None = definition.get("api_key")
    if api_key is None:
        env_var = definition.get("api_key_env")
        if env_var:
            api_key = os.environ.get(env_var)

    provider: str | None = definition.get("provider")
    base_url: str | None = definition.get("base_url")
    system_prompt = definition.get("system_prompt", config.system_prompt)
    tools: list[str] | None = definition.get("tools")

    return AgentConfig(
        model=model,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
        system_prompt=system_prompt,
        tools=tools,
    )


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

    agent_config = resolve_agent_config(config)

    llm_provider: str | None = (
        agent_config.provider
        if agent_config.provider and agent_config.provider.lower() != "simulated"
        else None
    )

    if llm_provider and llm_provider.lower() == "copilot":
        provider_instance = CopilotProvider(
            model=agent_config.model,
        )
    else:
        provider_instance = AnyLLMProvider(
            model=agent_config.model,
            api_key=agent_config.api_key,
            provider=llm_provider,
            base_url=agent_config.base_url,
        )

    return Agent(
        provider=provider_instance,
        system_prompt=agent_config.system_prompt,
        tools=agent_config.tools,
        on_connect=on_connect,
    )
