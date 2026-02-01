from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from artifice import ArtificeRepl


class ArtificeTerminal(App):
    TITLE = "Artifice Terminal"
    CSS = """
    Screen {
        layout: vertical;
    }

    ArtificeRepl {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ArtificeRepl()
        yield Footer()

def main():
    """Main entry point for the artifice command."""
    app = ArtificeTerminal()
    app.run()


if __name__ == "__main__":
    main()
