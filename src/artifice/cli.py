"""Simple command-line interface for artifice - GNU-style input/output mode."""

from __future__ import annotations

import argparse
import asyncio
import importlib.resources
import json
import logging
import os
import shutil
import sys
from typing import TYPE_CHECKING

from artifice.core.config import load_config, get_config_path, get_config_file_path
from artifice.core.prompts import list_prompts, load_prompt

if TYPE_CHECKING:
    from artifice.agent.tools.base import ToolCall

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
        COMPREPLY=($(compgen -W "-a --agent -p --prompt-name -s --system-prompt --logging --list-agents --list-prompts --get-current-agent --print-completion --tools --tool-approval" -- "${cur}"))
    fi
}

complete -F _art_completion art
"""

ZSH_COMPLETION = """#compdef art

_art() {
    local -a agents prompts

    agents=(${(f)"$(art --list-agents 2>/dev/null)"})
    prompts=(${(f)"$(art --list-prompts 2>/dev/null)"})

    _arguments \
        '1:prompt:' \
        '-a[Agent name from config]:agent:($agents)' \
        '--agent[Agent name from config]:agent:($agents)' \
        '-p[Named prompt from config]:prompt:($prompts)' \
        '--prompt-name[Named prompt from config]:prompt:($prompts)' \
        '-s[System prompt for the model]:system prompt:' \
        '--system-prompt[System prompt for the model]:system prompt:' \
        '--logging[Enable logging to stderr]' \
        '--list-agents[List available agent names]' \
        '--list-prompts[List available prompt names]' \
        '--get-current-agent[Print the current agent name and exit]' \
        '--print-completion[Print shell completion script]:shell:(bash zsh fish)' \
        '--tools[Tool patterns (e.g., "*", "read,write")]' \
        '--tool-approval[Tool approval mode]:mode:(ask auto deny)'
}
"""

FISH_COMPLETION = """complete -c art -f

complete -c art -s a -l agent -d 'Agent name from config' -a '(art --list-agents 2>/dev/null)'
complete -c art -s p -l prompt-name -d 'Named prompt from config' -a '(art --list-prompts 2>/dev/null)'
complete -c art -s s -l system-prompt -d 'System prompt for the model'
complete -c art -l logging -d 'Enable logging to stderr'
complete -c art -l list-agents -d 'List available agent names'
complete -c art -l list-prompts -d 'List available prompt names'
complete -c art -l get-current-agent -d 'Print the current agent name and exit'
complete -c art -l print-completion -d 'Print shell completion script' -a 'bash zsh fish'
complete -c art -l tools -d 'Tool patterns (e.g., "*", "read,write")'
complete -c art -l tool-approval -d 'Tool approval mode' -a 'ask auto deny'
"""


def _print_completion(shell: str) -> None:
    """Print shell completion script."""
    scripts = {
        "bash": BASH_COMPLETION,
        "zsh": ZSH_COMPLETION,
        "fish": FISH_COMPLETION,
    }
    print(scripts.get(shell, ""))


def install_config() -> None:
    """Install default configuration to ~/.artifice/."""
    config_dir = get_config_path()
    config_file = get_config_file_path()
    prompts_dir = config_dir / "prompts"

    if config_file.exists():
        print(f"Config already exists at {config_file}", file=sys.stderr)
        sys.exit(1)

    config_dir.mkdir(parents=True, exist_ok=True)

    try:
        example_config = importlib.resources.files("artifice.data").joinpath(
            "example.yaml"
        )
        with importlib.resources.as_file(example_config) as example_path:
            shutil.copy(example_path, config_file)
        print(f"Created {config_file}")

        prompts_source = importlib.resources.files("artifice.data.prompts")
        prompts_dir.mkdir(exist_ok=True)
        count = 0
        for prompt_file in prompts_source.iterdir():
            if prompt_file.is_file() and prompt_file.name.endswith(".md"):
                with importlib.resources.as_file(prompt_file) as prompt_path:
                    shutil.copy(prompt_path, prompts_dir / prompt_file.name)
                    count += 1
        print(f"Created {prompts_dir}/ ({count} prompts)")

        print("\nEdit the config file to customize your settings.")
    except Exception as e:
        print(f"Error creating config: {e}", file=sys.stderr)
        sys.exit(1)


class ToolApprover:
    """Manages tool call approval decisions."""

    def __init__(self, approval_mode: str, allowlist: list[str] | None = None) -> None:
        self.approval_mode = approval_mode
        self.allowlist = allowlist or []
        self.always_allowed: set[str] = set()
        self.session_allowed: set[str] = set()

    def is_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed based on approval mode and lists."""
        if self.approval_mode == "auto":
            return True
        if self.approval_mode == "deny":
            return False

        # Check permanent allowlist
        from fnmatch import fnmatch

        for pattern in self.allowlist:
            if fnmatch(tool_name, pattern):
                return True

        # Check always-allowed tools
        if tool_name in self.always_allowed:
            return True

        return False

    def prompt_approval(self, tool_call: ToolCall) -> str:
        """Prompt user for tool call approval.

        Returns one of: "allow", "deny", "always", "once"
        """
        print(f"\n🛠️  Tool Call: {tool_call.name}", file=sys.stderr)
        print(f"   Arguments: {json.dumps(tool_call.args, indent=4)}", file=sys.stderr)

        while True:
            print(
                "\nApprove this tool call? [Y]es [N]o [A]lways [O]nce: ",
                end="",
                flush=True,
                file=sys.stderr,
            )
            try:
                response = input().strip().lower()
                if response in ("y", "yes"):
                    return "allow"
                if response in ("n", "no"):
                    return "deny"
                if response in ("a", "always"):
                    return "always"
                if response in ("o", "once"):
                    return "once"
                print("Invalid response. Please enter Y, N, A, or O.", file=sys.stderr)
            except (KeyboardInterrupt, EOFError):
                print("\nOperation cancelled.", file=sys.stderr)
                return "deny"

    def approve_tool(self, tool_call: ToolCall) -> tuple[bool, bool]:
        """Approve or deny a tool call.

        Returns:
            tuple of (is_allowed, continue_session)
        """
        tool_name = tool_call.name

        # Check if tool has a one-time session allowance
        if tool_name in self.session_allowed:
            self.session_allowed.remove(tool_name)
            return True, True

        # Check if tool is pre-approved
        if self.is_allowed(tool_name):
            return True, True

        # Prompt user for decision
        decision = self.prompt_approval(tool_call)

        if decision == "allow":
            return True, True
        if decision == "always":
            self.always_allowed.add(tool_name)
            return True, True
        if decision == "once":
            self.session_allowed.add(tool_name)
            return True, True

        # decision == "deny"
        return False, False


async def run_prompt_with_tools(
    prompt: str,
    model: str,
    system_prompt: str | None,
    api_key: str | None,
    provider: str | None,
    base_url: str | None,
    tools: list[str] | None,
    tool_approval: str,
    tool_allowlist: list[str] | None,
) -> str:
    """Run a prompt with tool support and interactive approval."""
    from artifice.agent import Agent, AnyLLMProvider
    from artifice.agent.tools.base import execute_tool_call

    provider_instance = AnyLLMProvider(
        model=model,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
    )

    # Initialize tool approver
    approver = ToolApprover(tool_approval, tool_allowlist)

    # Create agent with tools
    agent = Agent(provider=provider_instance, system_prompt=system_prompt, tools=tools)
    final_text = ""

    def on_chunk(chunk: str) -> None:
        nonlocal final_text
        print(chunk, end="", flush=True)
        final_text += chunk

    # Initial prompt
    response = await agent.send(prompt, on_chunk=on_chunk)

    # Handle tool calls in a loop
    while response.tool_calls:
        print(
            f"\n🔧 Processing {len(response.tool_calls)} tool call(s)...",
            file=sys.stderr,
        )

        for tool_call in response.tool_calls:
            # Check approval
            is_allowed, continue_session = approver.approve_tool(tool_call)

            if not continue_session:
                print("\n❌ Operation cancelled by user.", file=sys.stderr)
                return final_text

            if is_allowed:
                print(f"\n✅ Executing tool: {tool_call.name}", file=sys.stderr)

                # Execute the tool
                try:
                    result = await execute_tool_call(tool_call)
                    if result is None:
                        result = f"Tool {tool_call.name} not executed (no executor)"

                    # Add tool result to conversation
                    agent.add_tool_result(tool_call.id, result)
                    logger.debug("Tool %s executed successfully", tool_call.name)
                except Exception:
                    logger.error(
                        "Error executing tool %s", tool_call.name, exc_info=True
                    )
                    error = f"Error executing tool {tool_call.name}"
                    agent.add_tool_result(tool_call.id, error)
            else:
                # Denied tool
                logger.debug("Tool %s denied by user", tool_call.name)
                agent.add_tool_result(
                    tool_call.id, f"Tool call {tool_call.name} was denied by user"
                )

        # Get next response with tool results
        print("\n💭 Continuing conversation...", file=sys.stderr)
        response = await agent.send("", on_chunk=on_chunk)

    return final_text


def main() -> None:
    """Main entry point for the art command."""
    parser = argparse.ArgumentParser(
        prog="art",
        description="Simple LLM prompt tool with tool support. Reads from stdin or argument, outputs to stdout.",
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
        "--get-current-agent",
        action="store_true",
        help="Print the current agent name and exit",
    )
    parser.add_argument(
        "--print-completion",
        choices=["bash", "zsh", "fish"],
        help="Print shell completion script",
    )
    parser.add_argument(
        "--tools",
        default=None,
        help="Enable tools (provide comma-separated patterns, e.g., 'read,write', or '*')",
    )
    parser.add_argument(
        "--tool-approval",
        choices=["ask", "auto", "deny"],
        default=None,
        help="Tool approval mode: ask (interactive), auto (allow all), or deny (disable all)",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install default configuration to ~/.artifice/",
    )
    args = parser.parse_args()

    if args.install:
        install_config()
        sys.exit(0)

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
        prompts = list_prompts()
        if prompts:
            for name in prompts:
                print(name)
        sys.exit(0)

    if args.get_current_agent:
        agent_name = args.agent or config.agent
        if not agent_name:
            print("Error: No agent configured", file=sys.stderr)
            sys.exit(1)
        print(agent_name)
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
            prompt_result = load_prompt(args.prompt_name)
            if not prompt_result:
                print(
                    f"Error: Unknown prompt '{args.prompt_name}'",
                    file=sys.stderr,
                )
                sys.exit(1)
            _, system_prompt = prompt_result
        else:
            system_prompt = agent_def.get("system_prompt", config.system_prompt)

    provider = agent_def.get("provider")
    if provider and provider.lower() == "simulated":
        print("Error: Simulated agents not supported in CLI mode", file=sys.stderr)
        sys.exit(1)

    base_url = agent_def.get("base_url")

    # Parse tools configuration
    tools = None
    if args.tools:
        tools = [pattern.strip() for pattern in args.tools.split(",")]
    elif config.tools:
        tools = config.tools

    tool_approval = args.tool_approval or config.tool_approval or "ask"
    tool_allowlist = config.tool_allowlist

    # If no tools enabled, use simple mode
    if not tools:
        try:
            response = asyncio.run(
                run_prompt_simple(
                    prompt, model, system_prompt, api_key, provider, base_url
                )
            )
            if response and not response.endswith("\n"):
                print()
        except KeyboardInterrupt:
            sys.exit(130)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Use tool-enabled mode
        try:
            response = asyncio.run(
                run_prompt_with_tools(
                    prompt,
                    model,
                    system_prompt,
                    api_key,
                    provider,
                    base_url,
                    tools,
                    tool_approval,
                    tool_allowlist,
                )
            )
            if response and not response.endswith("\n"):
                print()
        except KeyboardInterrupt:
            sys.exit(130)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


async def run_prompt_simple(
    prompt: str,
    model: str,
    system_prompt: str | None,
    api_key: str | None,
    provider: str | None,
    base_url: str | None,
) -> str:
    """Run a simple prompt without tool support."""
    from artifice.agent import Agent, AnyLLMProvider

    provider_instance = AnyLLMProvider(
        model=model,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
    )
    agent = Agent(provider=provider_instance, system_prompt=system_prompt, tools=None)

    def on_chunk(chunk: str) -> None:
        print(chunk, end="", flush=True)

    response = await agent.send(prompt, on_chunk=on_chunk)
    return response.text


if __name__ == "__main__":
    main()
