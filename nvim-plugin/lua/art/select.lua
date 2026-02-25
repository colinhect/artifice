local M = {}

local state = {
  agent = nil,
  prompt = nil,
}

--- Get the currently selected agent.
---@return string?
function M.current_agent()
  return state.agent
end

--- Get the currently selected prompt.
---@return string?
function M.current_prompt()
  return state.prompt
end

--- Set the current agent directly.
---@param name string?
function M.set_agent(name)
  state.agent = name
  if name then
    vim.notify("art: agent set to " .. name)
  else
    vim.notify("art: agent cleared")
  end
end

--- Set the current prompt directly.
---@param name string?
function M.set_prompt(name)
  state.prompt = name
  if name then
    vim.notify("art: prompt set to " .. name)
  else
    vim.notify("art: prompt cleared")
  end
end

--- Run a command and return its output lines (blocking).
---@param cmd string[]
---@return string[]
local function run_cmd(cmd)
  local result = vim.fn.systemlist(cmd)
  if vim.v.shell_error ~= 0 then
    return {}
  end
  -- Filter empty lines
  local lines = {}
  for _, line in ipairs(result) do
    local trimmed = vim.trim(line)
    if trimmed ~= "" then
      table.insert(lines, trimmed)
    end
  end
  return lines
end

--- Pick an agent interactively, or set directly if name is provided.
---@param name string?
function M.pick_agent(name)
  if name and name ~= "" then
    M.set_agent(name)
    return
  end

  local config = require("art").config
  local agents = run_cmd({ config.cmd, "--list-agents" })
  if #agents == 0 then
    vim.notify("art: no agents found", vim.log.levels.WARN)
    return
  end

  vim.ui.select(agents, { prompt = "Select agent:" }, function(choice)
    if choice then
      M.set_agent(choice)
    end
  end)
end

--- Pick a prompt interactively, or set directly if name is provided.
---@param name string?
function M.pick_prompt(name)
  if name and name ~= "" then
    M.set_prompt(name)
    return
  end

  local config = require("art").config
  local prompts = run_cmd({ config.cmd, "--list-prompts" })
  if #prompts == 0 then
    vim.notify("art: no prompts found", vim.log.levels.WARN)
    return
  end

  vim.ui.select(prompts, { prompt = "Select prompt:" }, function(choice)
    if choice then
      M.set_prompt(choice)
    end
  end)
end

return M
