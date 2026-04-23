# PowerShell argument completer for c6u.
# Add to your $PROFILE:
#   . "C:\path\to\c6u\completions\c6u.ps1"

$c6uCommands = @(
    'setup','login','clear-password','status','clients','wan','wifi','firmware','all',
    'reboot','wifi-toggle','dhcp','wol','qr','log','report','metrics','web','watch',
    'speedtest','tray','alias','vendor','rdns','public-ip','firmware-check','latency',
    'ping','discover','presence','csv','events','daemon','mqtt','schedule','profiles',
    'notify','rules','automation','watchdog','rotate','fingerprint','heatmap','cve',
    'sla','extping','telegram','discord','portscan','arpwatch','dnscheck','hibp',
    'tlswatch','tui','repl','sql','search','digest','backup','restore','anomaly'
)

Register-ArgumentCompleter -Native -CommandName c6u -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $c6uCommands | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}
