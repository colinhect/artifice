"""Agent - manages LLM conversation and tool calls via any-llm."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Callable

from .agent import Agent, AgentResponse, ToolCall
from .simulated import EchoAgent, ScriptedAgent, SimulatedAgent

if TYPE_CHECKING:
    from ..config import ArtificeConfig

__all__ = [
    "Agent",
    "AgentResponse",
    "EchoAgent",
    "ScriptedAgent",
    "SimulatedAgent",
    "ToolCall",
]

logger = logging.getLogger(__name__)


def create_agent(
    config: ArtificeConfig, on_connect: Callable | None = None
) -> Agent | SimulatedAgent | None:
    """Instantiate an agent from the user's configuration.

    Reads ``config.agent`` (the selected agent name) and
    ``config.agents`` (the dict of agent definitions). Each definition
    supports the following keys:

    - ``provider``: ``"simulated"`` or any string understood by any-llm
      (e.g. ``"openai"``, ``"moonshot"``). When omitted, ``model`` alone is
      used and any-llm auto-detects the provider.
    - ``model``: model identifier passed directly to any-llm.
    - ``api_key``: API key string. Alternatively, set ``api_key_env`` to read
      from an environment variable.
    - ``api_key_env``: Name of the environment variable holding the API key.
    - ``base_url``: Custom base URL for self-hosted or proxy endpoints.
    - ``use_tools``: Whether to register python/shell as native tools.
    - ``system_prompt``: Override the global system_prompt for this agent.
    """
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
    use_tools = bool(definition.get("use_tools", False))
    base_url: str | None = definition.get("base_url")
    # provider here is the any-llm provider override (not "simulated")
    llm_provider: str | None = (
        provider if provider and provider.lower() != "simulated" else None
    )

    return Agent(
        model=model,
        system_prompt=system_prompt,
        use_tools=use_tools,
        api_key=api_key,
        provider=llm_provider,
        base_url=base_url,
        on_connect=on_connect,
    )
