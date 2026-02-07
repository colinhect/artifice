"""Main Artifice terminal widget."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widget import Widget

from .execution import ExecutionResult, CodeExecutor, ShellExecutor
from .history import History
from .terminal_input import TerminalInput
from .terminal_output import TerminalOutput, AgentInputBlock, AgentOutputBlock, CodeInputBlock, CodeOutputBlock

if TYPE_CHECKING:
    from .app import ArtificeApp

class ArtificeTerminal(Widget):
    """Primary widget for interacting with Artifice."""

    DEFAULT_CSS = """
    ArtificeTerminal {
        height: 100%;
        width: 100%;
    }

    ArtificeTerminal Vertical {
        height: 100%;
    }

    ArtificeTerminal TerminalOutput {
        height: 1fr;
    }

    ArtificeTerminal TerminalInput {
        dock: bottom;
    }

    ArtificeTerminal .highlighted {
        background: $surface-lighten-2;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "clear", "Clear Output", show=True),
        Binding("ctrl+o", "toggle_mode_markdown", "Toggle Markdown Output", show=True),
    ]

    def __init__(
        self,
        app: ArtificeApp,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        history_file: str | Path | None = None,
        max_history_size: int = 1000,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._executor = CodeExecutor()
        self._shell_executor = ShellExecutor()

        # Create history manager
        self._history = History(history_file=history_file, max_history_size=max_history_size)

        # Per-mode markdown rendering settings
        self._python_markdown_enabled = False  # Default: no markdown for Python output
        self._agent_markdown_enabled = True    # Default: markdown for agent responses
        self._shell_markdown_enabled = False   # Default: no markdown for shell output

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
            "You are a minimal AI assistant in an interactive Python coding environment with shell access. "
            "Your primary goal is to help the user write and execute Python code or shell commands to accomplish what the user asks for. "
            "Provide the shortest possible code, do not overprovide examples unless asked to. "
            "Focus on action, not explanation:\n\n"
            "- Write the code or command that solves the user's problem\n"
            "- Use the request_execute_python tool to run Python code\n"
            "- Use the request_execute_shell tool to run shell commands\n"
            "- Provide a brief explanation of the code or shell commands you request\n"
            "- Keep responses concise and code-focused\n"
            "- If code produces an error, explain what is wrong and how to fix it, fix it and try again\n\n"
            "Remember: Code/command execution, not explanation, is your primary mode of operation."
        )
        
        def on_agent_connect(agent_name):
            app.notify(f"Connected to {agent_name}")

        # Create agent with tool support
        self._agent = None
        if app.agent_type.lower() == "claude":
            from .agent import ClaudeAgent
            self._agent = ClaudeAgent(
                tools=[python_tool, shell_tool],
                tool_handler=self._handle_tool_call,
                system_prompt=system_prompt,
                on_connect=on_agent_connect,
            )
        elif app.agent_type.lower() == "simulated":
            from artifice.agent.simulated import SimulatedAgent
            self._agent = SimulatedAgent(
                response_delay=0.01,
                tool_handler=self._handle_tool_call,
                on_connect=on_agent_connect,
             )

            # Configure scenarios with pattern matching
            self._agent.configure_scenarios([
                {
                    'pattern': r'hello|hi|hey',
                    'response': 'Hello! I\'m a **simulated** agent. How can I help you today?'
                },
                {
                    'pattern': r'calculate|math|sum|add',
                    'response': 'I can help with that calculation!',
                    'tools': [
                        {
                            'name': 'request_execute_python',
                            'input': {'code': 'result = 10 + 5\nprint(f"The result is: {result}")'}
                        }
                    ]
                },
                {
                    'pattern': r'goodbye|bye|exit',
                    'response': 'Goodbye! Thanks for chatting with me.'
                },
            ])

            self._agent.set_default_response("I'm not sure how to respond to that. Try asking about math or saying hello!")
        elif app.agent_type:
            raise Exception(f"Unsupported agent {app.agent_type}")
        self._agent_requested_execution: bool = False

        self.output = TerminalOutput(id="output")
        self.input = TerminalInput(history=self._history, id="input")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield self.output
            yield self.input

    async def on_terminal_input_submitted(self, event: TerminalInput.Submitted) -> None:
        """Handle code submission from input."""
        code = event.code

        # Clear input
        self.input.clear()

        if event.is_agent_prompt:
            await self._handle_agent_prompt(code)
        elif event.is_shell_command:
            result = await self._handle_shell_execution(code)

            if self._agent_requested_execution:
                agent_output_block = AgentOutputBlock()
                self.output.append_block(agent_output_block)

                prompt = "I executed the shell command that you requested:\n\n```\n" + code + "```\n\nOutput:\n```\n" + result.output + result.error + "\n```\n"
                response = await self._agent.send_prompt(
                    prompt,
                    on_chunk=lambda text: agent_output_block.append(text),
                )

                if response.error:
                    agent_output_block.mark_failed()
                else:
                    agent_output_block.mark_success()

                self._agent_requested_execution = False
        else:
            result = await self._handle_python_execution(code)

            if self._agent_requested_execution:
                agent_output_block = AgentOutputBlock()
                self.output.append_block(agent_output_block)

                prompt = "I executed code that you requested:\n\n```\n" + code + "```\n\nOutput:\n```\n" + result.output + result.error + "\n```\n"

                # Send prompt to agent with streaming into the NEW block
                response = await self._agent.send_prompt(
                    prompt,
                    on_chunk=lambda text: agent_output_block.append(text),
                )

                if response.error:
                    agent_output_block.mark_failed()
                else:
                    agent_output_block.mark_success()

                self._agent_requested_execution = False
    
    async def on_terminal_input_decline_requested(self, event: TerminalInput.DeclineRequested) -> None:
        """Handle decline request from input (escape key)."""
        # If no pending execution, just ignore the escape key
        pass

    async def _handle_python_execution(self, code: str) -> ExecutionResult:
        """Execute Python code."""
        code_input_block = CodeInputBlock(code, language="python")
        self.output.append_block(code_input_block)

        code_output_block = CodeOutputBlock(render_markdown=self._python_markdown_enabled)
        self.output.append_block(code_output_block)

        result = await self._executor.execute(
            code,
            on_output=lambda text: code_output_block.append_output(text),
            on_error=lambda text: code_output_block.append_error(text),
        )

        code_input_block.update_status(result)
        return result

    async def _handle_shell_execution(self, command: str) -> ExecutionResult:
        """Execute shell command."""
        command_input_block = CodeInputBlock(command, language="bash")
        self.output.append_block(command_input_block)

        code_output_block = CodeOutputBlock(render_markdown=self._shell_markdown_enabled)
        self.output.append_block(code_output_block)

        # Execute asynchronously with streaming callbacks
        result = await self._shell_executor.execute(
            command,
            on_output=lambda text: code_output_block.append_output(text),
            on_error=lambda text: code_output_block.append_error(text),
        )

        command_input_block.update_status(result)
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
            code = code.strip()

            self._agent_requested_execution = True

            # Populate the input field with the code for user review
            self.input.code = code
            # Switch to Python mode
            self.input.mode = "python"
            self.input._update_prompt()

            return "I will respond after requested code has been executed."

        elif tool_name == "request_execute_shell":
            command = tool_input.get("command", "")
            if not command:
                return "Error: No command provided"
            command = command.strip()

            self._agent_requested_execution = True

            # Populate the input field with the command for user review
            self.input.code = command
            # Switch to Shell mode
            self.input.mode = "shell"
            self.input._update_prompt()

            return "I will respond after requested command has been executed."

        return f"Error: Unknown tool '{tool_name}'"

    async def _handle_agent_prompt(self, prompt: str) -> None:
        """Handle AI agent prompt with tool support."""
        # Create a block showing the prompt
        agent_input_block = AgentInputBlock(prompt)
        self.output.append_block(agent_input_block)

        if self._agent is None:
            # No agent configured, show error
            agent_output_block = AgentOutputBlock("No AI agent configured.")
            self.output.append_block(agent_output_block)
            agent_output_block.mark_failed()
            return

        # Create a separate block for the agent's response
        agent_output_block = AgentOutputBlock()
        self.output.append_block(agent_output_block)

        # Send prompt to agent with streaming
        response = await self._agent.send_prompt(
            prompt,
            on_chunk=lambda text: agent_output_block.append(text),
        )

        if response.error:
            agent_output_block.mark_failed()
        else:
            agent_output_block.mark_success()

    def action_clear(self) -> None:
        """Clear the output."""
        self.output.clear()

    async def action_toggle_mode_markdown(self) -> None:
        """Toggle markdown rendering for the current input mode (affects future blocks only)."""
        # Determine current mode and toggle its setting
        if self.input.mode == "ai":
            self._agent_markdown_enabled = not self._agent_markdown_enabled
            enabled_str = "enabled" if self._agent_markdown_enabled else "disabled"
            self.app.notify(f"Markdown {enabled_str} for AI agent output")
        elif self.input.mode == "shell":
            self._shell_markdown_enabled = not self._shell_markdown_enabled
            enabled_str = "enabled" if self._shell_markdown_enabled else "disabled"
            self.app.notify(f"Markdown {enabled_str} for shell command output")
        else:
            self._python_markdown_enabled = not self._python_markdown_enabled
            enabled_str = "enabled" if self._python_markdown_enabled else "disabled"
            self.app.notify(f"Markdown {enabled_str} for Python code output")

    def reset(self) -> None:
        """Reset the REPL state."""
        self._executor.reset()
        self.output.clear()
        self._history.clear()
    
