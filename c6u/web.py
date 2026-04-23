"""FastAPI web dashboard with live status, history graphs, and device detail."""
from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from . import aliases as aliases_mod
from . import db as db_mod
from . import discover as discover_mod
from . import latency as latency_mod
from . import presence as presence_mod
from . import publicip as publicip_mod
from . import vendor as vendor_mod
from .client import router
from .render import enrich_devices_json, to_json

app = FastAPI(title="c6u router dashboard")


# ----- HTML pages -----

INDEX_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>c6u router</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { color-scheme: dark light; --b:#8884; --m:#888; }
  body { font: 14px/1.4 system-ui, sans-serif; margin:0; padding:20px; max-width:1280px; }
  h1 { margin:0 0 4px; }
  nav a { margin-right:14px; color:#48f; text-decoration:none; }
  nav a:hover { text-decoration:underline; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
  @media (max-width:900px){ .grid { grid-template-columns:1fr; } }
  .card { border:1px solid var(--b); border-radius:8px; padding:14px; }
  .card.full { grid-column:1 / -1; }
  .card h2 { margin:0 0 10px; font-size:13px; color:var(--m); text-transform:uppercase; letter-spacing:.04em; }
  table { border-collapse:collapse; width:100%; font-size:13px; }
  th,td { padding:6px 8px; text-align:left; border-bottom:1px solid #8882; }
  th { color:var(--m); font-weight:600; }
  tr:last-child td { border-bottom:none; }
  .ok{color:#4c9}.off{color:#c55}
  .bar { height:6px; background:#8882; border-radius:3px; overflow:hidden; }
  .bar > div { height:100%; background:linear-gradient(90deg,#4c9,#48f); }
  button { padding:8px 14px; border:1px solid var(--b); background:transparent; color:inherit;
           border-radius:6px; cursor:pointer; font:inherit; }
  button:hover { background:#8882; }
  button.danger { color:#c55; border-color:#c558; }
  .mono { font-family:ui-monospace,Menlo,Consolas,monospace; }
  .mute { color:var(--m); }
  .pill { display:inline-block; padding:2px 8px; border-radius:10px; background:#8882; font-size:11px; }
  a.dev { color:#48f; text-decoration:none; }
  a.dev:hover { text-decoration:underline; }
  canvas { max-height: 220px; }
</style></head>
<body>
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#111111">
<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});</script>
<h1>c6u router dashboard</h1>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/heatmaps">Heatmaps</a><a href="/security">Security</a><a href="/dns">DNS</a><a href="/flows">Flows</a><a href="/rules">Rules</a><a href="/digest">Digest</a><a href="/discover">Discovered</a></nav>
<p class="mute" id="updated">loading… <span id="wsstatus"></span></p>
<div class="grid">
  <div class="card"><h2>Status</h2><div id="status"></div>
    <div style="margin-top:12px">
      <button onclick="reboot()" class="danger">Reboot router</button>
      <button onclick="load()">Refresh</button>
    </div>
  </div>
  <div class="card"><h2>WAN / LAN</h2><div id="wan"></div></div>
  <div class="card full"><h2>Connected devices <span id="count" class="mute"></span></h2>
    <table><thead><tr>
      <th>Name</th><th>Hostname</th><th>IP</th><th>MAC</th><th>Vendor</th>
      <th>Type</th><th>Down</th><th>Up</th><th>Usage</th><th>Online</th>
    </tr></thead><tbody id="clients"></tbody></table>
  </div>
</div>
<script>
function fmtBps(v){if(!v)return '-';const u=['B/s','KB/s','MB/s','GB/s'];let i=0;while(v>=1024&&i<u.length-1){v/=1024;i++;}return v.toFixed(1)+' '+u[i];}
function fmtBytes(v){if(!v)return '-';const u=['B','KB','MB','GB','TB'];let i=0;while(v>=1024&&i<u.length-1){v/=1024;i++;}return v.toFixed(1)+' '+u[i];}
function fmtUptime(s){if(!s)return '-';s=+s;const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return (d?d+'d ':'')+h+'h '+m+'m';}
function bool(v){return v===true?'<span class=ok>on</span>':v===false?'<span class=off>off</span>':'-';}
function kv(k,v){return `<tr><th>${k}</th><td>${v}</td></tr>`;}

async function load(){
  try{ const d=await(await fetch('/api/all')).json(); render(d); }
  catch(e){document.getElementById('updated').textContent='error: '+e.message;}
}
async function reboot(){if(!confirm('Reboot the router? All connections drop.'))return;
  const r=await fetch('/api/reboot',{method:'POST'});alert(r.ok?'Reboot command sent.':'Reboot failed.');}
function render(d){
  try{
    const s=d.status,w=d.wan,fw=d.firmware;
    document.getElementById('updated').textContent=`${fw.model} · fw ${fw.firmware_version} · ${new Date().toLocaleTimeString()}`;
    document.getElementById('status').innerHTML='<table>'+[
      kv('Connection',s.conn_type||'-'),kv('WAN IPv4',s.wan_ipv4_addr||'-'),
      kv('LAN IPv4',s.lan_ipv4_addr||'-'),kv('WAN uptime',fmtUptime(s.wan_ipv4_uptime)),
      kv('CPU',s.cpu_usage!=null?`${(s.cpu_usage*100).toFixed(0)}%<div class=bar><div style="width:${s.cpu_usage*100}%"></div></div>`:'-'),
      kv('Memory',s.mem_usage!=null?`${(s.mem_usage*100).toFixed(0)}%<div class=bar><div style="width:${s.mem_usage*100}%"></div></div>`:'-'),
      kv('Clients',`${s.clients_total} (wired ${s.wired_total}, wifi ${s.wifi_clients_total}, guest ${s.guest_clients_total})`),
      kv('WiFi 2.4G',bool(s.wifi_2g_enable)),kv('WiFi 5G',bool(s.wifi_5g_enable)),
      kv('Guest 2.4G',bool(s.guest_2g_enable)),kv('Guest 5G',bool(s.guest_5g_enable)),
    ].join('')+'</table>';
    document.getElementById('wan').innerHTML='<table>'+[
      kv('WAN conn type',w.wan_ipv4_conntype||'-'),kv('WAN IP',w.wan_ipv4_ipaddr||'-'),
      kv('WAN gateway',w.wan_ipv4_gateway||'-'),kv('WAN netmask',w.wan_ipv4_netmask||'-'),
      kv('DNS 1',w.wan_ipv4_pridns||'-'),kv('DNS 2',w.wan_ipv4_snddns||'-'),
      kv('WAN MAC',w.wan_macaddr||'-'),kv('LAN IP',w.lan_ipv4_ipaddr||'-'),
      kv('LAN MAC',w.lan_macaddr||'-'),kv('DHCP',bool(w.lan_ipv4_dhcp_enable)),
      kv('Remote mgmt',bool(w.remote)),kv('Public IP', d.public_ip || '-'),
    ].join('')+'</table>';
    const devs=d.devices||[];
    document.getElementById('count').textContent=`(${devs.length})`;
    document.getElementById('clients').innerHTML=devs.map(x=>`<tr>
        <td>${x.alias?'<b>'+x.alias+'</b>':'<span class=mute>—</span>'}</td>
        <td><a class=dev href="/device/${encodeURIComponent(x.macaddr||'')}">${x.hostname||'-'}</a></td>
        <td class=mono>${x.ipaddr||'-'}</td>
        <td class=mono>${x.macaddr||'-'}</td>
        <td>${x.vendor||'-'}</td>
        <td><span class=pill>${x.type||'-'}</span></td>
        <td>${fmtBps(x.down_speed)}</td><td>${fmtBps(x.up_speed)}</td>
        <td>${fmtBytes(x.traffic_usage)}</td><td>${fmtUptime(x.online_time)}</td>
      </tr>`).join('');
  }catch(e){document.getElementById('updated').textContent='error: '+e.message;}
}
let ws, pollTimer;
function startWS(){
  try{
    const proto = location.protocol==='https:'?'wss':'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = ()=>{document.getElementById('wsstatus').innerHTML='<span class=pill>live</span>'; clearInterval(pollTimer);};
    ws.onmessage = e=>{const d=JSON.parse(e.data); if(!d.error)render(d);};
    ws.onerror = ()=>{ws?.close();};
    ws.onclose = ()=>{document.getElementById('wsstatus').innerHTML='<span class=pill>polling</span>'; startPolling();};
  }catch(e){startPolling();}
}
function startPolling(){if(pollTimer)return; load(); pollTimer=setInterval(load,10000);}
startWS();
</script></body></html>
"""

HISTORY_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>c6u history</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{color-scheme:dark light;--b:#8884;--m:#888;}
  body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:20px;max-width:1280px;}
  h1{margin:0 0 4px;}nav a{margin-right:14px;color:#48f;text-decoration:none;}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;}
  @media(max-width:900px){.grid{grid-template-columns:1fr;}}
  .card{border:1px solid var(--b);border-radius:8px;padding:14px;}
  .card.full{grid-column:1/-1;}.card h2{margin:0 0 10px;font-size:13px;color:var(--m);text-transform:uppercase;letter-spacing:.04em;}
  select{padding:4px 8px;background:transparent;color:inherit;border:1px solid var(--b);border-radius:4px;}
  canvas{max-height:240px;}
</style></head><body>
<h1>history</h1>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/discover">Discovered</a></nav>
<p>Window: <select id="win" onchange="load()">
  <option value="1">last 24h</option><option value="7" selected>last 7d</option><option value="30">last 30d</option>
</select></p>
<div class="grid">
  <div class="card"><h2>Clients over time</h2><canvas id="c1"></canvas></div>
  <div class="card"><h2>CPU + memory</h2><canvas id="c2"></canvas></div>
  <div class="card full"><h2>Speedtest history</h2><canvas id="c3"></canvas></div>
  <div class="card full"><h2>Public IP changes</h2><pre id="ipc" class="mute" style="max-height:160px;overflow:auto;"></pre></div>
</div>
<script>
let charts={};
function ts2lbl(ts){const d=new Date(ts*1000);return d.toLocaleString();}
async function load(){
  const win=document.getElementById('win').value;
  const d=await(await fetch('/api/history?days='+win)).json();
  const labels=d.snapshot.map(r=>ts2lbl(r.ts));
  Object.values(charts).forEach(c=>c.destroy());
  charts.c1=new Chart(document.getElementById('c1'),{type:'line',data:{labels,datasets:[
    {label:'Total',data:d.snapshot.map(r=>r.clients),borderColor:'#48f',tension:.2},
    {label:'Wired',data:d.snapshot.map(r=>r.wired),borderColor:'#4c9',tension:.2},
    {label:'WiFi',data:d.snapshot.map(r=>r.wifi),borderColor:'#fa3',tension:.2},
  ]},options:{maintainAspectRatio:false,plugins:{legend:{labels:{color:'#aaa'}}},scales:{x:{ticks:{display:false}},y:{beginAtZero:true,ticks:{color:'#aaa'}}}}});
  charts.c2=new Chart(document.getElementById('c2'),{type:'line',data:{labels,datasets:[
    {label:'CPU %',data:d.snapshot.map(r=>r.cpu*100),borderColor:'#c55',tension:.2},
    {label:'Mem %',data:d.snapshot.map(r=>r.mem*100),borderColor:'#a8f',tension:.2},
  ]},options:{maintainAspectRatio:false,plugins:{legend:{labels:{color:'#aaa'}}},scales:{x:{ticks:{display:false}},y:{beginAtZero:true,max:100,ticks:{color:'#aaa'}}}}});
  const sl=d.speedtest.map(r=>ts2lbl(r.ts));
  charts.c3=new Chart(document.getElementById('c3'),{type:'line',data:{labels:sl,datasets:[
    {label:'Down Mbps',data:d.speedtest.map(r=>r.down_mbps),borderColor:'#4c9',tension:.2,yAxisID:'y'},
    {label:'Up Mbps',data:d.speedtest.map(r=>r.up_mbps),borderColor:'#48f',tension:.2,yAxisID:'y'},
    {label:'Ping ms',data:d.speedtest.map(r=>r.ping_ms),borderColor:'#fa3',tension:.2,yAxisID:'y1'},
  ]},options:{maintainAspectRatio:false,plugins:{legend:{labels:{color:'#aaa'}}},scales:{
    y:{type:'linear',position:'left',beginAtZero:true,ticks:{color:'#aaa'}},
    y1:{type:'linear',position:'right',beginAtZero:true,grid:{drawOnChartArea:false},ticks:{color:'#aaa'}}}}});
  document.getElementById('ipc').textContent = d.public_ip.length
    ? d.public_ip.map(r=>`${ts2lbl(r.ts)}  ${r.ip}`).join('\\n')
    : 'no public-IP records yet';
}
load();
</script></body></html>
"""

DEVICE_HTML = """
<!doctype html><html><head><meta charset="utf-8"><title>device</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>:root{color-scheme:dark light;}body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:20px;max-width:1100px;}
h1{margin:0;}nav a{margin-right:14px;color:#48f;text-decoration:none;}
.card{border:1px solid #8884;border-radius:8px;padding:14px;margin-top:16px;}
table{border-collapse:collapse;width:100%;font-size:13px;}th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #8882;}
.mono{font-family:ui-monospace,Consolas,monospace;}canvas{max-height:240px;}</style>
</head><body>
<h1 id="title">device</h1>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/discover">Discovered</a></nav>
<div class="card"><h3>Identity</h3><table id="id"></table></div>
<div class="card"><h3>Latency</h3><canvas id="lat"></canvas></div>
<div class="card"><h3>Recent samples</h3><div id="samples"></div></div>
<script>
const mac = decodeURIComponent(location.pathname.split('/').pop());
function ts2lbl(ts){return new Date(ts*1000).toLocaleString();}
function kv(k,v){return `<tr><th>${k}</th><td>${v}</td></tr>`;}
async function load(){
  const d=await(await fetch('/api/device/'+encodeURIComponent(mac))).json();
  document.title='device '+mac;
  document.getElementById('title').textContent = (d.alias||d.last_hostname||mac);
  document.getElementById('id').innerHTML=[
    kv('Alias', d.alias||'-'),kv('Last hostname', d.last_hostname||'-'),
    kv('MAC', `<span class=mono>${mac}</span>`),kv('Vendor', d.vendor||'-'),
    kv('Last IP', d.last_ip||'-'),kv('Samples', d.samples.length),
  ].join('');
  if(d.latency.length){
    new Chart(document.getElementById('lat'),{type:'line',data:{
      labels:d.latency.map(r=>ts2lbl(r.ts)),
      datasets:[{label:'RTT ms',data:d.latency.map(r=>r.rtt_ms),borderColor:'#48f',tension:.2,spanGaps:true}]
    },options:{maintainAspectRatio:false,scales:{x:{ticks:{display:false}},y:{beginAtZero:true,ticks:{color:'#aaa'}}}}});
  }
  document.getElementById('samples').innerHTML='<table><tr><th>When</th><th>IP</th><th>Hostname</th><th>Online</th><th>Active</th></tr>'+
    d.samples.slice(-50).reverse().map(s=>`<tr><td>${ts2lbl(s.ts)}</td><td class=mono>${s.ip||'-'}</td><td>${s.hostname||'-'}</td><td>${s.online}</td><td>${s.active?'yes':'no'}</td></tr>`).join('')+'</table>';
}
load();
</script></body></html>
"""

DISCOVER_HTML = """
<!doctype html><html><head><meta charset="utf-8"><title>discovered</title>
<style>:root{color-scheme:dark light;}body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:20px;max-width:1100px;}
nav a{margin-right:14px;color:#48f;text-decoration:none;}
.card{border:1px solid #8884;border-radius:8px;padding:14px;margin-top:16px;}
table{border-collapse:collapse;width:100%;font-size:13px;}th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #8882;}
.mono{font-family:ui-monospace,Consolas,monospace;}.mute{color:#888;}</style>
</head><body><h1>discovered services</h1>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/discover">Discovered</a></nav>
<p class="mute">scanning takes ~5 seconds…</p>
<div class="card"><h3>mDNS</h3><div id="mdns">loading…</div></div>
<div class="card"><h3>SSDP / UPnP</h3><div id="ssdp">loading…</div></div>
<script>
async function load(){
  const d=await(await fetch('/api/discover')).json();
  document.getElementById('mdns').innerHTML = d.mdns.length
    ? '<table><tr><th>Service</th><th>Name</th><th>Host</th><th>Port</th><th>Addresses</th></tr>'+
      d.mdns.map(x=>`<tr><td>${x.service}</td><td>${x.name}</td><td>${x.host}</td><td>${x.port}</td><td class=mono>${(x.addresses||[]).join(', ')}</td></tr>`).join('')+'</table>'
    : '<i class=mute>nothing found</i>';
  document.getElementById('ssdp').innerHTML = d.ssdp.length
    ? '<table><tr><th>IP</th><th>ST</th><th>Server</th><th>Location</th></tr>'+
      d.ssdp.map(x=>`<tr><td class=mono>${x.ip}</td><td>${x.st||'-'}</td><td>${x.server||'-'}</td><td class=mono>${x.location||'-'}</td></tr>`).join('')+'</table>'
    : '<i class=mute>nothing found</i>';
}
load();
</script></body></html>
"""


# ----- routes -----

@app.get("/", response_class=HTMLResponse)
def index(): return HTMLResponse(INDEX_HTML)


@app.get("/history", response_class=HTMLResponse)
def history_page(): return HTMLResponse(HISTORY_HTML)


@app.get("/discover", response_class=HTMLResponse)
def discover_page(): return HTMLResponse(DISCOVER_HTML)


@app.get("/device/{mac}", response_class=HTMLResponse)
def device_page(mac: str): return HTMLResponse(DEVICE_HTML)


@app.get("/api/all")
def api_all():
    try:
        with router() as r:
            s = r.get_status()
            ipv4 = r.get_ipv4_status()
            fw = r.get_firmware()
        public_ip = None
        try:
            with db_mod.connect() as conn:
                row = conn.execute("SELECT ip FROM public_ip ORDER BY ts DESC LIMIT 1").fetchone()
                public_ip = row["ip"] if row else None
        except Exception:
            pass
        return JSONResponse({
            "status": to_json(s),
            "wan": to_json(ipv4),
            "firmware": to_json(fw),
            "devices": enrich_devices_json(s.devices),
            "public_ip": public_ip,
            "ts": int(time.time()),
        })
    except Exception as e:
        raise HTTPException(502, str(e))


@app.post("/api/reboot")
def api_reboot():
    try:
        with router() as r:
            r.reboot()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/history")
def api_history(days: int = 7):
    return db_mod.history_series(days=days)


@app.get("/api/device/{mac}")
def api_device(mac: str, days: int = 7):
    aliases = aliases_mod.load()
    h = db_mod.device_history(mac, days=days)
    norm = mac.upper().replace("-", ":")
    last_ip = h["samples"][-1]["ip"] if h["samples"] else None
    last_host = h["samples"][-1]["hostname"] if h["samples"] else None
    return {
        **h,
        "alias": aliases.get(norm),
        "vendor": vendor_mod.vendor(norm),
        "last_ip": last_ip,
        "last_hostname": last_host,
    }


@app.get("/api/discover")
def api_discover(timeout: float = 4.0):
    return discover_mod.scan_all(timeout=timeout)


@app.get("/api/presence")
def api_presence():
    return presence_mod.who_is_present()


@app.get("/api/public-ip")
def api_public_ip():
    return publicip_mod.check_and_record()


@app.post("/api/latency-probe")
def api_latency_probe():
    return {"samples": latency_mod.probe_and_record()}


# ----- new endpoints (heatmap / anomaly / sla / cve / search / fingerprint / security) -----

@app.get("/api/heatmap")
def api_heatmap(mac: str | None = None, days: int = 30, top: int = 12):
    from . import heatmap as heatmap_mod
    if mac:
        return heatmap_mod.heatmap(mac, days=days)
    return {"devices": heatmap_mod.heatmap_all(days=days, top=top)}


@app.get("/api/anomaly")
def api_anomaly(baseline_days: int = 14, recent_minutes: int = 60):
    from . import anomaly as anomaly_mod
    return {"anomalies": anomaly_mod.scan(baseline_days=baseline_days,
                                           recent_minutes=recent_minutes)}


@app.get("/api/sla")
def api_sla(days: int = 30):
    from . import sla as sla_mod
    return sla_mod.report(days=days)


@app.get("/api/cve")
def api_cve():
    from . import cve as cve_mod
    try:
        with router() as r:
            fw = r.get_firmware()
        return cve_mod.check(fw.model, firmware=fw.firmware_version)
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/events/search")
def api_event_search(q: str, limit: int = 100):
    from . import search as search_mod
    return {"q": q, "results": search_mod.query(q, limit=limit)}


@app.get("/api/fingerprint")
def api_fingerprint(scan_ports: bool = False):
    from . import fingerprint as fp_mod
    try:
        with router() as r:
            s = r.get_status()
    except Exception as e:
        raise HTTPException(502, str(e))
    devs = [{"mac": str(d.macaddress) or "",
             "hostname": d.hostname,
             "ip": str(d.ipaddress) if d.ipaddress else None} for d in s.devices]
    return {"devices": fp_mod.fingerprint_all(devs, scan_ports=scan_ports)}


@app.get("/api/portscan")
def api_portscan():
    from . import portscan as ps_mod
    return ps_mod.scan()


@app.get("/api/portscan/lan")
def api_portscan_lan(timeout: float = 0.5):
    from . import portscan as ps_mod
    try:
        r = ps_mod.scan_lan(timeout=timeout)
        r["risky"] = ps_mod.risky_findings(r)
        return r
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/api/dns-check")
def api_dns_check():
    from . import dnscheck
    return dnscheck.check()


@app.get("/api/arp")
def api_arp():
    from . import arpwatch
    return arpwatch.check()


@app.get("/api/tls-check")
def api_tls_check():
    from . import tlswatch
    try:
        return tlswatch.check()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/ext-latency")
def api_ext_latency(days: int = 1, target: str | None = None):
    from . import extping
    return {"series": extping.series(days=days, target=target)}


@app.post("/api/ext-latency/probe")
def api_ext_latency_probe():
    from . import extping
    return {"results": extping.probe()}


@app.get("/api/digest", response_class=HTMLResponse)
def api_digest(days: int = 7):
    from . import digest
    return HTMLResponse(digest.build(days=days))


@app.post("/api/rotate-password")
def api_rotate(try_apply: bool = False):
    from . import rotate
    return rotate.rotate(try_apply=try_apply)


@app.get("/api/rules")
def api_rules():
    from . import rules
    return {"rules": rules.load_rules()}


@app.post("/api/rules/save")
def api_rules_save(body: dict):
    """Overwrite rules.json with the submitted rule list."""
    import json
    from . import config as _cfg
    rules_list = (body or {}).get("rules") or []
    path = _cfg.ROOT / "rules.json"
    path.write_text(json.dumps({"rules": rules_list}, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(rules_list), "path": str(path)}


@app.post("/api/rules/test")
def api_rules_test(body: dict):
    from . import rules
    evt = body.get("event") or {}
    only_rules = body.get("rules")  # optionally test with unsaved in-memory rules
    fired = rules.dispatch(evt, cfg={}, rules=only_rules)
    return {"fired": fired, "event": evt}


@app.get("/api/automation")
def api_automation():
    from . import automation
    return {"jobs": [{k: v for k, v in j.items() if not k.startswith("_")}
                       for j in automation.load_jobs()]}


@app.post("/api/automation/save")
def api_automation_save(body: dict):
    import json
    from . import config as _cfg
    jobs = (body or {}).get("jobs") or []
    clean = [{k: v for k, v in j.items() if not k.startswith("_")} for j in jobs]
    path = _cfg.ROOT / "automation.json"
    path.write_text(json.dumps({"jobs": clean}, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(clean), "path": str(path)}


# ----- DNS filter, NetFlow, passive DNS endpoints -----

@app.get("/api/dns/stats")
def api_dns_stats(days: int = 1):
    from . import dnsfilter
    return dnsfilter.stats(days=days)


@app.post("/api/dns/blocklist/update")
def api_dns_blocklist_update():
    from . import dnsfilter
    return dnsfilter.update_blocklists()


@app.get("/api/flows/top")
def api_flows_top(days: int = 1, by: str = "bytes", limit: int = 20):
    from . import netflow
    return {"flows": netflow.top(days=days, by=by, limit=limit),
            "sources": netflow.by_src_ip(days=days, limit=limit)}


@app.get("/api/pdns")
def api_pdns(ip: str | None = None, hostname: str | None = None, limit: int = 100):
    from . import passivedns
    return {"records": passivedns.recent(ip=ip, hostname=hostname, limit=limit)}


# ----- Plugin info + PWA manifest/service worker -----

@app.get("/api/plugins")
def api_plugins():
    from . import plugins
    return {"plugins": plugins.info()}


@app.get("/manifest.webmanifest")
def pwa_manifest():
    return JSONResponse({
        "name": "c6u router",
        "short_name": "c6u",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#111111",
        "theme_color": "#111111",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@app.get("/sw.js", response_class=PlainTextResponse)
def pwa_sw():
    return PlainTextResponse("""
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => self.clients.claim());
const CACHE = 'c6u-v1';
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  e.respondWith(
    caches.open(CACHE).then(async cache => {
      try {
        const resp = await fetch(r);
        if (resp.ok) cache.put(r, resp.clone());
        return resp;
      } catch (err) {
        const cached = await cache.match(r);
        if (cached) return cached;
        throw err;
      }
    })
  );
});
""", media_type="application/javascript")


@app.get("/icon-192.png")
def icon_192():
    from io import BytesIO
    from fastapi.responses import Response
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (192, 192), (17, 17, 17))
        d = ImageDraw.Draw(img)
        d.rectangle((12, 12, 180, 180), outline=(100, 180, 255), width=6)
        d.text((62, 74), "c6u", fill=(100, 180, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception:
        return Response(status_code=404)


@app.get("/icon-512.png")
def icon_512():
    from io import BytesIO
    from fastapi.responses import Response
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (512, 512), (17, 17, 17))
        d = ImageDraw.Draw(img)
        d.rectangle((32, 32, 480, 480), outline=(100, 180, 255), width=14)
        d.text((180, 220), "c6u", fill=(100, 180, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception:
        return Response(status_code=404)


# ----- WebSocket live updates -----

@app.websocket("/ws")
async def ws(socket: WebSocket):
    await socket.accept()
    try:
        while True:
            try:
                def fetch():
                    with router() as r:
                        s = r.get_status()
                        ipv4 = r.get_ipv4_status()
                        fw = r.get_firmware()
                    public_ip = None
                    try:
                        with db_mod.connect() as conn:
                            row = conn.execute(
                                "SELECT ip FROM public_ip ORDER BY ts DESC LIMIT 1"
                            ).fetchone()
                            public_ip = row["ip"] if row else None
                    except Exception:
                        pass
                    return {
                        "status": to_json(s), "wan": to_json(ipv4),
                        "firmware": to_json(fw),
                        "devices": enrich_devices_json(s.devices),
                        "public_ip": public_ip,
                        "ts": int(time.time()),
                    }
                payload = await asyncio.get_event_loop().run_in_executor(None, fetch)
                await socket.send_json(payload)
            except Exception as e:
                await socket.send_json({"error": str(e), "ts": int(time.time())})
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return


# ----- new HTML pages -----

HEATMAP_HTML = """
<!doctype html><html><head><meta charset=utf-8><title>heatmaps</title>
<style>:root{color-scheme:dark light;}
body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:20px;max-width:1280px;}
nav a{margin-right:14px;color:#48f;text-decoration:none;}
h2{font-size:14px;margin:24px 0 6px;color:#8aa;text-transform:uppercase;letter-spacing:.04em;}
.grid{display:grid;grid-template-columns:repeat(24,1fr);gap:2px;}
.cell{aspect-ratio:1;background:#222;border-radius:2px;}
.row{display:contents;}.label{font-size:11px;color:#888;grid-column:1/-1;margin-top:4px;}
.dev{border:1px solid #333;border-radius:8px;padding:12px;margin-top:10px;}
.dev h3{margin:0 0 6px;font-size:14px;}
.hour-row{display:grid;grid-template-columns:30px repeat(24,1fr);gap:2px;align-items:center;}
.dowlabel{font-size:11px;color:#888;text-align:right;padding-right:6px;}
.hh{font-size:10px;color:#555;text-align:center;}
</style></head><body>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/heatmaps">Heatmaps</a><a href="/security">Security</a><a href="/discover">Discovered</a></nav>
<h1>Device presence heatmaps</h1>
<p>Darker = more frequent presence at that hour-of-week (last 30 days).</p>
<div id=h>loading…</div>
<script>
function cellColor(v,max){if(!v)return '#1a1a1a';const t=Math.log(v+1)/Math.log(max+1);const r=Math.round(40+200*t),g=Math.round(40+120*t),b=Math.round(140+80*t);return `rgb(${r},${g},${b})`;}
async function load(){
  const d=await(await fetch('/api/heatmap?days=30&top=12')).json();
  const out=d.devices.map(dev=>{
    const flat=dev.grid.flat(),m=Math.max(1,...flat);
    let rows=`<div class=hour-row><div></div>`+Array.from({length:24},(_,i)=>`<div class=hh>${i}</div>`).join('')+'</div>';
    dev.grid.forEach((row,dow)=>{
      rows+=`<div class=hour-row><div class=dowlabel>${dev.labels_dow[dow]}</div>`+row.map(v=>`<div class=cell style="background:${cellColor(v,m)}" title="${v}"></div>`).join('')+'</div>';
    });
    return `<div class=dev><h3>${dev.hostname||'-'} <span style="color:#666;font-size:12px">${dev.mac}</span></h3>${rows}</div>`;
  }).join('');
  document.getElementById('h').innerHTML = out || '<i>no data — let the daemon collect for a day first.</i>';
}
load();
</script></body></html>
"""

SECURITY_HTML = """
<!doctype html><html><head><meta charset=utf-8><title>security</title>
<style>:root{color-scheme:dark light;}
body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:20px;max-width:1280px;}
nav a{margin-right:14px;color:#48f;text-decoration:none;}
.card{border:1px solid #8884;border-radius:8px;padding:14px;margin-top:16px;}
.card h2{margin:0 0 10px;font-size:13px;color:#8aa;text-transform:uppercase;letter-spacing:.04em;}
button{padding:6px 12px;border:1px solid #888;background:transparent;color:inherit;border-radius:4px;cursor:pointer;margin:2px 4px 2px 0;}
button:hover{background:#8882;}
pre{background:#111;padding:10px;border-radius:6px;overflow:auto;max-height:320px;font-size:12px;}
.bad{color:#f77;}.ok{color:#6c9;}
table{border-collapse:collapse;width:100%;font-size:13px;}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #8882;}
</style></head><body>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/heatmaps">Heatmaps</a><a href="/security">Security</a><a href="/discover">Discovered</a></nav>
<h1>Security posture</h1>

<div class=card><h2>Port scan (your public IP)</h2>
<button onclick="pscan()">Run scan</button> <span id=psum></span>
<pre id=pout>click Run scan…</pre></div>

<div class=card><h2>Port scan (every LAN device)</h2>
<button onclick="lscan()">Run LAN scan</button> <span id=lsum></span>
<div id=lout>click Run LAN scan…</div></div>

<div class=card><h2>DNS hijack check</h2>
<button onclick="dnsc()">Run check</button> <span id=dsum></span>
<pre id=dout>click Run check…</pre></div>

<div class=card><h2>ARP table watch</h2>
<button onclick="arpc()">Check now</button>
<pre id=aout>click Check now…</pre></div>

<div class=card><h2>TLS pin (router admin UI)</h2>
<button onclick="tlsc()">Check now</button>
<pre id=tout>click Check now…</pre></div>

<div class=card><h2>CVE check</h2>
<button onclick="cvec()">Query NVD</button>
<pre id=cout>(takes a few seconds)</pre></div>

<div class=card><h2>Anomaly scan</h2>
<button onclick="anoc()">Run</button>
<pre id=anom>click Run…</pre></div>

<script>
async function pscan(){document.getElementById('pout').textContent='scanning…';
  const d=await(await fetch('/api/portscan')).json();
  document.getElementById('psum').innerHTML=d.open?.length?`<span class=bad>${d.open.length} open</span>`:'<span class=ok>all closed</span>';
  document.getElementById('pout').textContent=JSON.stringify(d,null,2);}
async function lscan(){document.getElementById('lout').textContent='scanning LAN (may take ~30s)…';
  const d=await(await fetch('/api/portscan/lan')).json();
  document.getElementById('lsum').innerHTML = d.risky?.length
    ? `<span class=bad>${d.risky.length} host(s) with risky ports</span>`
    : `<span class=ok>scanned ${d.devices.length} hosts, no risky ports</span>`;
  const rows = (d.devices||[]).map(x=>{
    const open = (x.open||[]).join(', ') || '-';
    const cls = (d.risky||[]).some(r=>r.ip===x.ip) ? 'bad' : '';
    return `<tr class=${cls}><td>${x.alias||x.hostname||'-'}</td><td>${x.ip}</td><td>${x.mac||'-'}</td><td>${x.vendor||'-'}</td><td class=mono>${open}</td></tr>`;
  }).join('');
  document.getElementById('lout').innerHTML='<table><tr><th>Name</th><th>IP</th><th>MAC</th><th>Vendor</th><th>Open ports</th></tr>'+rows+'</table>';
}
async function dnsc(){document.getElementById('dout').textContent='checking…';
  const d=await(await fetch('/api/dns-check')).json();
  document.getElementById('dsum').innerHTML=d.hijack_suspected?`<span class=bad>${d.hijack_suspected} suspect</span>`:'<span class=ok>clean</span>';
  document.getElementById('dout').textContent=JSON.stringify(d,null,2);}
async function arpc(){document.getElementById('aout').textContent='checking…';
  const d=await(await fetch('/api/arp')).json();
  document.getElementById('aout').textContent=JSON.stringify(d,null,2);}
async function tlsc(){document.getElementById('tout').textContent='checking…';
  const d=await(await fetch('/api/tls-check')).json();
  document.getElementById('tout').textContent=JSON.stringify(d,null,2);}
async function cvec(){document.getElementById('cout').textContent='querying NVD…';
  const d=await(await fetch('/api/cve')).json();
  document.getElementById('cout').textContent=JSON.stringify(d,null,2);}
async function anoc(){document.getElementById('anom').textContent='scanning…';
  const d=await(await fetch('/api/anomaly')).json();
  document.getElementById('anom').textContent=JSON.stringify(d,null,2);}
</script></body></html>
"""


RULES_HTML = """
<!doctype html><html><head><meta charset=utf-8><title>rules</title>
<style>:root{color-scheme:dark light;}
body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:20px;max-width:1100px;}
nav a{margin-right:14px;color:#48f;text-decoration:none;}
.rule{border:1px solid #8884;border-radius:8px;padding:14px;margin-top:12px;}
textarea{width:100%;min-height:360px;background:#111;color:#ddd;border:1px solid #333;border-radius:6px;padding:10px;font-family:ui-monospace,Consolas,monospace;font-size:12px;}
button{padding:8px 14px;border:1px solid #8884;background:transparent;color:inherit;border-radius:6px;cursor:pointer;margin-right:6px;}
button:hover{background:#8882;}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;background:#8882;font-size:11px;}
input{padding:6px 8px;background:transparent;color:inherit;border:1px solid #8884;border-radius:4px;}
pre{background:#111;padding:10px;border-radius:6px;overflow:auto;}
</style></head><body>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/heatmaps">Heatmaps</a><a href="/security">Security</a><a href="/dns">DNS</a><a href="/flows">Flows</a><a href="/rules">Rules</a><a href="/digest">Digest</a></nav>
<h1>Rules &amp; automation</h1>
<p class=mute>Edit <code>rules.json</code> and <code>automation.json</code> live. Save writes to disk; the daemon picks up new rules on next event dispatch.</p>

<h2>Rules</h2>
<textarea id=rules>loading…</textarea>
<div style="margin-top:8px">
  <button onclick=saveRules()>Save rules</button>
  <button onclick=loadRules()>Reload</button>
  <span class=pill id=rstatus></span>
</div>

<h3>Test console</h3>
<div class=rule>
  <label>Synthetic event (JSON):</label>
  <textarea id=evt style=min-height:120px>{"kind": "device_joined", "mac": "AA:BB:CC:00:00:99", "hostname": "testdev"}</textarea>
  <button onclick=testRules()>Dispatch</button>
  <span class=pill id=testresult></span>
</div>

<h2>Automation</h2>
<textarea id=auto>loading…</textarea>
<div style="margin-top:8px">
  <button onclick=saveAuto()>Save automation</button>
  <button onclick=loadAuto()>Reload</button>
  <span class=pill id=astatus></span>
</div>

<script>
async function loadRules(){
  const d=await(await fetch('/api/rules')).json();
  document.getElementById('rules').value = JSON.stringify(d.rules||[], null, 2);
  document.getElementById('rstatus').textContent = (d.rules||[]).length+' rules';
}
async function saveRules(){
  let rules;
  try{ rules = JSON.parse(document.getElementById('rules').value); }
  catch(e){ document.getElementById('rstatus').textContent = 'JSON error: '+e.message; return; }
  const r=await fetch('/api/rules/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules})});
  const d=await r.json();
  document.getElementById('rstatus').textContent = d.ok?('saved '+d.count+' rules'):'save failed';
}
async function testRules(){
  let evt, rules;
  try{ evt = JSON.parse(document.getElementById('evt').value); }
  catch(e){ document.getElementById('testresult').textContent='bad event JSON'; return; }
  try{ rules = JSON.parse(document.getElementById('rules').value); }
  catch(e){ rules = undefined; }
  const r=await fetch('/api/rules/test',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event:evt, rules})});
  const d=await r.json();
  document.getElementById('testresult').textContent = d.fired+' action(s) fired';
}
async function loadAuto(){
  const d=await(await fetch('/api/automation')).json();
  document.getElementById('auto').value = JSON.stringify(d.jobs||[], null, 2);
  document.getElementById('astatus').textContent = (d.jobs||[]).length+' jobs';
}
async function saveAuto(){
  let jobs;
  try{ jobs = JSON.parse(document.getElementById('auto').value); }
  catch(e){ document.getElementById('astatus').textContent='JSON error: '+e.message; return; }
  const r=await fetch('/api/automation/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jobs})});
  const d=await r.json();
  document.getElementById('astatus').textContent = d.ok?('saved '+d.count+' jobs'):'save failed';
}
loadRules(); loadAuto();
</script></body></html>
"""

DNS_HTML = """
<!doctype html><html><head><meta charset=utf-8><title>DNS</title>
<style>:root{color-scheme:dark light;}
body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:20px;max-width:1200px;}
nav a{margin-right:14px;color:#48f;text-decoration:none;}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;}
@media(max-width:900px){.grid{grid-template-columns:1fr;}}
.card{border:1px solid #8884;border-radius:8px;padding:14px;}
.card h2{margin:0 0 8px;font-size:13px;color:#8aa;text-transform:uppercase;letter-spacing:.04em;}
table{border-collapse:collapse;width:100%;font-size:13px;}th,td{padding:4px 6px;text-align:left;border-bottom:1px solid #8882;}
.big{font-size:28px;font-weight:600;}
.mute{color:#888;}button{padding:6px 12px;border:1px solid #8884;background:transparent;color:inherit;border-radius:6px;cursor:pointer;}
</style></head><body>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/heatmaps">Heatmaps</a><a href="/security">Security</a><a href="/dns">DNS</a><a href="/flows">Flows</a><a href="/rules">Rules</a></nav>
<h1>DNS filter stats</h1>
<p class=mute>Queries logged when you run <code>c6u dns run</code> and point your router's DNS at this machine. <button onclick=updateList()>Update blocklist</button> <span id=listmsg></span></p>
<div class=grid>
  <div class=card><h2>Total</h2><div class=big id=total>-</div><div class=mute>queries (last 24h)</div></div>
  <div class=card><h2>Blocked</h2><div class=big id=blocked>-</div><div class=mute id=blockpct>-</div></div>
  <div class=card><h2>Uniques</h2><div class=big id=uniq>-</div><div class=mute>top domains below</div></div>
</div>
<div class=grid style=margin-top:16px>
  <div class=card><h2>Top domains</h2><table id=tdom></table></div>
  <div class=card><h2>Top blocked</h2><table id=tblk></table></div>
  <div class=card><h2>Top clients</h2><table id=tcli></table></div>
</div>
<script>
async function load(){
  const d=await(await fetch('/api/dns/stats?days=1')).json();
  document.getElementById('total').textContent = d.total.toLocaleString();
  document.getElementById('blocked').textContent = d.blocked.toLocaleString();
  document.getElementById('blockpct').textContent = d.block_pct.toFixed(1)+'% blocked';
  document.getElementById('uniq').textContent = (d.top_domains||[]).length;
  document.getElementById('tdom').innerHTML = (d.top_domains||[]).map(r=>`<tr><td>${r.qname}</td><td>${r.n}</td></tr>`).join('') || '<tr><td class=mute>no data yet</td></tr>';
  document.getElementById('tblk').innerHTML = (d.top_blocked||[]).map(r=>`<tr><td>${r.qname}</td><td>${r.n}</td></tr>`).join('') || '<tr><td class=mute>no blocks</td></tr>';
  document.getElementById('tcli').innerHTML = (d.top_clients||[]).map(r=>`<tr><td>${r.client_ip} ${r.client_mac||''}</td><td>${r.n}</td></tr>`).join('') || '<tr><td class=mute>no clients</td></tr>';
}
async function updateList(){document.getElementById('listmsg').textContent='updating…';
  const d=await(await fetch('/api/dns/blocklist/update',{method:'POST'})).json();
  document.getElementById('listmsg').textContent = 'loaded '+d.total+' domains';
}
load(); setInterval(load, 15000);
</script></body></html>
"""

FLOWS_HTML = """
<!doctype html><html><head><meta charset=utf-8><title>flows</title>
<style>:root{color-scheme:dark light;}
body{font:14px/1.4 system-ui,sans-serif;margin:0;padding:20px;max-width:1200px;}
nav a{margin-right:14px;color:#48f;text-decoration:none;}
.card{border:1px solid #8884;border-radius:8px;padding:14px;margin-top:16px;}
.card h2{margin:0 0 8px;font-size:13px;color:#8aa;text-transform:uppercase;letter-spacing:.04em;}
table{border-collapse:collapse;width:100%;font-size:13px;}th,td{padding:4px 6px;text-align:left;border-bottom:1px solid #8882;}
.mono{font-family:ui-monospace,Consolas,monospace;}
</style></head><body>
<nav><a href="/">Live</a><a href="/history">History</a><a href="/heatmaps">Heatmaps</a><a href="/security">Security</a><a href="/dns">DNS</a><a href="/flows">Flows</a><a href="/rules">Rules</a></nav>
<h1>NetFlow top talkers</h1>
<p class=mute>Populated when a switch/router exports flow records to <code>c6u netflow run</code> (UDP port 2055).</p>
<div class=card><h2>Top flows by bytes (24h)</h2><table id=ttop></table></div>
<div class=card><h2>Top source IPs by total bytes (24h)</h2><table id=tsrc></table></div>
<script>
function fmt(b){if(!b)return '-';const u=['B','KB','MB','GB','TB'];let i=0,v=+b;while(v>=1024&&i<u.length-1){v/=1024;i++;}return v.toFixed(1)+' '+u[i];}
async function load(){
  const d=await(await fetch('/api/flows/top?days=1&limit=30')).json();
  document.getElementById('ttop').innerHTML = '<tr><th>Src</th><th>Dst</th><th>Proto</th><th>Dst port</th><th>Bytes</th><th>Packets</th></tr>'+
    (d.flows||[]).map(r=>`<tr><td class=mono>${r.src_ip}</td><td class=mono>${r.dst_ip}</td><td>${r.protocol}</td><td>${r.dst_port}</td><td>${fmt(r.tot_bytes)}</td><td>${r.tot_packets}</td></tr>`).join('') || '<tr><td>no flows yet</td></tr>';
  document.getElementById('tsrc').innerHTML = '<tr><th>Source IP</th><th>Bytes</th><th>Packets</th><th>Unique peers</th></tr>'+
    (d.sources||[]).map(r=>`<tr><td class=mono>${r.src_ip}</td><td>${fmt(r.tot_bytes)}</td><td>${r.tot_packets}</td><td>${r.uniq_peers}</td></tr>`).join('') || '<tr><td>no flows</td></tr>';
}
load();
</script></body></html>
"""


@app.get("/heatmaps", response_class=HTMLResponse)
def heatmap_page(): return HTMLResponse(HEATMAP_HTML)


@app.get("/rules", response_class=HTMLResponse)
def rules_page(): return HTMLResponse(RULES_HTML)


@app.get("/dns", response_class=HTMLResponse)
def dns_page(): return HTMLResponse(DNS_HTML)


@app.get("/flows", response_class=HTMLResponse)
def flows_page(): return HTMLResponse(FLOWS_HTML)


@app.get("/security", response_class=HTMLResponse)
def security_page(): return HTMLResponse(SECURITY_HTML)


@app.get("/digest", response_class=HTMLResponse)
def digest_page(days: int = 7):
    from . import digest as digest_mod
    return HTMLResponse(digest_mod.build(days=days))


def serve(host: str = "127.0.0.1", port: int = 8000, ssl: bool = False) -> None:
    import uvicorn
    try:
        from . import plugins
        plugins.register_web(app)
    except Exception:
        pass
    kwargs = {"host": host, "port": port, "log_level": "info"}
    if ssl:
        from . import acme
        active = acme.active_cert()
        if not active:
            raise RuntimeError("ssl=True but no cert in certs/; run `c6u acme issue` first")
        kwargs["ssl_certfile"] = active["cert"]
        kwargs["ssl_keyfile"] = active["key"]
    uvicorn.run(app, **kwargs)
