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


BASH_COMPLETION = """_art_completion() {
    local cur prev words cword
    _init_completion || return

    case ${prev} in
        -a|--agent)
            COMPREPLY=($(compgen -W "$(art --list-agents 2>/dev/null)" -- "${cur}"))
            return
            ;;
        -p|--prompt-name)
            COMPREPLY=($(compgen -W "$(art --list-prompts 2>/dev/null)" -- "${cur}"))
            return
            ;;
        -s|--system-prompt)
            return
            ;;
    esac

    if [[ ${cur} == -* ]]; then
        COMPREPLY=($(compgen -W "-a --agent -p --prompt-name -s --system-prompt --logging --list-agents --list-prompts --print-completion" -- "${cur}"))
    fi
}

complete -F _art_completion art
"""

ZSH_COMPLETION = """#compdef art

_art() {
    local -a agents prompts

    agents=(${(f)"$(art --list-agents 2>/dev/null)"})
    prompts=(${(f)"$(art --list-prompts 2>/dev/null)"})

    _arguments \\\\
        '1:prompt:' \\\\
        '-a[Agent name from config]:agent:($agents)' \\\\
        '--agent[Agent name from config]:agent:($agents)' \\\\
        '-p[Named prompt from config]:prompt:($prompts)' \\\\
        '--prompt-name[Named prompt from config]:prompt:($prompts)' \\\\
        '-s[System prompt for the model]:system prompt:' \\\\
        '--system-prompt[System prompt for the model]:system prompt:' \\\\
        '--logging[Enable logging to stderr]' \\\\
        '--list-agents[List available agent names]' \\\\
        '--list-prompts[List available prompt names]' \\\\
        '--print-completion[Print shell completion script]:shell:(bash zsh fish)'
}

_art
"""

FISH_COMPLETION = """complete -c art -f

complete -c art -s a -l agent -d 'Agent name from config' -a '(art --list-agents 2>/dev/null)'
complete -c art -s p -l prompt-name -d 'Named prompt from config' -a '(art --list-prompts 2>/dev/null)'
complete -c art -s s -l system-prompt -d 'System prompt for the model'
complete -c art -l logging -d 'Enable logging to stderr'
complete -c art -l list-agents -d 'List available agent names'
complete -c art -l list-prompts -d 'List available prompt names'
complete -c art -l print-completion -d 'Print shell completion script' -a 'bash zsh fish'
"""

ZSH_COMPLETION = """#compdef art

_art() {
    local -a agents prompts

    agents=(${(f)"$({art} --list-agents 2>/dev/null)"})
    prompts=(${(f)"$({art} --list-prompts 2>/dev/null)"})

    _arguments \\
        '1:prompt:' \\
        '-a[Agent name from config]:agent:($agents)' \\
        '--agent[Agent name from config]:agent:($agents)' \\
        '-p[Named prompt from config]:prompt:($prompts)' \\
        '--prompt-name[Named prompt from config]:prompt:($prompts)' \\
        '-s[System prompt for the model]:system prompt:' \\
        '--system-prompt[System prompt for the model]:system prompt:' \\
        '--logging[Enable logging to stderr]' \\
        '--list-agents[List available agent names]' \\
        '--list-prompts[List available prompt names]' \\
        '--print-completion[Print shell completion script]:shell:(bash zsh fish)'
}

_art
"""

FISH_COMPLETION = """complete -c art -f

complete -c art -s a -l agent -d 'Agent name from config' -a '({art} --list-agents 2>/dev/null)'
complete -c art -s p -l prompt-name -d 'Named prompt from config' -a '({art} --list-prompts 2>/dev/null)'
complete -c art -s s -l system-prompt -d 'System prompt for the model'
complete -c art -l logging -d 'Enable logging to stderr'
complete -c art -l list-agents -d 'List available agent names'
complete -c art -l list-prompts -d 'List available prompt names'
complete -c art -l print-completion -d 'Print shell completion script' -a 'bash zsh fish'
"""


def _print_completion(shell: str) -> None:
    """Print shell completion script."""
    scripts = {
        "bash": BASH_COMPLETION,
        "zsh": ZSH_COMPLETION,
        "fish": FISH_COMPLETION,
    }
    print(scripts.get(shell, ""))


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
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List available agent names (for shell completion)",
    )
    parser.add_argument(
        "--list-prompts",
        action="store_true",
        help="List available prompt names (for shell completion)",
    )
    parser.add_argument(
        "--print-completion",
        choices=["bash", "zsh", "fish"],
        help="Print shell completion script",
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

    if args.list_agents:
        if config.agents:
            for name in config.agents:
                print(name)
        sys.exit(0)

    if args.list_prompts:
        if config.prompts:
            for name in config.prompts:
                print(name)
        sys.exit(0)

    if args.print_completion:
        _print_completion(args.print_completion)
        sys.exit(0)

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
