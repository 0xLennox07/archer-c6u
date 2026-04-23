"""Round-3 feature tests: DNS parsing, NetFlow parsing, notifier cooldown,
retention sweep, audit hash chain, WireGuard config, fake router, plugin system."""
import struct
import time

from c6u import (audit, db, dnsfilter, fakerouter, netflow, notifier, plugins,
                 retention, rules as rules_mod, vpn)


# ---------- DNS ----------

def test_dns_blockset_subdomain_match():
    blockset = {"ads.badsite.com", "tracker.net"}
    assert dnsfilter._check_blocked("foo.ads.badsite.com", blockset)
    assert dnsfilter._check_blocked("deep.sub.tracker.net", blockset)
    assert not dnsfilter._check_blocked("good.example.com", blockset)
    assert dnsfilter._check_blocked("tracker.net", blockset)


def test_dns_parse_hosts_line():
    assert dnsfilter._parse_hosts_line("0.0.0.0 bad.domain.test") == "bad.domain.test"
    assert dnsfilter._parse_hosts_line("# comment") is None
    assert dnsfilter._parse_hosts_line("127.0.0.1 localhost") is None
    assert dnsfilter._parse_hosts_line("   ") is None


# ---------- NetFlow ----------

def test_netflow_v5_parse():
    header = struct.pack("!HH", 5, 1) + b"\0" * 20
    # src 10.0.0.1 → dst 8.8.8.8, 100 bytes, 1 packet, prot 17 (UDP), src 12345 dst 53
    record = struct.pack("!4s4s4sHHIIIIHHBBBBHHBBH",
        bytes([10, 0, 0, 1]), bytes([8, 8, 8, 8]), b"\0\0\0\0",
        0, 0,
        1, 100,
        0, 1000,
        12345, 53,
        0, 0, 17, 0,
        0, 0, 0, 0, 0)
    rows = netflow.parse_v5(header + record, exporter_ip="192.168.0.1")
    assert len(rows) == 1
    r = rows[0]
    assert r["src_ip"] == "10.0.0.1"
    assert r["dst_ip"] == "8.8.8.8"
    assert r["bytes"] == 100
    assert r["protocol"] == 17
    assert r["dst_port"] == 53


# ---------- Notifier ----------

def test_notifier_cooldown(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "n.sqlite3")
    # Minimal config so load_config succeeds inside the module.
    from c6u import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", tmp_path / "cfg.json")
    (tmp_path / "cfg.json").write_text('{"host":"x","username":"u","password":"p"}')
    assert notifier.should_send("device_joined", "AA", cooldown_s=60)
    assert not notifier.should_send("device_joined", "AA", cooldown_s=60)   # cooldown active
    assert notifier.should_send("device_joined", "BB", cooldown_s=60)       # different key


# ---------- Retention ----------

def test_retention_sweep(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r.sqlite3")
    from c6u import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", tmp_path / "cfg.json")
    (tmp_path / "cfg.json").write_text(
        '{"host":"x","username":"u","password":"p",'
        '"retention":{"device_sample_days":1,"vacuum_on_sweep":false}}'
    )
    now = int(time.time())
    old = now - 3 * 86400  # 3 days old, outside 1-day retention
    with db.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO device_sample VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (old, "AA", "h", "10.0.0.1", "wifi", 0, 0, 0, 0, 1))
        conn.execute("INSERT OR REPLACE INTO device_sample VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (now, "BB", "h", "10.0.0.2", "wifi", 0, 0, 0, 0, 1))
    r = retention.sweep()
    assert r["deleted"].get("device_sample") == 1
    with db.connect() as conn:
        remaining = conn.execute("SELECT COUNT(*) FROM device_sample").fetchone()[0]
    assert remaining == 1


# ---------- Audit ----------

def test_audit_seal_and_verify(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "a.sqlite3")
    # Seed a handful of events.
    for i in range(3):
        db.record_event("device_joined", mac=f"AA:BB:CC:00:00:{i:02d}", payload="hi")
    r = audit.seal()
    assert r["sealed"] == 3
    v = audit.verify()
    assert v["ok"], v
    # Tamper by editing a payload.
    with db.connect() as conn:
        conn.execute("UPDATE event SET payload = 'TAMPERED' WHERE rowid = 1")
    v2 = audit.verify()
    assert not v2["ok"]


# ---------- WireGuard config ----------

def test_wg_gen_keypair_pure_python():
    priv, pub = vpn._gen_keypair_pycrypto()
    import base64
    assert len(base64.b64decode(priv)) == 32
    assert len(base64.b64decode(pub)) == 32
    assert priv != pub


def test_wg_provision(tmp_path, monkeypatch):
    from c6u import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "ROOT", tmp_path)
    r = vpn.provision(out_dir=tmp_path / "wg", peer_names=["phone"],
                       network="10.99.99.0/24", listen_port=51820,
                       endpoint="203.0.113.10:51820")
    assert (tmp_path / "wg" / "wg0.conf").exists()
    assert (tmp_path / "wg" / "phone.conf").exists()
    assert r["peers"][0]["address"].startswith("10.99.99.")


# ---------- Fake router ----------

def test_fake_router_status():
    fr = fakerouter.FakeRouter()
    fr.authorize()
    s = fr.get_status()
    assert s.clients_total == len(fakerouter.FIXTURE_DEVICES)
    assert len(s.devices) == s.clients_total


# ---------- Plugin discovery ----------

def test_plugin_discovery():
    found = plugins.discover()
    # plugins/example_hello.py should be picked up.
    assert any(p.name == "example_hello.py" for p in found)
    info = plugins.info()
    assert any(p["file"] == "example_hello.py" and "register_cli" in p["hooks"] for p in info)


# ---------- Rules: plugin actions still wire in ----------

def test_rules_ignores_unknown_action_cleanly(tmp_path, monkeypatch):
    from c6u import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", tmp_path / "cfg.json")
    (tmp_path / "cfg.json").write_text('{"host":"x","username":"u","password":"p"}')
    rs = [{"when": {"kind": "e"}, "then": [{"nonexistent_action": {}}]}]
    fired = rules_mod.dispatch({"kind": "e"}, cfg={"host":"x"}, rules=rs)
    assert fired == 0  # unknown actions are logged & skipped, not crashed on
