# bash completion for c6u
# source it from ~/.bashrc:
#   source /path/to/c6u/completions/c6u.bash

_c6u_complete() {
  local cur prev words cword
  _init_completion -n : 2>/dev/null || {
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
  }
  local cmds="setup login clear-password status clients wan wifi firmware all reboot \
    wifi-toggle dhcp wol qr log report metrics web watch speedtest tray \
    alias vendor rdns public-ip firmware-check latency ping discover presence \
    csv events daemon mqtt schedule profiles \
    notify rules automation watchdog rotate fingerprint heatmap cve sla extping \
    telegram discord portscan arpwatch dnscheck hibp tlswatch \
    tui repl sql search digest backup restore anomaly"
  if [[ ${COMP_CWORD} -le 2 ]]; then
    COMPREPLY=( $(compgen -W "${cmds}" -- "${cur}") )
    return 0
  fi
  case "${prev}" in
    --profile)
      local profs
      profs=$(ls profiles/*.json 2>/dev/null | xargs -n1 basename -s .json 2>/dev/null)
      COMPREPLY=( $(compgen -W "${profs}" -- "${cur}") ); return 0 ;;
    wifi-toggle) COMPREPLY=( $(compgen -W "host guest iot" -- "${cur}") ); return 0 ;;
    csv) COMPREPLY=( $(compgen -W "snapshots devices" -- "${cur}") ); return 0 ;;
    alias) COMPREPLY=( $(compgen -W "set rm list" -- "${cur}") ); return 0 ;;
  esac
}
complete -F _c6u_complete c6u
complete -F _c6u_complete "python main.py"
