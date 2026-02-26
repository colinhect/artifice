# Fish completion for art command
# Install to: ~/.config/fish/completions/art.fish

complete -c art -f

complete -c art -s a -l agent -d 'Agent name from config' -a '(art --list-agents 2>/dev/null)'
complete -c art -s p -l prompt-name -d 'Named prompt from config' -a '(art --list-prompts 2>/dev/null)'
complete -c art -s s -l system-prompt -d 'System prompt for the model'
complete -c art -s m -l markdown -d 'Render output as markdown'
complete -c art -l logging -d 'Enable logging to stderr'
complete -c art -l list-agents -d 'List available agent names'
complete -c art -l list-prompts -d 'List available prompt names'
complete -c art -l get-current-agent -d 'Print current agent name'
complete -c art -l tools -d 'Enable tools (comma-separated patterns)' -r
complete -c art -l tool-approval -d 'Tool approval mode' -a 'ask auto deny' -r
complete -c art -l tool-output -d 'Show tool call output'
complete -c art -l install -d 'Install default configuration'
complete -c art -l add-prompt -d 'Add a prompt file' -r -F
complete -c art -l new-prompt -d 'Create a new prompt' -r
complete -c art -l no-session -d 'Disable saving session'

# Complete @file attachments
complete -c art -a '(for f in (commandline -ct | string replace -r "^@" "" | string collect); __fish_complete_path "$f" | string replace -r "^" "@"; end)' -n 'string match -q "@*" (commandline -ct)'
