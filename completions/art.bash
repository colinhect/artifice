# Bash completion for art command
# Source this file: source /path/to/completions/art.bash
# Or install to: /etc/bash_completion.d/ or ~/.bash_completion

_art_completion() {
    local cur prev words cword
    _init_completion || return

    case ${prev} in
        -a|--agent)
            COMPREPLY=($(compgen -W "$(art --list-agents 2>/dev/null)" -- "${cur}"))
            return
            ;;
        -p|--prompt-name)
            COMPREPLY=($(compgen -W "$(art --list-prompts 2>/dev/null)" -- "${cur}"))
            return
            ;;
        -s|--system-prompt)
            return
            ;;
        --print-completion)
            COMPREPLY=($(compgen -W "bash zsh fish" -- "${cur}"))
            return
            ;;
    esac

    if [[ ${cur} == -* ]]; then
        COMPREPLY=($(compgen -W "-a --agent -p --prompt-name -s --system-prompt --logging --list-agents --list-prompts --print-completion" -- "${cur}"))
    fi
}

complete -F _art_completion art
