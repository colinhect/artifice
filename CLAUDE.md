# Claude Instructions for Artifice

## Project Overview
Artifice is an interactive Python REPL and coding environment with AI agent integration. It's a TUI application built with Textual that allows human-in-the-loop code execution.

## Important Constraints

### Do Not Execute
- **Never run the application directly** (`artifice` or `python src/artifice/terminal.py`)
- The TUI interface requires terminal interaction that won't work in this environment
- Test changes through unit tests instead

### Do Not Use Git
- **Never use git commands** for any operations
- The user manages version control manually

## Development Guidelines
- The project uses Python with Textual for the TUI
- Source code is in `src/artifice/`
- Tests use pytest
- When making changes, focus on code correctness and explain modifications clearly
