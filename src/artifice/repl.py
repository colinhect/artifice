"""Main Interactive Python REPL widget."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widget import Widget

from .executor import CodeExecutor, ShellExecutor, ExecutionResult
from .repl_input import ReplInput
from .repl_output import ReplOutput
from .agent import AgentBase, create_agent


class InteractivePython(Widget):
    """An interactive Python REPL widget for Textual applications.

    This widget provides a full-featured Python REPL that can be embedded
    in any Textual application. It supports:
    - Async code execution with activity indicators
    - Success/failure icons for completed commands
    - Multiline input
    - Command history navigation
    - Highlighted block navigation with Ctrl+Arrow keys
    """

    DEFAULT_CSS = """
    InteractivePython {
        height: 100%;
        width: 100%;
    }

    InteractivePython Vertical {
        height: 100%;
    }

    InteractivePython ReplOutput {
        height: 1fr;
    }

    InteractivePython ReplInput {
        dock: bottom;
    }

    InteractivePython .highlighted {
        background: $surface-lighten-2;
    }
    """

    BINDINGS = [
        Binding("alt+up", "history_back", "History Back", show=True),
        Binding("alt+down", "history_forward", "History Forward", show=True),
        Binding("ctrl+up", "highlight_previous", "Previous Block", show=True),
        Binding("ctrl+down", "highlight_next", "Next Block", show=True),
        Binding("ctrl+l", "clear", "Clear Output", show=True),
        Binding("ctrl+o", "toggle_markdown", "Toggle Markdown", show=True),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        history_file: str | Path | None = None,
        max_history_size: int = 1000,
        agent: AgentBase | None = None,
        agent_type: str = "claude",
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._executor = CodeExecutor()
        self._shell_executor = ShellExecutor()

        # Separate histories for Python, AI, and Shell modes
        self._python_history: list[str] = []
        self._ai_history: list[str] = []
        self._shell_history: list[str] = []
        self._python_history_index: int = -1  # -1 means not browsing history
        self._ai_history_index: int = -1
        self._shell_history_index: int = -1
        self._current_input: str = ""  # Store current input when browsing history
        
        # History persistence configuration
        if history_file is None:
            # Default to ~/.artifice_history.json
            self._history_file = Path.home() / ".artifice_history.json"
        else:
            self._history_file = Path(history_file)
        
        self._max_history_size = max_history_size
        self._load_history()
        
        # AI Agent configuration
        if agent is not None:
            self._agent = agent
        elif agent_type:
            try:
                # Create agent with Python execution tool
                from .agent import ClaudeAgent
                
                # Define Python execution request tool (user confirmation required)
                python_tool = {
                    "name": "request_execute_python",
                    "description": (
                        "Request execution of Python code in the REPL environment. "
                        "The code will be presented to the user in the input prompt where they will choose to:\n"
                        "- Execute the code as-is\n"
                        "- Edit the code and execute the modified version\n"
                        "- Decline execution\n\n"
                        "After the user's action, you will receive either:\n"
                        "- The executed code (possibly modified) and its output/result\n"
                        "- A message that the user declined to execute the code\n\n"
                        "Use this to run Python commands, perform calculations, test code snippets, "
                        "or explore Python functionality. The code runs in a persistent Python session, "
                        "so variables and imports persist across executions."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "The Python code to request execution for",
                            }
                        },
                        "required": ["code"],
                    },
                }

                # Define Shell execution request tool (user confirmation required)
                shell_tool = {
                    "name": "request_execute_shell",
                    "description": (
                        "Request execution of a shell command. "
                        "The command will be presented to the user in the input prompt where they will choose to:\n"
                        "- Execute the command as-is\n"
                        "- Edit the command and execute the modified version\n"
                        "- Decline execution\n\n"
                        "After the user's action, you will receive either:\n"
                        "- The executed command (possibly modified) and its output\n"
                        "- A message that the user declined to execute the command\n\n"
                        "Use this to run shell commands, check system state, run scripts, "
                        "or perform file system operations."
                    ),
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to request execution for",
                            }
                        },
                        "required": ["command"],
                    },
                }
                
                # System prompt to guide the agent's behavior
                system_prompt = (
                    "You are an AI assistant in an interactive Python REPL environment with shell access. "
                    "Your primary goal is to write and execute Python code or shell commands to accomplish what the user asks for. "
                    "Provide the shortest possible code, do not overprovide examples unless asked to. "
                    "Focus on action, not explanation:\n\n"
                    "- Write the code or command that solves the user's problem\n"
                    "- Use the request_execute_python tool to run Python code\n"
                    "- Use the request_execute_shell tool to run shell commands\n"
                    "- Only provide explanations if the user explicitly asks for them\n"
                    "- Keep responses concise and code-focused\n"
                    "- If code produces an error, explain what is wrong and how to fix it, fix it and try again\n\n"
                    "Remember: Code/command execution, not explanation, is your primary mode of operation."
                )
                
                # Create agent with tool support
                if agent_type.lower() == "claude":
                    self._agent = ClaudeAgent(
                        tools=[python_tool, shell_tool],
                        tool_handler=self._handle_tool_call,
                        on_tool_call=None,
                        system_prompt=system_prompt,
                    )
                else:
                    self._agent = create_agent(agent_type)
            except Exception:
                # Agent creation failed (e.g., missing API key), but that's okay
                # We'll show an error when the user tries to use it
                self._agent = create_agent(agent_type)
        else:
            self._agent = None
        
        # Track pending code execution requests from agent
        self._pending_code_execution: dict[str, Any] = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield ReplOutput(id="output")
            yield ReplInput(id="input")

    @property
    def output(self) -> ReplOutput:
        """Get the output component."""
        return self.query_one("#output", ReplOutput)

    @property
    def input(self) -> ReplInput:
        """Get the input component."""
        return self.query_one("#input", ReplInput)

    async def on_repl_input_submitted(self, event: ReplInput.Submitted) -> None:
        """Handle code submission from input."""
        code = event.code

        # Add to appropriate history
        if event.is_agent_prompt:
            self._ai_history.append(code)
            self._ai_history_index = -1  # Reset history navigation
        elif event.is_shell_command:
            self._shell_history.append(code)
            self._shell_history_index = -1  # Reset history navigation
        else:
            self._python_history.append(code)
            self._python_history_index = -1  # Reset history navigation

        self._current_input = ""

        # Save history to disk
        self._save_history()

        # Clear input
        self.input.clear()

        if event.is_agent_prompt:
            # Route to AI agent
            await self._handle_agent_prompt(code)
        elif event.is_shell_command:
            # Execute as shell command
            result = await self._handle_shell_execution(code)

            if self._pending_code_execution is not None:
                # The user executed a shell command requested by the agent
                from .executor import ExecutionStatus
                agent_response_result = ExecutionResult(code="")
                agent_response_result.status = ExecutionStatus.RUNNING
                agent_response_block = self.output.add_result(agent_response_result, is_agent=True, show_code=False, block_type="agent_response")

                # Send prompt to agent with streaming into the NEW block
                response = await self._agent.send_prompt(
                    "The user executed shell command that you requested:\n\n```\n" + code + "```\n\nOutput:\n```\n" + result.output + result.error + "\n```\n",
                    on_chunk=lambda text: agent_response_block.append_output(text),
                )

                # Finalize the agent response block
                if response.error:
                    agent_response_result.status = ExecutionStatus.ERROR
                    agent_response_result.error = response.error
                else:
                    agent_response_result.status = ExecutionStatus.SUCCESS

                agent_response_block.update_status(agent_response_result)

                self._pending_code_execution = None
        else:
            # Execute as Python code
            result = await self._handle_python_execution(code)

            if self._pending_code_execution is not None:
                # The user executed code requested by the agent
                from .executor import ExecutionStatus
                agent_response_result = ExecutionResult(code="")
                agent_response_result.status = ExecutionStatus.RUNNING
                agent_response_block = self.output.add_result(agent_response_result, is_agent=True, show_code=False, block_type="agent_response")

                # Send prompt to agent with streaming into the NEW block
                response = await self._agent.send_prompt(
                    "The user executed code that you requested:\n\n```\n" + code + "```\n\nOutput:\n```\n" + result.output + result.error + "\n```\n",
                    on_chunk=lambda text: agent_response_block.append_output(text),
                )

                # Finalize the agent response block
                if response.error:
                    agent_response_result.status = ExecutionStatus.ERROR
                    agent_response_result.error = response.error
                else:
                    agent_response_result.status = ExecutionStatus.SUCCESS

                agent_response_block.update_status(agent_response_result)

                self._pending_code_execution = None

    
    async def on_repl_input_decline_requested(self, event: ReplInput.DeclineRequested) -> None:
        """Handle decline request from input (escape key)."""
        # If no pending execution, just ignore the escape key

    async def _handle_python_execution(self, code: str) -> ExecutionResult:
        """Execute Python code."""
        # Create a block showing the code input
        from .executor import ExecutionStatus
        code_result = ExecutionResult(code=code)
        code_result.status = ExecutionStatus.SUCCESS
        self.output.add_result(code_result, show_output=False, block_type="code_input")

        # Create a separate block for the execution output
        output_result = ExecutionResult(code="")
        output_result.status = ExecutionStatus.RUNNING
        output_block = self.output.add_result(output_result, show_code=False, block_type="code_output")

        # Execute asynchronously with streaming callbacks
        result = await self._executor.execute(
            code,
            on_output=lambda text: output_block.append_output(text),
            on_error=lambda text: output_block.append_error(text),
        )

        # Update the output block status
        output_block.update_status(result)
        return result

    async def _handle_shell_execution(self, command: str) -> ExecutionResult:
        """Execute shell command."""
        # Create a block showing the command input
        from .executor import ExecutionStatus
        command_result = ExecutionResult(code=command)
        command_result.status = ExecutionStatus.SUCCESS
        self.output.add_result(command_result, show_output=False, block_type="shell_input")

        # Create a separate block for the execution output
        output_result = ExecutionResult(code="")
        output_result.status = ExecutionStatus.RUNNING
        output_block = self.output.add_result(output_result, show_code=False, block_type="shell_output")

        # Execute asynchronously with streaming callbacks
        result = await self._shell_executor.execute(
            command,
            on_output=lambda text: output_block.append_output(text),
            on_error=lambda text: output_block.append_error(text),
        )

        # Update the output block status
        output_block.update_status(result)
        return result
    
    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """Handle tool calls from the agent.

        Args:
            tool_name: Name of the tool to execute.
            tool_input: Input parameters for the tool.

        Returns:
            String result from the tool execution.
        """
        if tool_name == "request_execute_python":
            code = tool_input.get("code", "")
            if not code:
                return "Error: No code provided"

            # Store pending execution state
            self._pending_code_execution = {
                "code": code,
            }

            # Populate the input field with the code for user review
            self.input.code = code
            # Switch to Python mode
            self.input.mode = "python"
            self.input._update_prompt()

            return "The user will respond after requested code has been executed."

        elif tool_name == "request_execute_shell":
            command = tool_input.get("command", "")
            if not command:
                return "Error: No command provided"

            # Store pending execution state
            self._pending_code_execution = {
                "command": command,
            }

            # Populate the input field with the command for user review
            self.input.code = command
            # Switch to Shell mode
            self.input.mode = "shell"
            self.input._update_prompt()

            return "The user will respond after requested command has been executed."

        return f"Error: Unknown tool '{tool_name}'"

    async def _handle_agent_prompt(self, prompt: str) -> None:
        """Handle AI agent prompt with tool support."""
        if self._agent is None:
            # No agent configured, show error
            from .executor import ExecutionStatus
            error_result = ExecutionResult(
                code=f"{prompt}",
                status=ExecutionStatus.ERROR,
                error="No AI agent configured. Set ANTHROPIC_API_KEY environment variable or pass an agent to InteractivePython.",
            )
            self.output.add_result(error_result, is_agent=True)
            return

        # Create a block showing the prompt
        from .executor import ExecutionStatus
        prompt_result = ExecutionResult(code=f"{prompt}")
        prompt_result.status = ExecutionStatus.SUCCESS
        self.output.add_result(prompt_result, is_agent=True, show_output=False, block_type="agent_prompt")

        # Create a separate block for the agent's response
        response_result = ExecutionResult(code="")
        response_result.status = ExecutionStatus.RUNNING
        response_block = self.output.add_result(response_result, is_agent=True, show_code=False, block_type="agent_response")

        # Send prompt to agent with streaming
        response = await self._agent.send_prompt(
            prompt,
            on_chunk=lambda text: response_block.append_output(text),
        )

        # Finalize the response block
        if response.error:
            response_result.status = ExecutionStatus.ERROR
            response_result.error = response.error
        else:
            response_result.status = ExecutionStatus.SUCCESS

        response_block.update_status(response_result)


    def action_history_back(self) -> None:
        """Handle request for previous history item."""
        # Determine which history to use based on current mode
        if self.input.is_ai_mode:
            history = self._ai_history
            history_index = self._ai_history_index
        elif self.input.mode == "shell":
            history = self._shell_history
            history_index = self._shell_history_index
        else:
            history = self._python_history
            history_index = self._python_history_index

        if not history:
            return

        # First time navigating up, save current input
        if history_index == -1:
            self._current_input = self.input.code
            history_index = len(history)

        # Move back in history
        if history_index > 0:
            history_index -= 1
            self.input.code = history[history_index]

        # Update the appropriate history index
        if self.input.is_ai_mode:
            self._ai_history_index = history_index
        elif self.input.mode == "shell":
            self._shell_history_index = history_index
        else:
            self._python_history_index = history_index

    def action_history_forward(self) -> None:
        """Handle request for next history item."""
        # Determine which history to use based on current mode
        if self.input.is_ai_mode:
            history = self._ai_history
            history_index = self._ai_history_index
        elif self.input.mode == "shell":
            history = self._shell_history
            history_index = self._shell_history_index
        else:
            history = self._python_history
            history_index = self._python_history_index

        if history_index == -1:
            return  # Not browsing history

        # Move forward in history
        if history_index < len(history) - 1:
            history_index += 1
            self.input.code = history[history_index]
        else:
            # Reached the end, restore original input
            history_index = -1
            self.input.code = self._current_input
            self._current_input = ""

        # Update the appropriate history index
        if self.input.is_ai_mode:
            self._ai_history_index = history_index
        elif self.input.mode == "shell":
            self._shell_history_index = history_index
        else:
            self._python_history_index = history_index

    def action_highlight_previous(self) -> None:
        """Move highlight to previous output block."""
        self.output.highlight_previous()

    def action_highlight_next(self) -> None:
        """Move highlight to next output block."""
        self.output.highlight_next()

    def action_clear(self) -> None:
        """Clear the output."""
        self.output.clear()

    async def action_toggle_markdown(self) -> None:
        """Toggle markdown rendering for the currently highlighted block."""
        block = self.output.get_highlighted_block()
        if block:
            await block.toggle_markdown()

    def reset(self) -> None:
        """Reset the REPL state."""
        self._executor.reset()
        self.output.clear()
        self._python_history.clear()
        self._ai_history.clear()
        self._shell_history.clear()
        self._python_history_index = -1
        self._ai_history_index = -1
        self._shell_history_index = -1
        self._current_input = ""
    
    def _load_history(self) -> None:
        """Load command history from disk."""
        try:
            if self._history_file.exists():
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Support both old format (list) and new format (dict)
                    if isinstance(data, list):
                        # Old format: treat as Python history
                        self._python_history = data[-self._max_history_size:]
                        self._ai_history = []
                        self._shell_history = []
                    elif isinstance(data, dict):
                        # New format: separate Python, AI, and Shell histories
                        self._python_history = data.get("python", [])[-self._max_history_size:]
                        self._ai_history = data.get("ai", [])[-self._max_history_size:]
                        self._shell_history = data.get("shell", [])[-self._max_history_size:]
        except Exception:
            # If we can't load history, just start with empty lists
            self._python_history = []
            self._ai_history = []
            self._shell_history = []
    
    def _save_history(self) -> None:
        """Save command history to disk."""
        try:
            # Ensure parent directory exists
            self._history_file.parent.mkdir(parents=True, exist_ok=True)

            # Keep only the most recent entries
            history_to_save = {
                "python": self._python_history[-self._max_history_size:],
                "ai": self._ai_history[-self._max_history_size:],
                "shell": self._shell_history[-self._max_history_size:],
            }

            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(history_to_save, f, indent=2)
        except Exception:
            # Silently fail if we can't save history
            pass
