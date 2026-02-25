# NeoVim Plugin

A NeoVim plugin for streaming LLM responses directly into your editor using `art`.

## Installation

### lazy.nvim

```lua
{
  dir = "/path/to/artifice/nvim-plugin",
  config = function()
    require("art").setup()
  end,
}
```

### Manual

Add `nvim-plugin/` to your runtime path:

```lua
vim.opt.rtp:prepend("/path/to/artifice/nvim-plugin")
require("art").setup()
```

## Commands

| Command | Description |
|---|---|
| `:Art <prompt>` | Send a prompt and stream the response into a split buffer |
| `:'<,'>Art [prompt]` | Visual mode: use selection as prompt, or as context if a prompt is also given |
| `:ArtInline <prompt>` | Stream the response at the current cursor position |
| `:'<,'>ArtReplace` | Replace the visual selection with the LLM response (selection is used as the prompt) |
| `:ArtFile <prompt>` | Send the current file as context along with the prompt |
| `:ArtAgent [name]` | Set the agent directly, or open a picker if no name is given |
| `:ArtPrompt [name]` | Set a named prompt directly, or open a picker if no name is given |
| `:ArtStop` | Cancel the currently running job |

## Default Keymaps

| Key | Mode | Action |
|---|---|---|
| `<leader>aa` | Normal | Prompt for input, stream to split |
| `<leader>aa` | Visual | Send selection as prompt, stream to split |
| `<leader>ai` | Normal | Prompt for input, insert at cursor |
| `<leader>ar` | Visual | Replace selection with LLM response |
| `<leader>af` | Normal | Prompt for input, send current file as context |
| `<leader>as` | Normal | Stop the running job |

## Configuration

Pass options to `setup()` to override defaults:

```lua
require("art").setup({
  cmd = "art",               -- path to the art CLI
  default_agent = nil,       -- agent name from your art config
  default_prompt = nil,      -- named prompt from your art config
  split = "horizontal",      -- "horizontal", "vertical", or "float"
  no_session = true,         -- pass --no-session to art
  extra_args = {},           -- additional CLI args passed to every invocation
  keymaps = {
    prompt = "<leader>aa",
    inline = "<leader>ai",
    replace = "<leader>ar",
    file = "<leader>af",
    stop = "<leader>as",
  },
})
```

Set any keymap to `false` to disable it:

```lua
require("art").setup({
  keymaps = {
    inline = false,
  },
})
```

## Output Modes

- **Horizontal split** (default) -- opens a scratch buffer below the current window
- **Vertical split** -- opens a scratch buffer to the right
- **Float** -- opens a centered floating window with a rounded border

Output buffers are set to the `markdown` filetype for syntax highlighting and are wiped when closed.

## Lua API

You can call the plugin functions directly from Lua:

```lua
local art = require("art")

art.prompt("Explain this error")
art.prompt("Summarize this", { stdin = some_text })
art.inline("Complete this function")
art.replace()  -- call after visual selection
art.file("Review this file")
art.stop()
```

Agent and prompt selection:

```lua
local select = require("art.select")

select.pick_agent()          -- interactive picker
select.set_agent("gpt-4")   -- set directly
select.pick_prompt()         -- interactive picker
select.set_prompt("review")  -- set directly
```
