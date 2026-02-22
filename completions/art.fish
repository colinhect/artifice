# Fish completion for art command
# Install to: ~/.config/fish/completions/art.fish

complete -c art -f

complete -c art -s a -l agent -d 'Agent name from config' -a '(art --list-agents 2>/dev/null)'
complete -c art -s p -l prompt-name -d 'Named prompt from config' -a '(art --list-prompts 2>/dev/null)'
complete -c art -s s -l system-prompt -d 'System prompt for the model'
complete -c art -l logging -d 'Enable logging to stderr'
complete -c art -l list-agents -d 'List available agent names'
complete -c art -l list-prompts -d 'List available prompt names'
complete -c art -l print-completion -d 'Print shell completion script' -a 'bash zsh fish'
