# Artifice Documentation

Comprehensive design documentation for the Artifice project.

## Document Overview

### [ARCHITECTURE.md](ARCHITECTURE.md)
**High-level system design and architectural decisions**

Topics covered:
- Core principles and design philosophy
- System architecture and component layers
- Data flow diagrams
- Threading model and async architecture
- State management
- Configuration system
- Extension points
- Security considerations
- Performance characteristics
- Design rationale

**Start here** for understanding the overall system structure.

---

### [COMPONENTS.md](COMPONENTS.md)
**Detailed component specifications and interfaces**

Topics covered:
- Application layer (App, Header, Footer)
- Terminal layer (ArtificeTerminal orchestrator)
- I/O components (TerminalOutput, TerminalInput, PinnedOutput)
- Block components (CodeInputBlock, AgentOutputBlock, etc.)
- Execution components (CodeExecutor, ShellExecutor)
- Agent components (ClaudeAgent, OllamaAgent, etc.)
- Streaming components (StreamingFenceDetector)
- Utility components (History, SessionTranscript, Config)
- Design patterns used

**Read this** for understanding how individual components work and interact.

---

### [STREAMING.md](STREAMING.md)
**Streaming architecture and real-time fence detection**

Topics covered:
- Why streaming matters
- Streaming pipeline (background thread → main loop)
- Fence detection algorithm (state machine)
- String tracking (avoiding false positives)
- Block updates and buffering strategies
- Threading constraints (critical: no widget mount in callbacks)
- Rendering performance optimizations
- Finalization and error handling
- Testing strategies
- Known limitations

**Essential reading** for anyone working on agent integration or streaming.

---

### [EXECUTION_MODEL.md](EXECUTION_MODEL.md)
**Code execution and REPL design**

Topics covered:
- Execution modes (Python REPL, Shell)
- Execution flow (input → block → execution → output)
- Python execution (namespace, compilation, output capture)
- Shell execution (process lifecycle, streaming, persistence)
- Output handling (buffering, markdown rendering)
- Agent integration (auto-send, context management)
- Cancellation
- Result structures
- Error handling

**Read this** for understanding code execution and output handling.

---

### [CONFIGURATION.md](CONFIGURATION.md)
**Configuration system and extension guide**

Topics covered:
- Configuration sources and priority
- Agent configuration (provider, model, system prompt)
- Display configuration (banner, markdown rendering)
- Behavior configuration (auto-send, shell init)
- Session configuration
- Command-line arguments
- Environment variables
- Extension points (custom agents, executors, themes)
- Advanced patterns
- Configuration security
- Troubleshooting
- Configuration examples

**Read this** for customizing Artifice or building extensions.

---

### [DEVELOPMENT.md](DEVELOPMENT.md)
**Development guidelines and contribution workflow**

Topics covered:
- Project structure
- Development setup
- Coding conventions
- Testing strategy (unit, integration, fixtures, mocking)
- Debugging techniques
- Common development tasks (adding agents, executors, blocks)
- Performance optimization
- Common pitfalls (widget mounting, event loop blocking)
- Release process
- Contribution guidelines
- Troubleshooting development issues

**Read this** before contributing code or starting development.

---

## Quick Reference

### For Users
1. Start with [README.md](../README.md) in the root directory
2. See [CONFIGURATION.md](CONFIGURATION.md) for customization
3. Check [ARCHITECTURE.md](ARCHITECTURE.md) for understanding how it works

### For Contributors
1. Read [DEVELOPMENT.md](DEVELOPMENT.md) for setup and guidelines
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) for system overview
3. Study [COMPONENTS.md](COMPONENTS.md) for component details
4. See [STREAMING.md](STREAMING.md) if working on agent integration

### For Integrators/Extenders
1. Read [CONFIGURATION.md](CONFIGURATION.md) for extension points
2. Review [COMPONENTS.md](COMPONENTS.md) for interfaces
3. Study [EXECUTION_MODEL.md](EXECUTION_MODEL.md) if adding executors
4. See [DEVELOPMENT.md](DEVELOPMENT.md) for coding conventions

---

## Document Status

| Document | Version | Last Updated | Status |
|----------|---------|--------------|--------|
| ARCHITECTURE.md | 0.1.0 | 2026-02-12 | ✅ Current |
| COMPONENTS.md | 0.1.0 | 2026-02-12 | ✅ Current |
| STREAMING.md | 0.1.0 | 2026-02-12 | ✅ Current |
| EXECUTION_MODEL.md | 0.1.0 | 2026-02-12 | ✅ Current |
| CONFIGURATION.md | 0.1.0 | 2026-02-12 | ✅ Current |
| DEVELOPMENT.md | 0.1.0 | 2026-02-12 | ✅ Current |

---

## Additional Resources

### External Documentation
- [Textual Framework](https://textual.textualize.io/) - TUI framework used by Artifice
- [Anthropic API](https://docs.anthropic.com/) - Claude API documentation
- [Ollama](https://ollama.ai/docs) - Local model integration

### Project Files
- [CLAUDE.md](../CLAUDE.md) - Instructions for AI assistants working on this project
- [pyproject.toml](../pyproject.toml) - Project metadata and dependencies
- [README.md](../README.md) - User-facing documentation

### Memory Files
- [MEMORY.md](~/.claude/projects/-home-colin-dev-artifice/memory/MEMORY.md) - Critical lessons learned

---

## Contributing to Documentation

### When to Update

Update documentation when:
- Adding new features or components
- Changing architectural decisions
- Modifying APIs or interfaces
- Discovering new patterns or anti-patterns
- Fixing bugs that reveal design issues

### Documentation Standards

**Format:** Markdown with:
- Clear hierarchical structure (H1 → H2 → H3)
- Code examples with syntax highlighting
- Diagrams using ASCII art or code blocks
- Cross-references to related documents

**Style:**
- Present tense ("The detector processes..." not "will process")
- Active voice ("The system creates..." not "is created by")
- Concrete examples over abstract descriptions
- "Why" before "how" (explain rationale)

**Version:**
- Update version number when significant changes made
- Update "Last Updated" date
- Maintain document status table

### Review Checklist

- [ ] Accurate (reflects current implementation)
- [ ] Complete (covers all relevant aspects)
- [ ] Clear (understandable to target audience)
- [ ] Consistent (follows documentation standards)
- [ ] Cross-referenced (links to related docs)
- [ ] Examples included (code samples, diagrams)
- [ ] Version updated (if significant changes)

---

## Feedback

Found an issue with the documentation? Please open an issue on GitHub with:
- Document name and section
- Description of issue (inaccurate, unclear, missing, etc.)
- Suggested improvement

## License

Documentation is licensed under the same license as the Artifice project (MIT).
