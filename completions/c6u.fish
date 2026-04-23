# fish completion — drop into ~/.config/fish/completions/

set -l cmds setup login clear-password status clients wan wifi firmware all \
    reboot wifi-toggle dhcp wol qr log report metrics web watch speedtest tray \
    alias vendor rdns public-ip firmware-check latency ping discover presence \
    csv events daemon mqtt schedule profiles \
    notify rules automation watchdog rotate fingerprint heatmap cve sla extping \
    telegram discord portscan arpwatch dnscheck hibp tlswatch \
    tui repl sql search digest backup restore anomaly

complete -c c6u -f
complete -c c6u -n "__fish_use_subcommand" -a "$cmds"
complete -c c6u -n "__fish_seen_subcommand_from wifi-toggle" -a "host guest iot"
complete -c c6u -n "__fish_seen_subcommand_from csv" -a "snapshots devices"
complete -c c6u -n "__fish_seen_subcommand_from alias" -a "set rm list"
