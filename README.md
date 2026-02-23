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
cat error.log | art -a glm-5 -s "Why doesn't this work?" -f relevant_code.cpp

# Multiple files as context
art -f main.py -f utils.py "Refactor these to reduce duplication"
```

---

## Configuration

Create `~/.artifice/config.yaml`:

```yaml
agent: glm4

agents:
  glm4:
    api_key_env: HF_TOKEN
    provider: openai
    model: zai-org/GLM-4.7-Flash:novita
    base_url: https://router.huggingface.co/v1

prompts:
  summarize: "Summarize concisely. Use bullet points."
  review: "Review for bugs, security issues, and improvements."
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
- `ask` — prompt for each call (default)
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
  --tools PATTERNS        Enable tools ("*" or "read,write,...")
  --tool-approval MODE    ask | auto | deny
  --list-agents           List available agents
  --list-prompts          List available prompts
```

---

## Shell Completion

```bash
# Zsh
art --print-completion zsh > ~/.zsh/completions/_art

# Bash
art --print-completion bash >> ~/.bash_completion

# Fish
art --print-completion fish > ~/.config/fish/completions/art.fish
```

---

## Experimental TUI

Run `artifice` for an interactive terminal interface with:
- Python REPL and shell execution
- Tool calls and code execution
- Markdown rendering
- Block navigation

| Mode | Key |
|------|-----|
| AI prompt | `>` |
| Python | `]` |
| Shell | `$` |

---

## License

MIT
