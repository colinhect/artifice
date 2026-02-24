# Artifice

A CLI tool that pipes data to language models—designed to compose with your existing tools. Plus an experimental TUI for interactive sessions.

```bash
cat error.log | art "What's causing this error?"
```

---

## Installation

```bash
pip install artifice
art --install  # Creates ~/.artifice/config.yaml
```

## Quick Examples

```bash
# Simple prompt
art "Write a haiku about recursion"

# Pipe and analyze
git diff HEAD~1 | art "Explain these changes"

# Transform data
cat data.csv | art "Convert to JSON"

# Search and summarize
grep -r "TODO" src/ | art "Prioritize these TODOs"

# Generate tests
cat mymodule.py | art "Write pytest tests"

# Attach files as context with prompt
cat error.log | art -a glm-flash "Why doesn't this work?" -f relevant_code.cpp

# Multiple files as context
art -f main.py -f utils.py "Refactor these to reduce duplication"
```

---

## Configuration

Create `~/.artifice/config.yaml`:

```yaml
agent: glm-flash

agents:
  glm-flash:
    api_key_env: HF_TOKEN
    provider: openai
    model: zai-org/GLM-4.7-Flash:novita
    base_url: https://router.huggingface.co/v1
```

---

## Tool Support

Give the LLM controlled access to your system:

```bash
# Enable tools with interactive approval
art --tools "*" "Read README.md and suggest improvements"

# Auto-approve everything (use carefully)
art --tools "*" --tool-approval auto "Find all .txt files"

# Specific tools only
art --tools "read,glob" "Find Python files with TODOs"
```

**Available tools:** `read`, `write`, `edit`, `glob`, `shell`, `python`

**Approval modes:**
- `ask` — prompt for each call (default): `y`=yes, `n`=no, `a`=always allow, `c`=cancel session
- `auto` — approve everything
- `deny` — reject everything

---

## CLI Reference

```
art [OPTIONS] [PROMPT]

Options:
  -a, --agent AGENT       Agent name from config
  -p, --prompt-name NAME  Named prompt from config
  -s, --system-prompt     Override system prompt
  -f, --file FILE         Attach file(s) as context (multiple allowed)
  -m, --markdown          Render output as markdown in real-time
  --tools PATTERNS        Enable tools ("*" or "read,write,...")
  --tool-approval MODE    ask | auto | deny
  --tool-output           Show tool call output (hidden by default)
  --no-session            Disable saving session to ~/.artifice/sessions/
  --list-agents           List available agents
  --list-prompts          List available prompts
  --install               Install default config to ~/.artifice/
```

---

## Experimental TUI

Run `artifice` for an interactive terminal interface with:
- Python REPL and shell execution
- Tool calls and code execution
- Markdown rendering
- Block navigation

See [docs/TUI.md](docs/TUI.md) for full documentation.

| Mode | Key |
|------|-----|
| AI prompt | `>` |
| Python | `]` |
| Shell | `$` |

---

## License

MIT
