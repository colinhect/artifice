local M = {}

--- Create a scratch buffer for art output.
---@param prompt string The prompt (used for buffer name)
---@return number buf Buffer handle
local function create_scratch_buf(prompt)
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_option_value("buftype", "nofile", { buf = buf })
  vim.api.nvim_set_option_value("bufhidden", "wipe", { buf = buf })
  vim.api.nvim_set_option_value("filetype", "markdown", { buf = buf })

  local name = "[art] " .. (prompt or ""):sub(1, 40)
  pcall(vim.api.nvim_buf_set_name, buf, name)

  return buf
end

--- Open a scratch buffer in a horizontal split and return the buffer handle.
---@param prompt string
---@return number buf
function M.split(prompt)
  local buf = create_scratch_buf(prompt)
  vim.cmd("belowright split")
  vim.api.nvim_win_set_buf(0, buf)
  return buf
end

--- Open a scratch buffer in a vertical split and return the buffer handle.
---@param prompt string
---@return number buf
function M.vsplit(prompt)
  local buf = create_scratch_buf(prompt)
  vim.cmd("belowright vsplit")
  vim.api.nvim_win_set_buf(0, buf)
  return buf
end

--- Open a scratch buffer in a floating window and return the buffer handle.
---@param prompt string
---@return number buf
function M.float(prompt)
  local buf = create_scratch_buf(prompt)

  local width = math.floor(vim.o.columns * 0.8)
  local height = math.floor(vim.o.lines * 0.8)
  local row = math.floor((vim.o.lines - height) / 2)
  local col = math.floor((vim.o.columns - width) / 2)

  vim.api.nvim_open_win(buf, true, {
    relative = "editor",
    width = width,
    height = height,
    row = row,
    col = col,
    style = "minimal",
    border = "rounded",
  })

  return buf
end

--- Open a scratch buffer based on the configured split mode.
---@param prompt string
---@return number buf
function M.open_output(prompt)
  local config = require("art").config
  local mode = config.split or "horizontal"
  if mode == "vertical" then
    return M.vsplit(prompt)
  elseif mode == "float" then
    return M.float(prompt)
  else
    return M.split(prompt)
  end
end

--- Get the current cursor position (0-indexed line, 0-indexed col).
---@return number line, number col
function M.cursor_pos()
  local pos = vim.api.nvim_win_get_cursor(0)
  return pos[1] - 1, pos[2]
end

--- Get visual selection text and range.
---@return string text, number start_line, number start_col, number end_line, number end_col
function M.get_visual_selection()
  local start_pos = vim.fn.getpos("'<")
  local end_pos = vim.fn.getpos("'>")
  local start_line = start_pos[2] - 1 -- 0-indexed
  local end_line = end_pos[2] - 1
  local lines = vim.api.nvim_buf_get_lines(0, start_line, end_line + 1, false)

  -- Adjust for column selection
  if #lines > 0 then
    local start_col = start_pos[3] - 1
    local end_col = end_pos[3]
    if #lines == 1 then
      lines[1] = lines[1]:sub(start_col + 1, end_col)
    else
      lines[1] = lines[1]:sub(start_col + 1)
      lines[#lines] = lines[#lines]:sub(1, end_col)
    end
  end

  return table.concat(lines, "\n"), start_line, start_pos[3] - 1, end_line, end_pos[3]
end

return M
