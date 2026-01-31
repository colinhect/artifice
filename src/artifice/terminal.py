from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from artifice import InteractivePython


class ArtificeTerminal(App):
    TITLE = "Artifice Terminal"
    CSS = """
    Screen {
        layout: vertical;
    }

    InteractivePython {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+r", "reset", "Reset REPL"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield InteractivePython()
        yield Footer()

    def action_reset(self) -> None:
        """Reset the REPL."""
        self.query_one(InteractivePython).reset()


def main():
    """Main entry point for the artifice command."""
    app = ArtificeTerminal()
    app.run()


if __name__ == "__main__":
    main()
