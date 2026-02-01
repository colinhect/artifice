from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from artifice import ArtificeTerminal

class ArtificeApp(App):
    TITLE = "Artifice Terminal"
    CSS = """
    Screen {
        layout: vertical;
    }

    ArtificeTerminal {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, agent_type):
        self.agent_type = agent_type
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Header()
        yield ArtificeTerminal(self)
        yield Footer()

import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agent-type",
        choices=["claude", "simulated"],
        default="",
        help="Type of agent to use (claude or simulated). Defaults to empty."
    )
    args = parser.parse_args()

    """Main entry point for the artifice command."""
    app = ArtificeApp(args.agent_type)
    app.run()


if __name__ == "__main__":
    main()
