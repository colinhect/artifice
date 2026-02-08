import argparse

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from artifice import ArtificeTerminal

class ArtificeApp(App):
    TITLE = "Artifice Terminal"
    CSS = """
    Screen {
        layout: vertical;
        height: auto;
    }

    ArtificeTerminal {
        height: auto;
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

    def __init__(self, agent_type):
        self.agent_type = agent_type
        self.footer_visible = False
        super().__init__()

    def compose(self) -> ComposeResult:
        #yield Header()
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
        choices=["claude", "ollama", "simulated"],
        default="",
        help="Type of agent to use (claude, ollama, or simulated). Defaults to empty."
    )
    args = parser.parse_args()

    app = ArtificeApp(args.agent_type)
    app.run(inline=True, inline_no_clear=True)


if __name__ == "__main__":
    main()
