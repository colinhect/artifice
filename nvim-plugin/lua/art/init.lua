local M = {}

M.config = {
  cmd = "art",
  default_agent = nil,
  default_prompt = nil,
  split = "horizontal", -- "horizontal", "vertical", "float"
  no_session = true,
  extra_args = {},
  keymaps = {
    prompt = "<leader>aa",
    inline = "<leader>ai",
    replace = "<leader>ar",
    file = "<leader>af",
    stop = "<leader>as",
  },
}

--- Send a prompt and stream output to a split buffer.
---@param prompt string
---@param opts { stdin: string? }?
function M.prompt(prompt, opts)
  opts = opts or {}
  local ui = require("art.ui")
  local stream = require("art.stream")

  local buf = ui.open_output(prompt)
  stream.start(buf, {
    prompt = prompt,
    stdin = opts.stdin,
  })
end

--- Send a prompt and stream output inline at cursor position.
---@param prompt string
function M.inline(prompt)
  local ui = require("art.ui")
  local stream = require("art.stream")

  local line, col = ui.cursor_pos()
  local buf = vim.api.nvim_get_current_buf()
  stream.start(buf, {
    prompt = prompt,
    insert_at = { line, col },
  })
end

--- Replace visual selection with LLM response (selection is used as prompt).
function M.replace()
  local ui = require("art.ui")
  local stream = require("art.stream")

  local text, start_line, _, end_line, _ = ui.get_visual_selection()
  if not text or text == "" then
    vim.notify("art: no text selected", vim.log.levels.WARN)
    return
  end

  local buf = vim.api.nvim_get_current_buf()

  -- Delete the selected lines and position cursor for insertion
  vim.api.nvim_buf_set_lines(buf, start_line, end_line + 1, false, { "" })

  stream.start(buf, {
    stdin = text,
    insert_at = { start_line, 0 },
  })
end

--- Send current file as context with a prompt.
---@param prompt string
function M.file(prompt)
  local ui = require("art.ui")
  local stream = require("art.stream")

  local filepath = vim.fn.expand("%:p")
  if filepath == "" then
    vim.notify("art: no file in current buffer", vim.log.levels.WARN)
    return
  end

  local buf = ui.open_output(prompt)
  stream.start(buf, {
    prompt = prompt,
    file = filepath,
  })
end

--- Stop the currently running job.
function M.stop()
  require("art.stream").stop()
  vim.notify("art: stopped")
end

--- Setup the plugin with user config.
---@param user_config table?
function M.setup(user_config)
  M.config = vim.tbl_deep_extend("force", M.config, user_config or {})

  local km = M.config.keymaps
  if km then
    if km.prompt then
      vim.keymap.set("n", km.prompt, function()
        vim.ui.input({ prompt = "Art prompt: " }, function(input)
          if input and input ~= "" then
            M.prompt(input)
          end
        end)
      end, { desc = "Art: prompt" })
      vim.keymap.set("v", km.prompt, function()
        local text = require("art.ui").get_visual_selection()
        if text and text ~= "" then
          M.prompt(text)
        end
      end, { desc = "Art: prompt with selection" })
    end

    if km.inline then
      vim.keymap.set("n", km.inline, function()
        vim.ui.input({ prompt = "Art inline: " }, function(input)
          if input and input ~= "" then
            M.inline(input)
          end
        end)
      end, { desc = "Art: inline" })
    end

    if km.replace then
      vim.keymap.set("v", km.replace, function()
        M.replace()
      end, { desc = "Art: replace selection" })
    end

    if km.file then
      vim.keymap.set("n", km.file, function()
        vim.ui.input({ prompt = "Art file prompt: " }, function(input)
          if input and input ~= "" then
            M.file(input)
          end
        end)
      end, { desc = "Art: file context" })
    end

    if km.stop then
      vim.keymap.set("n", km.stop, function()
        M.stop()
      end, { desc = "Art: stop" })
    end
  end
end

return M
