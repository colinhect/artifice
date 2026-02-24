"""Simple command-line interface for artifice."""

from __future__ import annotations

import argparse
import asyncio
import datetime
import importlib.resources
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artifice.agent.client import Agent
    from artifice.agent.tools.base import ToolCall

logger = logging.getLogger(__name__)


def save_session(
    prompt: str,
    system_prompt: str | None,
    model: str,
    provider: str | None,
    response: str,
) -> Path | None:
    """Save prompt and response to a session markdown file.

    Returns the path to the saved file, or None if saving was disabled.
    """
    sessions_dir = Path.home() / ".artifice" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    session_file = sessions_dir / f"{timestamp}.md"

    content = f"""# Session: {timestamp}

## Model
- **Provider**: {provider or "default"}
- **Model**: {model}

## System Prompt
{system_prompt or "(none)"}

## User Prompt
{prompt}

## Response
{response}
"""

    session_file.write_text(content, encoding="utf-8")
    return session_file


def install_config() -> None:
    """Install default configuration to ~/.artifice/."""
    from artifice.core.config import get_config_path, get_config_file_path

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

        from fnmatch import fnmatch

        for pattern in self.allowlist:
            if fnmatch(tool_name, pattern):
                return True

        if tool_name in self.always_allowed:
            return True

        return False

    def prompt_approval(self, tool_call: ToolCall) -> str:
        """Prompt user for tool call approval.

        Returns one of: "allow", "deny", "always", "once"
        """
        print(f"\nTool Call: {tool_call.name}", file=sys.stderr)
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

        if tool_name in self.session_allowed:
            self.session_allowed.remove(tool_name)
            return True, True

        if self.is_allowed(tool_name):
            return True, True

        decision = self.prompt_approval(tool_call)

        if decision == "allow":
            return True, True
        if decision == "always":
            self.always_allowed.add(tool_name)
            return True, True
        if decision == "once":
            self.session_allowed.add(tool_name)
            return True, True

        return False, False


def format_tool_args(tool_call: ToolCall) -> str:
    """Format tool arguments for display on one line."""
    if not tool_call.args:
        return ""
    parts = []
    for key, value in tool_call.args.items():
        if isinstance(value, str):
            if len(value) > 40:
                value = value[:37] + "..."
            value = f'"{value}"'
        elif isinstance(value, dict):
            value = "{...}"
        elif isinstance(value, list):
            value = f"[{len(value)} items]"
        parts.append(f"{key}={value}")
    return " ".join(parts)


def format_token_usage(
    input_tokens: int, output_tokens: int, context_window: int | None = None
) -> str:
    """Format token usage for display."""
    parts = [f"in:{input_tokens}", f"out:{output_tokens}"]
    if context_window:
        used_pct = (input_tokens + output_tokens) / context_window * 100
        parts.append(f"{used_pct:.0f}%")
    return " ".join(parts)


def get_context_length(messages: list[dict]) -> int:
    """Calculate total character length of message content."""
    total = 0
    for msg in messages:
        if isinstance(msg.get("content"), str):
            total += len(msg["content"])
        elif isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part.get("text"), str):
                    total += len(part["text"])
    return total


async def execute_tool(
    tool_call: ToolCall,
    agent: "Agent",
    tool_output: bool = False,
) -> tuple[bool, str]:
    """Execute a single tool call and add result to agent.

    Returns:
        tuple of (success, result_message)
    """
    from artifice.agent.tools.base import execute_tool_call

    try:
        before_len = get_context_length(agent.messages)
        result = await execute_tool_call(tool_call)
        if result is None:
            result = f"Tool {tool_call.name} not executed (no executor)"

        agent.add_tool_result(tool_call.id, result)
        after_len = get_context_length(agent.messages)
        added = after_len - before_len

        if tool_output:
            print(result, file=sys.stderr)

        logger.debug("Tool %s executed successfully", tool_call.name)
        return True, f"+{added} chars"
    except Exception:
        logger.error("Error executing tool %s", tool_call.name, exc_info=True)
        error = f"Error executing tool {tool_call.name}"
        agent.add_tool_result(tool_call.id, error)
        return False, "error"


async def process_tool_calls(
    tool_calls: list["ToolCall"],
    agent: "Agent",
    approver: ToolApprover,
    tool_output: bool = False,
) -> bool:
    """Process a list of tool calls with approval.

    Returns:
        True if processing should continue, False if cancelled.
    """
    if tool_calls:
        print("", file=sys.stderr)
    for tool_call in tool_calls:
        is_allowed, continue_session = approver.approve_tool(tool_call)

        if not continue_session:
            print("\nOperation cancelled by user.", file=sys.stderr)
            return False

        args_str = format_tool_args(tool_call)
        print(f"{tool_call.name}({args_str})", end="", flush=True, file=sys.stderr)

        if is_allowed:
            success, msg = await execute_tool(tool_call, agent, tool_output)
            print(f" → {msg}", file=sys.stderr)
        else:
            agent.add_tool_result(
                tool_call.id, f"Tool call {tool_call.name} was denied by user"
            )
            print(" → denied", file=sys.stderr)
            logger.debug("Tool %s denied by user", tool_call.name)

    return True


async def run_prompt(
    prompt: str,
    model: str,
    system_prompt: str | None,
    api_key: str | None,
    provider: str | None,
    base_url: str | None,
    tools: list[str] | None = None,
    tool_approval: str | None = None,
    tool_allowlist: list[str] | None = None,
    tool_output: bool = False,
) -> str:
    """Run a prompt with optional tool support and interactive approval."""
    from artifice.agent import Agent, AnyLLMProvider
    from artifice.agent.providers.base import TokenUsage

    provider_instance = AnyLLMProvider(
        model=model,
        api_key=api_key,
        provider=provider,
        base_url=base_url,
    )

    agent = Agent(provider=provider_instance, system_prompt=system_prompt, tools=tools)
    final_text = ""
    total_usage = TokenUsage()

    def on_chunk(chunk: str) -> None:
        nonlocal final_text
        print(chunk, end="", flush=True)
        final_text += chunk

    response = await agent.send(prompt, on_chunk=on_chunk)

    if response.usage:
        total_usage.input_tokens += response.usage.input_tokens
        total_usage.output_tokens += response.usage.output_tokens
        total_usage.total_tokens += response.usage.total_tokens

    if not tools:
        if total_usage.total_tokens > 0:
            usage_str = format_token_usage(
                total_usage.input_tokens, total_usage.output_tokens
            )
            print(f"\n[{usage_str}]", file=sys.stderr)
        return final_text

    approver = ToolApprover(tool_approval or "ask", tool_allowlist)

    while response.tool_calls:
        should_continue = await process_tool_calls(
            response.tool_calls, agent, approver, tool_output
        )
        if not should_continue:
            return final_text

        response = await agent.send("", on_chunk=on_chunk)

        if response.usage:
            total_usage.input_tokens += response.usage.input_tokens
            total_usage.output_tokens += response.usage.output_tokens
            total_usage.total_tokens += response.usage.total_tokens

    if total_usage.total_tokens > 0:
        usage_str = format_token_usage(
            total_usage.input_tokens, total_usage.output_tokens
        )
        print(f"\n[{usage_str}]", file=sys.stderr)

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
        help="List available agent names",
    )
    parser.add_argument(
        "--list-prompts",
        action="store_true",
        help="List available prompt names",
    )
    parser.add_argument(
        "--get-current-agent",
        action="store_true",
        help="Print the current agent name and exit",
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
    parser.add_argument(
        "--add-prompt",
        metavar="FILE",
        help="Add a prompt from FILE to ~/.artifice/prompts/",
    )
    parser.add_argument(
        "--new-prompt",
        metavar="NAME",
        help="Create a new prompt with NAME in ~/.artifice/prompts/ (reads from stdin)",
    )
    parser.add_argument(
        "--no-session",
        action="store_true",
        help="Disable saving session to ~/.artifice/sessions/",
    )
    parser.add_argument(
        "--tool-output",
        action="store_true",
        help="Show tool call output (hidden by default)",
    )
    parser.add_argument(
        "-f",
        "--file",
        action="append",
        dest="files",
        metavar="FILE",
        help="Attach file(s) as context (can be specified multiple times)",
    )
    args = parser.parse_args()

    if args.install:
        install_config()
        sys.exit(0)

    if args.add_prompt:
        from artifice.core.config import get_config_path

        prompts_dir = get_config_path() / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        source = Path(args.add_prompt)
        if not source.is_file():
            print(f"Error: File not found: {args.add_prompt}", file=sys.stderr)
            sys.exit(1)
        dest = prompts_dir / source.name
        if dest.exists():
            print(f"Error: Prompt already exists: {dest}", file=sys.stderr)
            sys.exit(1)
        shutil.copy(source, dest)
        print(f"Added prompt: {dest}")
        sys.exit(0)

    if args.new_prompt:
        from artifice.core.config import get_config_path

        prompts_dir = get_config_path() / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        name = args.new_prompt
        if not name.endswith(".md"):
            name += ".md"
        dest = prompts_dir / name
        if dest.exists():
            print(f"Error: Prompt already exists: {dest}", file=sys.stderr)
            sys.exit(1)
        if sys.stdin.isatty():
            print(
                f"Enter prompt content for '{args.new_prompt}'. "
                "Press Ctrl-D (or Ctrl-Z on Windows) to save.",
                file=sys.stderr,
            )
        content = sys.stdin.read()
        dest.write_text(content)
        print(f"Created prompt: {dest}")
        sys.exit(0)

    if args.logging:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stderr,
        )

    from artifice.core.config import load_config

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
        from artifice.core.prompts import list_prompts

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

    prompt = args.prompt or ""

    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read()
        if args.prompt and stdin_content.strip():
            prompt = f"{args.prompt}\n\n{stdin_content}"
        elif stdin_content.strip():
            prompt = stdin_content

    if not prompt.strip():
        sys.exit(0)

    if args.files:
        file_contents: list[str] = []
        for file_path in args.files:
            path = Path(file_path)
            if not path.is_file():
                print(f"Error: File not found: {file_path}", file=sys.stderr)
                sys.exit(1)
            try:
                content = path.read_text(encoding="utf-8")
                file_contents.append(f"--- {file_path} ---\n{content}")
            except Exception as e:
                print(f"Error reading {file_path}: {e}", file=sys.stderr)
                sys.exit(1)
        if file_contents:
            context = "\n\n".join(file_contents)
            prompt = f"{context}\n\n---\n\n{prompt}"

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
            from artifice.core.prompts import load_prompt

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

    tools = None
    if args.tools:
        tools = [pattern.strip() for pattern in args.tools.split(",")]
    elif config.tools:
        tools = config.tools

    tool_approval = args.tool_approval or config.tool_approval
    tool_allowlist = config.tool_allowlist

    try:
        response = asyncio.run(
            run_prompt(
                prompt,
                model,
                system_prompt,
                api_key,
                provider,
                base_url,
                tools,
                tool_approval,
                tool_allowlist,
                tool_output=args.tool_output,
            )
        )
        if response and not response.endswith("\n"):
            print()

        if config.save_session and not args.no_session:
            save_session(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                provider=provider,
                response=response,
            )
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
