if vim.g.loaded_art then
  return
end
vim.g.loaded_art = true

-- :Art <prompt> — stream to split (visual mode: use selection as prompt)
vim.api.nvim_create_user_command("Art", function(opts)
  local prompt = opts.args
  if opts.range > 0 then
    -- Called from visual mode
    local text = require("art.ui").get_visual_selection()
    if text and text ~= "" then
      if prompt ~= "" then
        -- Selection as context, args as prompt — pipe selection via stdin
        require("art").prompt(prompt, { stdin = text })
      else
        -- Selection is the prompt
        require("art").prompt(text)
      end
      return
    end
  end
  if prompt == "" then
    vim.notify("art: no prompt provided", vim.log.levels.WARN)
    return
  end
  require("art").prompt(prompt)
end, { nargs = "*", range = true, desc = "Send prompt to art and stream output" })

-- :ArtInline <prompt> — stream at cursor position
vim.api.nvim_create_user_command("ArtInline", function(opts)
  local prompt = opts.args
  if prompt == "" then
    vim.notify("art: no prompt provided", vim.log.levels.WARN)
    return
  end
  require("art").inline(prompt)
end, { nargs = "+", desc = "Stream art output at cursor position" })

-- :ArtReplace — replace visual selection with LLM response
vim.api.nvim_create_user_command("ArtReplace", function(_)
  require("art").replace()
end, { range = true, desc = "Replace visual selection with art response" })

-- :ArtFile <prompt> — send current file as context
vim.api.nvim_create_user_command("ArtFile", function(opts)
  local prompt = opts.args
  if prompt == "" then
    vim.notify("art: no prompt provided", vim.log.levels.WARN)
    return
  end
  require("art").file(prompt)
end, { nargs = "+", desc = "Send current file as context to art" })

-- :ArtAgent [name] — set/pick agent
vim.api.nvim_create_user_command("ArtAgent", function(opts)
  local name = opts.args
  if name == "" then
    name = nil
  end
  require("art.select").pick_agent(name)
end, { nargs = "?", desc = "Set or pick art agent" })

-- :ArtPrompt [name] — set/pick prompt
vim.api.nvim_create_user_command("ArtPrompt", function(opts)
  local name = opts.args
  if name == "" then
    name = nil
  end
  require("art.select").pick_prompt(name)
end, { nargs = "?", desc = "Set or pick art named prompt" })

-- :ArtStop — cancel running job
vim.api.nvim_create_user_command("ArtStop", function(_)
  require("art").stop()
end, { desc = "Stop running art job" })
