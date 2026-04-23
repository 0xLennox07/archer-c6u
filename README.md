# c6u — TP-Link Archer C6U control suite

Auto-logs into your router's web admin (handles the RSA+AES encrypted login via [`tplinkrouterc6u`](https://github.com/AlexandrErohin/TP-Link-Archer-C6U)) and gives you a CLI, Textual TUI, REPL, live watch mode, SQLite history, desktop alerts, push notifications (ntfy/Pushover/Gotify), Telegram bot, Discord webhook, Prometheus exporter, Grafana dashboard, FastAPI dashboard with live WebSocket updates + history graphs + device heatmaps + security posture page, system tray, MAC vendor + alias enrichment, device fingerprinting, latency probes, mDNS/SSDP discovery, public-IP tracker, external-latency map, connectivity watchdog, MQTT publisher (Home Assistant auto-discovery) + native HA custom component, rules engine (YAML/JSON), cron-style automation jobs, anomaly detection, CVE watcher, ISP SLA report, webhooks, CSV export, SQL CLI, FTS5 event search, backup/restore, admin password rotator, parental-controls scheduler, port-scan detector, DNS-hijack detector, ARP watcher, TLS pin watcher, HIBP checker, multi-router profiles, Docker image + compose, shell completions (bash/zsh/fish/pwsh), GitHub Actions CI, and a combined background daemon that runs all of it.

## Setup

```bash
pip install -r requirements.txt
python main.py setup        # interactive wizard, password into OS keyring
```

Optional `config.json` extras:

```json
{
  "host": "http://192.168.0.1",
  "username": "admin",
  "verify_ssl": false,
  "timeout": 30,
  "webhooks": ["https://hooks.zapier.com/hooks/catch/.../"],
  "mqtt": {
    "host": "192.168.0.50", "port": 1883,
    "username": "homeassistant", "password": "secret",
    "discovery_prefix": "homeassistant", "device_id": "c6u_router"
  }
}
```

## Commands

### Info
| cmd | what |
|---|---|
| `login` | verify credentials |
| `status [--json]` | CPU/mem/clients/wifi flags |
| `clients [--json]` | enriched device list (alias + vendor) |
| `wan [--json]` | WAN + LAN IPv4 (DNS, gateway, netmask) |
| `wifi [--json]` | radios on/off (2.4G/5G/guest/IoT) |
| `firmware [--json]` | model + hardware + firmware |
| `dhcp [--json]` | DHCP leases + static reservations |
| `all [--json]` | dump everything |

### Control
| cmd | what |
|---|---|
| `reboot [-y]` | reboot router |
| `wifi-toggle <host\|guest\|iot> <2g\|5g\|6g> <on\|off>` | flip a radio |
| `wol <hostname\|MAC>` | Wake-on-LAN magic packet |
| `qr <ssid> <password> [--save file.png]` | WiFi-join QR |

### Identification & enrichment
| cmd | what |
|---|---|
| `alias set <MAC> <name>` | name a device |
| `alias rm <MAC>` | unname |
| `alias list` | show all |
| `vendor <MAC>` | OUI to vendor name |
| `rdns <IP>` | reverse DNS |

### Network probes
| cmd | what |
|---|---|
| `latency [--workers N] [--timeout S] [--json]` | ping every router-known device in parallel |
| `ping <target>` | one ping |
| `discover [--timeout S] [--json]` | mDNS + SSDP scan |
| `presence [--json]` | which named devices are home |
| `public-ip [--json]` | check & record router's public IP |
| `firmware-check` | compare to TP-Link's published firmware |
| `speedtest [--json]` | speedtest, stamped with router load |

### History & monitoring
| cmd | what |
|---|---|
| `log` | record one snapshot to SQLite |
| `watch [--interval N] [--log] [--no-alert]` | live TUI, alert on new device |
| `report [--days N] [--top N] [--json]` | summarize recent activity |
| `events [--limit N] [--json]` | recent join/leave/IP-change events |
| `csv <snapshots\|devices> <out.csv> [--days N]` | export DB tables |

### Services
| cmd | what |
|---|---|
| `web [--host H] [--port P]` | FastAPI dashboard (live + history graphs + device pages + heatmap + security) |
| `metrics [--port P] [--interval N]` | Prometheus exporter |
| `tray` | system tray icon w/ live client count |
| `tui` | full-screen Textual dashboard |
| `repl` | interactive shell — run any subcommand with history / tab-complete |
| `daemon` | combined loops: snapshot + latency + publicip + extping + anomaly + automation + webhooks + MQTT + rules + Discord |
| `mqtt [--discovery] [--state]` | one-shot MQTT publish |
| `schedule [--out file.xml]` | generate Windows Task Scheduler XML for `daemon` |
| `watchdog [--auto-reboot]` | connectivity watchdog — ping external targets, reboot on prolonged outage |
| `automation run` / `list` / `example` | cron-style scheduled actions (see [Automation](#automation)) |
| `telegram` | run the Telegram bot (long-polling) |
| `discord <text>` | post a message via configured Discord webhook |

### Rules & automation
| cmd | what |
|---|---|
| `rules list` / `example` / `test <kind>` | declarative triggers for events (see [Rules](#rules)) |
| `automation list` / `example` / `run` | cron-style scheduled actions |
| `notify <title> [body]` | send a test push via ntfy/Pushover/Gotify |
| `parental list` / `example` / `apply [--dry-run]` | block MACs during time windows |

### Intelligence
| cmd | what |
|---|---|
| `fingerprint [--scan-ports] [--json]` | guess device types from vendor + mDNS + open ports |
| `heatmap [--mac MAC] [--days N] [--top N]` | per-device presence heatmap (24x7) |
| `anomaly` | flag traffic spikes, unusual hours, latency outliers |
| `cve` | query NIST NVD for known vulns of the router model+firmware |
| `sla [--days N]` | ISP SLA report — mean / p10 / p95 / % of contract |
| `extping` | ping external targets (1.1.1.1 / 8.8.8.8 / …) and record to DB |
| `digest [--out file.html] [--days N]` | render weekly HTML digest |

### Security
| cmd | what |
|---|---|
| `portscan [--lan] [--target IP] [--json]` | TCP port scan — default: your public IP; `--lan` scans every device the router knows about |
| `arpwatch` | snapshot ARP table, alert on MAC↔IP changes |
| `dnscheck` | compare system resolver to DoH (Cloudflare + Google), flag hijacks |
| `tlswatch` | fingerprint (SPKI-pin) the router admin UI cert, alert on change |
| `hibp password|email|config [value]` | Have-I-Been-Pwned checker (password via k-anon, email via API key) |
| `rotate [--try-apply]` | generate 24-char admin password, store in keyring, keep rotation log |
| `rotate history` | show past rotation fingerprints |

### Data / utilities
| cmd | what |
|---|---|
| `sql "<statement>" [--json] [--mutate]` | ad-hoc SQL against the history DB (read-only by default) |
| `search query <q>` / `search rebuild` | FTS5 fulltext search across event log |
| `backup [--out file.tar.gz]` | bundle config + aliases + DB + profiles + rules + TLS pins |
| `restore <archive> [--overwrite]` | restore from a backup archive |

### Multi-router
- Default config: `config.json` in repo root.
- Add a profile: drop `profiles/office.json`, then run with `--profile office`.
- `python main.py profiles` lists them.
- Keyring entries are namespaced so passwords don't collide across profiles.

## Web dashboard

```bash
python main.py web   # http://127.0.0.1:8000
```

- **`/`** — live status, clients (with alias + vendor), reboot button. WebSocket-driven, auto-falls-back to polling.
- **`/history`** — Chart.js graphs from SQLite (clients, CPU, memory, speedtest, public-IP changes)
- **`/device/<MAC>`** — per-device timeline + latency chart
- **`/heatmaps`** — 24x7 presence heatmaps for the top-N devices
- **`/security`** — port scan, DNS hijack, ARP table, TLS pin, CVE, anomaly panels
- **`/digest`** — on-demand weekly HTML report
- **`/discover`** — live mDNS + SSDP scan

JSON endpoints: `/api/all`, `/api/history?days=N`, `/api/device/<MAC>`, `/api/discover`, `/api/presence`, `/api/public-ip`, `/api/latency-probe`, `/api/heatmap`, `/api/anomaly`, `/api/sla`, `/api/cve`, `/api/events/search?q=`, `/api/fingerprint`, `/api/portscan`, `/api/dns-check`, `/api/arp`, `/api/tls-check`, `/api/ext-latency`, `/api/rules`, `/api/automation`. WebSocket: `/ws` (5s status frames).

## Rules

Drop `rules.json` (or `rules.yaml`) in the repo root. `python main.py rules example` prints a starter file.

```json
{"rules": [
  {"name": "unknown device at night",
   "when": {"kind": "device_joined", "unknown_mac": true, "hour_between": [23, 6]},
   "then": [{"push": {"title": "New device!", "body": "{mac} {hostname}"}}]},
  {"name": "public ip change",
   "when": {"kind": "public_ip_changed"},
   "then": [{"push": {"title": "WAN IP changed", "body": "{previous} -> {current}"}}]}
]}
```

Triggers: `kind`, `mac_in`, `unknown_mac`, `hour_between: [start, end]` (wraps midnight).
Actions: `push`, `webhook`, `notify_desktop`, `reboot_router`, `wifi_toggle`, `exec`.
The daemon dispatches every event (`device_joined`, `device_left`, `public_ip_changed`, `outage_started`, `outage_recovered`, `anomaly_*`, etc.) through the rules.

## Automation

`automation.json` defines cron-style scheduled actions, run by the daemon or `python main.py automation run`.

```json
{"jobs": [
  {"name": "guest wifi off midnight", "cron": "0 0 * * *",
   "action": {"wifi_toggle": {"which": "guest", "band": "2g", "state": "off"}}},
  {"name": "weekly reboot", "cron": "0 3 * * 1",
   "action": {"reboot_router": {}}}
]}
```

Supported cron fields: minute · hour · day-of-month · month · day-of-week (0=Sun). `*`, ranges (`1-5`), lists (`1,3,5`) and steps (`*/15`) all work.

## Push notifications

Add a `push` block to `config.json` with any subset of:

```json
"push": {
  "ntfy":     {"topic": "my-c6u-alerts", "server": "https://ntfy.sh"},
  "pushover": {"token": "APP_TOKEN", "user": "USER_KEY"},
  "gotify":   {"url": "https://gotify.example", "token": "APP_TOKEN"}
}
```

`python main.py notify "Hello" "World"` fans out to every configured provider.

## Telegram / Discord

```json
"telegram": {"token": "123:ABC...", "allowed_chats": [12345678]},
"discord":  {"webhook": "https://discord.com/api/webhooks/..."}
```

`python main.py telegram` runs the bot (long-polling). Commands: `/status`, `/clients`, `/presence`, `/public_ip`, `/speedtest`, `/events [N]`, `/reboot confirm`. The daemon mirrors every event into Discord via the webhook.

## Grafana

`grafana/c6u_dashboard.json` is a pre-built dashboard for the Prometheus exporter — import via **Dashboards → Import → Upload JSON**, then select your Prometheus datasource.

## Home Assistant

Two integration paths:
1. **MQTT auto-discovery** (easier): set the `mqtt` block in `config.json`, then `python main.py mqtt --discovery && python main.py daemon`.
2. **Native custom component**: copy `ha_custom_component/c6u/` into `<HA config>/custom_components/c6u/` and add to `configuration.yaml`:
   ```yaml
   c6u:
     host: http://192.168.0.1
     username: admin
     password: !secret c6u_password
   sensor:
     - platform: c6u
   ```

## Docker

```bash
docker compose up -d
```

Runs three containers: `c6u-daemon` (host-networked for discovery), `c6u-web` (port 8000), `c6u-metrics` (port 9100). Mount your `config.json`, `aliases.json`, `rules.json`, and `automation.json` into the container.

## Daemon (recommended setup)

```bash
python main.py daemon   # snapshot every 60s, latency every 120s, publicip every 600s
```

Fires webhooks (`device_joined`, `device_left`, `public_ip_changed`) to every URL in `config.json -> webhooks`, and publishes MQTT state if `mqtt` is configured.

To run at logon as a Windows scheduled task:
```bash
python main.py schedule --out c6u_daemon.xml
schtasks /create /tn c6u_daemon /xml c6u_daemon.xml
```

## Home Assistant integration

1. Set `mqtt` block in `config.json`.
2. `python main.py mqtt --discovery` (one-shot). HA auto-creates sensors: `sensor.c6u_clients`, `sensor.c6u_cpu`, `sensor.c6u_mem`, `sensor.c6u_wired`, `sensor.c6u_wifi`, `sensor.c6u_public_ip`.
3. Run `python main.py daemon` to keep state fresh.

## Files it creates

| path | purpose |
|---|---|
| `config.json` | router URL/user/options (no password) |
| `aliases.json` | MAC → friendly name |
| `known_macs.txt` | watch-mode whitelist |
| `c6u.sqlite3` | snapshots + devices + speedtests + latency + events + public_ip |
| `profiles/*.json` | additional router profiles |

All gitignored.

## Shell completions

Drop one of the `completions/c6u.*` files into your shell's completion directory:
- bash: `source completions/c6u.bash` in `~/.bashrc`
- zsh: place `completions/_c6u.zsh` on `$fpath`
- fish: copy `completions/c6u.fish` to `~/.config/fish/completions/`
- PowerShell: `. completions\c6u.ps1` in your `$PROFILE`

## Tests

```bash
pytest
```

34 tests cover DB round-trips, WoL packet shape, QR payload, aliases, public-IP change detection, event log, CLI help, push fanout, rules matching, cron expressions, heatmap aggregation, SLA percentiles, anomaly scan, backup round-trip, FTS5 search, fingerprint heuristics, parental schedule windows.

## Build a single .exe

```bash
pyinstaller c6u.spec
# -> dist/c6u.exe
```
