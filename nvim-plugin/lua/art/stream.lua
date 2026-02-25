local M = {}

local current_job = nil

--- Build the command table for art invocation.
---@param opts { prompt: string?, agent: string?, prompt_name: string?, file: string?, extra_args: string[] }
---@return string[]
local function build_cmd(opts)
  local config = require("art").config
  local cmd = { config.cmd }

  if config.no_session then
    table.insert(cmd, "--no-session")
  end

  -- Disable tools for now
  table.insert(cmd, "--tools")
  table.insert(cmd, "''")

  -- Agent flag
  local agent = opts.agent or require("art.select").current_agent() or config.default_agent
  if agent then
    table.insert(cmd, "-a")
    table.insert(cmd, agent)
  end

  -- Named prompt flag
  local prompt_name = opts.prompt_name or require("art.select").current_prompt() or config.default_prompt
  if prompt_name then
    table.insert(cmd, "-p")
    table.insert(cmd, prompt_name)
  end

  -- File context
  if opts.file then
    table.insert(cmd, "-f")
    table.insert(cmd, opts.file)
  end

  -- Extra args from config
  for _, arg in ipairs(config.extra_args) do
    table.insert(cmd, arg)
  end

  -- Positional prompt (if not piping via stdin)
  if opts.prompt and not opts.stdin then
    table.insert(cmd, opts.prompt)
  end

  return cmd
end

--- Start streaming art output into the given buffer.
---@param buf number Buffer handle
---@param opts { prompt: string?, stdin: string?, agent: string?, prompt_name: string?, file: string?, insert_at: number[]? }
---@return number job_id
function M.start(buf, opts)
  opts = opts or {}

  -- Cancel any existing job
  M.stop()

  local cmd = build_cmd(opts)

  -- For inline/replace modes, track the insertion point
  local insert_line = opts.insert_at and opts.insert_at[1] or nil
  local insert_col = opts.insert_at and opts.insert_at[2] or nil

  -- Append arbitrary text (may contain newlines) at the current write position.
  -- Called from vim.schedule so it's safe to modify buffers.
  local function append_text(text)
    vim.schedule(function()
      if not vim.api.nvim_buf_is_valid(buf) then
        M.stop()
        return
      end

      local lines = vim.split(text, "\n", { plain = true })

      if insert_line then
        -- Inline/replace mode: splice into buffer at tracked position
        local existing = vim.api.nvim_buf_get_lines(buf, insert_line, insert_line + 1, false)
        local cur = existing[1] or ""
        local before = cur:sub(1, insert_col)
        local after = cur:sub(insert_col + 1)

        if #lines == 1 then
          vim.api.nvim_buf_set_lines(buf, insert_line, insert_line + 1, false, { before .. lines[1] .. after })
          insert_col = insert_col + #lines[1]
        else
          local new_lines = { before .. lines[1] }
          for i = 2, #lines - 1 do
            table.insert(new_lines, lines[i])
          end
          table.insert(new_lines, lines[#lines] .. after)
          vim.api.nvim_buf_set_lines(buf, insert_line, insert_line + 1, false, new_lines)
          insert_line = insert_line + #lines - 1
          insert_col = #lines[#lines]
        end
      else
        -- Scratch buffer mode: append at end
        local line_count = vim.api.nvim_buf_line_count(buf)
        local last_line = vim.api.nvim_buf_get_lines(buf, line_count - 1, line_count, false)[1] or ""

        if #lines == 1 then
          vim.api.nvim_buf_set_lines(buf, line_count - 1, line_count, false, { last_line .. lines[1] })
        else
          local new_lines = { last_line .. lines[1] }
          for i = 2, #lines do
            table.insert(new_lines, lines[i])
          end
          vim.api.nvim_buf_set_lines(buf, line_count - 1, line_count, false, new_lines)
        end

        -- Scroll to bottom in all windows showing this buffer
        for _, win in ipairs(vim.fn.win_findbuf(buf)) do
          local new_count = vim.api.nvim_buf_line_count(buf)
          vim.api.nvim_win_set_cursor(win, { new_count, 0 })
        end
      end
    end)
  end

  local job_id = vim.fn.jobstart(cmd, {
    stdout_buffered = false,
    pty = true,
    on_stdout = function(_, data, _)
      if not data then
        return
      end
      -- Reconstruct the raw chunk from the data list (split on \n by neovim)
      local text = table.concat(data, "\n")
      -- Strip carriage returns injected by pty
      text = text:gsub("\r", "")
      -- Stream every chunk immediately — no line buffering
      if text ~= "" then
        append_text(text)
      end
    end,
    on_stderr = function(_, data, _)
      -- Silently ignore stderr
    end,
    on_exit = function(_, _, _)
      current_job = nil
    end,
  })

  if job_id <= 0 then
    vim.notify("art: failed to start job (is `" .. cmd[1] .. "` installed?)", vim.log.levels.ERROR)
    return job_id
  end

  current_job = job_id

  -- If we need to pipe stdin, send it and close
  if opts.stdin then
    vim.fn.chansend(job_id, opts.stdin)
    vim.fn.chanclose(job_id, "stdin")
  end

  return job_id
end

--- Stop the currently running job.
function M.stop()
  if current_job then
    pcall(vim.fn.jobstop, current_job)
    current_job = nil
  end
end

--- Check if a job is currently running.
---@return boolean
function M.is_running()
  return current_job ~= nil
end

return M
