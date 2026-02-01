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

    def compose(self) -> ComposeResult:
        yield Header()
        yield ArtificeTerminal()
        yield Footer()

def main():
    """Main entry point for the artifice command."""
    app = ArtificeApp()
    app.run()


if __name__ == "__main__":
    main()
