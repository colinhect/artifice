import argparse

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Static

from artifice import ArtificeTerminal

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

    def __init__(self, agent_type, show_banner=False):
        self.agent_type = agent_type
        self.show_banner = show_banner
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
        default="",
        help="Type of agent to use (claude, copilot, ollama, or simulated). Defaults to empty."
    )
    parser.add_argument("--show-banner", action="store_true", help="Show the banner")
    args = parser.parse_args()

    app = ArtificeApp(args.agent_type, args.show_banner)
    app.run(inline=True, inline_no_clear=True)


if __name__ == "__main__":
    main()
