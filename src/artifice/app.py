import argparse

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Static
from textual.theme import Theme

from artifice import ArtificeTerminal
from artifice.config import load_config, ArtificeConfig

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

def create_artifice_theme() -> Theme:
    #black = "#07080A" 
    dark_gray = "#3B4252" 
    gray = "#434C5E" 
    #light_gray = "#4C566A" 
    #light_gray_bright = "#616E88" 
    #darkest_white = "#D8DEE9" 
    #darker_white = "#E5E9F0" 
    white = "#ECEFF4" 
    teal = "#8FBCBB" 
    #off_blue = "#88C0D0" 
    glacier = "#81A1C1" 
    blue = "#5E81AC" 
    red = "#BF616A" 
    #orange = "#D08770" 
    #yellow = "#EBCB8B" 
    green = "#A3BE8C" 
    #purple = "#B48EAD" 
    #none = "NONE"

    return Theme(
        name="artifice",
        primary=blue,
        secondary=green,
        accent=teal,
        foreground=white,
        #background=black,
        success=green,
        warning=glacier,
        error=red,
        surface=dark_gray,
        panel=gray,
        dark=True,
    )


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
        self.provider = config.provider or ""
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
    parser.add_argument(
        "--provider",
        choices=["claude", "copilot", "ollama", "simulated"],
        default=None,
        help="Type of agent to use (claude, copilot, ollama, or simulated). Overrides config."
    )
    parser.add_argument("--model", default=None, help="Model to use (overrides config)")
    parser.add_argument("--system-prompt", default=None, help="System prompt to use for the agent")
    parser.add_argument("--prompt-prefix", default=None, help="Prefix to user prompts")
    parser.add_argument("--banner", action="store_true", default=None, help="Show the banner")
    parser.add_argument("--fullscreen", action="store_true", default=None, help="Full screen")
    parser.add_argument("--thinking-budget", type=int, default=None, help="Extended thinking token budget (enables thinking)")
    parser.add_argument("--logging", action="store_true", default=None, help="Enable logging")
    args = parser.parse_args()

    # Load configuration from ~/.config/artifice/init.py
    config, config_error = load_config()
    
    # Command-line arguments override config
    if args.provider is not None:
        config.provider = args.provider
    if args.banner is not None:
        config.banner = args.banner
    if args.model is not None:
        config.model = args.model
    if args.system_prompt:
        config.system_prompt = args.system_prompt
    if args.prompt_prefix:
        config.prompt_prefix = args.prompt_prefix
    if args.thinking_budget is not None:
        config.thinking_budget = args.thinking_budget
    if args.logging:
        import logging
        logging.basicConfig(
          level=logging.INFO,
          format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
          filename='artifice_agent.log',
          filemode='a'  # append mode
        )
        logging.getLogger('artifice.agent').setLevel(logging.DEBUG)

    app = ArtificeApp(config)
    
    # Show config error if any (as a notification once app starts)
    if config_error:
        app.call_later(lambda: app.notify(f"Config error: {config_error}", severity="warning", timeout=10))
    
    if args.fullscreen:
        app.run()
    else:
        app.run(inline=True, inline_no_clear=True)


if __name__ == "__main__":
    main()
