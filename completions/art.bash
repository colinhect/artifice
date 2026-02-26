# Bash completion for art command
# Source this file: source /path/to/completions/art.bash
# Or install to: /etc/bash_completion.d/ or ~/.bash_completion

_art_completion() {
    local cur prev words cword
    _init_completion || return

    # Complete @file attachments
    if [[ ${cur} == @* ]]; then
        local prefix="${cur#@}"
        COMPREPLY=($(compgen -f -- "${prefix}" | sed 's/^/@/'))
        compopt -o nospace
        return
    fi

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
        --add-prompt)
            _filedir
            return
            ;;
        --tool-approval)
            COMPREPLY=($(compgen -W "ask auto deny" -- "${cur}"))
            return
            ;;
        --tools|--new-prompt)
            return
            ;;
    esac

    if [[ ${cur} == -* ]]; then
        COMPREPLY=($(compgen -W "-a --agent -p --prompt-name -s --system-prompt -m --markdown --logging --list-agents --list-prompts --get-current-agent --tools --tool-approval --tool-output --install --add-prompt --new-prompt --no-session" -- "${cur}"))
    fi
}

complete -F _art_completion art
