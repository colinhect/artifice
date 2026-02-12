import argparse

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Static

from artifice import ArtificeTerminal
from artifice.config import load_config, ArtificeConfig

import logging

# Only log agent interactions, not other modules


logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
  filename='artifice_agent.log',
  filemode='a'  # append mode
)

logging.getLogger('artifice.agent').setLevel(logging.INFO)


class ArtificeHeader(Static):
    """Custom header with gradient fade effect."""

    DEFAULT_CSS = """
    ArtificeHeader {
        height: auto;
        padding: 0;
        margin: 0;
        background: $background;
        content-align: left top;
    }

    ArtificeHeader .header-bar {
        width: 1fr;
        height: auto;
        padding: 0;
        margin: 0;
        color: $primary;
    }
    """

    def __init__(self, show_banner):
        super().__init__()
        self.show_banner = show_banner

    def compose(self) -> ComposeResult:
        # Create a gradient bar using Unicode box-drawing characters
        # Start with a solid block from the left (matching in-context border) and fade right
        # Extended gradient for a more interesting fade effect
        gradient_chars = ["█", "█", "▓", "▓", "▒", "▒", "░", "░", "·", "·", " "]

        header_content = ""
        if self.show_banner:
            header_content = """┌─┐┬─┐┌┬┐┬┌─┐┬┌─┐┌─┐
├─┤├┬┘ │ │├┤ ││  ├┤
┴ ┴┴└─ ┴ ┴└  ┴└─┘└─┘\n"""
        
        header_content += "".join(gradient_chars)
        yield Static(header_content, classes="header-bar")


class ArtificeApp(App):
    TITLE = "Artifice Terminal"
    CSS = """
    Screen {
        layout: vertical;
        height: auto;
        padding: 0;
        margin: 0;
        border: none;
        overflow-y: auto;
    }

    ArtificeHeader {
        dock: top;
    }

    ArtificeTerminal {
        height: auto;
        margin-top: 0;
        padding-top: 0;
    }

    Footer {
        background: $panel-darken-1;
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f2", "toggle_footer", "Toggle Help"),
    ]

    def __init__(self, config: ArtificeConfig):
        self.config = config
        # Use config values, with command-line args taking precedence
        self.agent_type = config.agent_type or ""
        self.show_banner = config.show_banner
        self.footer_visible = False
        super().__init__()

    def compose(self) -> ComposeResult:
        yield ArtificeHeader(self.show_banner)
        yield ArtificeTerminal(self)
        footer = Footer()
        footer.display = False
        yield footer

    def action_toggle_footer(self) -> None:
        """Toggle the visibility of the footer."""
        footer = self.query_one(Footer)
        self.footer_visible = not self.footer_visible
        footer.display = self.footer_visible


def main():
    """Main entry point for the artifice command."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent-type",
        choices=["claude", "copilot", "ollama", "simulated"],
        default=None,
        help="Type of agent to use (claude, copilot, ollama, or simulated). Overrides config."
    )
    parser.add_argument("--show-banner", action="store_true", default=None, help="Show the banner")
    parser.add_argument("--model", default=None, help="Model to use (overrides config)")
    args = parser.parse_args()

    # Load configuration from ~/.config/artifice/init.py
    config, config_error = load_config()
    
    # Command-line arguments override config
    if args.agent_type is not None:
        config.agent_type = args.agent_type
    if args.show_banner is not None:
        config.show_banner = args.show_banner
    if args.model is not None:
        config.model = args.model

    app = ArtificeApp(config)
    
    # Show config error if any (as a notification once app starts)
    if config_error:
        app.call_later(lambda: app.notify(f"Config error: {config_error}", severity="warning", timeout=10))
    
    app.run(inline=True, inline_no_clear=True)


if __name__ == "__main__":
    main()
