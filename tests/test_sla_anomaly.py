"""SLA percentile calculation + anomaly z-score scan."""
import time

from c6u import db, sla, anomaly, config as cfg_mod


def test_sla_percentiles(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "s.sqlite3")
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", tmp_path / "cfg.json")
    (tmp_path / "cfg.json").write_text(
        '{"host":"http://x","username":"u","password":"p",'
        '"isp":{"down_mbps":100,"up_mbps":20,"provider":"x"}}'
    )
    now = int(time.time())
    with db.connect() as conn:
        for i, v in enumerate((50, 90, 95, 100, 100, 100, 105, 110)):
            conn.execute(
                "INSERT OR REPLACE INTO speedtest VALUES (?,?,?,?,?,?,?,?)",
                (now - i * 60, float(v), 20.0, 10.0, "srv", 0.1, 0.1, 5),
            )
    rpt = sla.report(days=1)
    assert rpt["samples"] == 8
    assert rpt["down_mbps"]["mean"] > 80
    assert 0 <= rpt["down_sla_met_percent"] <= 100


def test_anomaly_no_data(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "a.sqlite3")
    # Empty DB — should return no anomalies without errors.
    out = anomaly.scan(baseline_days=14, recent_minutes=60)
    assert out == []
