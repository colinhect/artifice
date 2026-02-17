import argparse

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Static

from artifice import ArtificeTerminal
from artifice.config import load_config, ArtificeConfig
from artifice.prompts import load_prompt
from artifice.theme import create_artifice_theme


class ArtificeHeader(Static):
    """Custom header with gradient fade effect."""

    def __init__(self, banner):
        super().__init__()
        self.banner = banner

    def compose(self) -> ComposeResult:
        gradient_chars = ["█", "█", "▓", "▓", "▒", "▒", "░", "░", "·", "·", " "]

        header_content = ""
        if self.banner:
            header_content = """┌─┐┬─┐┌┬┐┬┌─┐┬┌─┐┌─┐
├─┤├┬┘ │ │├┤ ││  ├┤
┴ ┴┴└─ ┴ ┴└  ┴└─┘└─┘\n"""

        header_content += "".join(gradient_chars)
        yield Static(header_content, classes="header-bar")


class ArtificeApp(App):
    TITLE = "Artifice Terminal"
    CSS_PATH = "styles.css"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f2", "toggle_footer", "Toggle Help"),
    ]

    def __init__(self, config: ArtificeConfig):
        self.config = config
        # Use config values, with command-line args taking precedence
        self.banner = config.banner
        self.footer_visible = False
        super().__init__()

    def compose(self) -> ComposeResult:
        yield ArtificeHeader(self.banner)
        yield ArtificeTerminal(self)
        footer = Footer()
        footer.display = False
        yield footer

    def on_mount(self) -> None:
        self.register_theme(create_artifice_theme())
        self.theme = "artifice"

    def action_toggle_footer(self) -> None:
        """Toggle the visibility of the footer."""
        footer = self.query_one(Footer)
        self.footer_visible = not self.footer_visible
        footer.display = self.footer_visible


def main():
    """Main entry point for the artifice command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("assistant", nargs="?", default=None, help="Assistant to use")
    parser.add_argument(
        "--system-prompt", default=None, help="System prompt to use for the assistant"
    )
    parser.add_argument("--prompt-prefix", default=None, help="Prefix to user prompts")
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=None,
        help="Extended thinking token budget (>0 enables thinking)",
    )
    parser.add_argument(
        "--fullscreen", action="store_true", default=None, help="Full screen"
    )
    parser.add_argument(
        "--logging", action="store_true", default=None, help="Enable logging"
    )
    parser.add_argument(
        "--tmux",
        default=None,
        metavar="TARGET",
        help="Use tmux shell executor with the given target (e.g. 'session:window.pane')",
    )
    parser.add_argument(
        "--tmux-prompt",
        default=None,
        metavar="PATTERN",
        help="Regex matching the shell prompt in the tmux pane",
    )
    args = parser.parse_args()

    # Load configuration from ~/.config/artifice/init.yaml
    config, config_error = load_config()

    # Auto-load system prompt from prompts/system.md if not set in config
    if config.system_prompt is None:
        system_prompt_content = load_prompt("system")
        if system_prompt_content is not None:
            config.system_prompt = system_prompt_content

    # Command-line arguments override config
    if args.assistant is not None:
        config.assistant = args.assistant
    if args.system_prompt is not None:
        config.system_prompt = args.system_prompt
    if args.prompt_prefix:
        config.prompt_prefix = args.prompt_prefix
    if args.thinking_budget is not None:
        config.thinking_budget = args.thinking_budget
    if args.tmux is not None:
        config.tmux_target = args.tmux
    if args.tmux_prompt is not None:
        config.tmux_prompt_pattern = args.tmux_prompt
    if args.logging:
        import logging

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            filename="artifice_assistant.log",
            filemode="a",  # append mode
        )
        logging.getLogger("artifice.assistant").setLevel(logging.DEBUG)

    app = ArtificeApp(config)

    # Show config error if any (as a notification once app starts)
    if config_error:
        app.call_later(
            lambda: app.notify(
                f"Config error: {config_error}", severity="warning", timeout=10
            )
        )

    if args.fullscreen:
        app.run()
    else:
        app.run(inline=True, inline_no_clear=True)


if __name__ == "__main__":
    main()
