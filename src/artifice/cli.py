"""Simple command-line interface for artifice - GNU-style input/output mode."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

from artifice.agent import Agent, AnyLLMProvider
from artifice.core.config import load_config

logger = logging.getLogger(__name__)


async def run_prompt(
    prompt: str,
    model: str,
    system_prompt: str | None,
    api_key: str | None,
    provider: str | None,
    base_url: str | None,
) -> str:
    """Run a prompt through the LLM and return the response."""
    provider_instance = AnyLLMProvider(
        model=model,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
    )
    agent = Agent(provider=provider_instance, system_prompt=system_prompt, tools=None)
    response = await agent.send(prompt)
    return response.text


def main() -> None:
    """Main entry point for the art command."""
    parser = argparse.ArgumentParser(
        prog="art",
        description="Simple LLM prompt tool - reads from stdin or argument, outputs to stdout",
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Prompt string (if not provided, reads from stdin)",
    )
    parser.add_argument(
        "-a",
        "--agent",
        default=None,
        help="Agent name from config (uses config default if not specified)",
    )
    parser.add_argument(
        "-p",
        "--prompt-name",
        default=None,
        help="Named prompt from config to use as system prompt",
    )
    parser.add_argument(
        "-s",
        "--system-prompt",
        default=None,
        help="System prompt for the model",
    )
    parser.add_argument(
        "--logging",
        action="store_true",
        help="Enable logging to stderr",
    )
    args = parser.parse_args()

    if args.logging:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stderr,
        )

    config, config_error = load_config()
    if config_error:
        print(f"Configuration error: {config_error}", file=sys.stderr)
        sys.exit(1)

    prompt = args.prompt
    if prompt is None:
        if sys.stdin.isatty():
            print(
                "Error: No prompt provided. Use argument or pipe input.",
                file=sys.stderr,
            )
            sys.exit(1)
        prompt = sys.stdin.read()

    if not prompt.strip():
        sys.exit(0)

    agent_name = args.agent or config.agent
    if not agent_name or not config.agents:
        print(
            "Error: No agent specified. Use --agent or configure a default agent.",
            file=sys.stderr,
        )
        sys.exit(1)

    agent_def = config.agents.get(agent_name)
    if not agent_def:
        print(f"Error: Unknown agent '{agent_name}'", file=sys.stderr)
        sys.exit(1)

    model = agent_def.get("model")
    if not model:
        print(f"Error: Agent '{agent_name}' has no model defined", file=sys.stderr)
        sys.exit(1)

    api_key = agent_def.get("api_key")
    if api_key is None:
        env_var = agent_def.get("api_key_env")
        if env_var:
            api_key = os.environ.get(env_var)

    system_prompt = args.system_prompt
    if system_prompt is None:
        if args.prompt_name:
            if not config.prompts or args.prompt_name not in config.prompts:
                print(
                    f"Error: Unknown prompt '{args.prompt_name}'",
                    file=sys.stderr,
                )
                sys.exit(1)
            system_prompt = config.prompts[args.prompt_name]
        else:
            system_prompt = agent_def.get("system_prompt", config.system_prompt)

    provider = agent_def.get("provider")
    if provider and provider.lower() == "simulated":
        print("Error: Simulated agents not supported in CLI mode", file=sys.stderr)
        sys.exit(1)

    base_url = agent_def.get("base_url")

    try:
        response = asyncio.run(
            run_prompt(prompt, model, system_prompt, api_key, provider, base_url)
        )
        print(response, end="" if response.endswith("\n") else "\n")
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
