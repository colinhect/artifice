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
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield InteractivePython()
        yield Footer()

def main():
    """Main entry point for the artifice command."""
    app = ArtificeTerminal()
    app.run()


if __name__ == "__main__":
    main()
