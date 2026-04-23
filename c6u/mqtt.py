"""MQTT publisher with Home Assistant auto-discovery.

Set in config.json:
  "mqtt": {
    "host": "192.168.0.50",
    "port": 1883,
    "username": "...",
    "password": "...",
    "discovery_prefix": "homeassistant",
    "device_id": "c6u_router"
  }
"""
from __future__ import annotations

import json
import logging
import time

log = logging.getLogger(__name__)


def _client(cfg: dict):
    import paho.mqtt.client as mqtt
    c = mqtt.Client(client_id=cfg.get("device_id", "c6u_router"), clean_session=True)
    if cfg.get("username"):
        c.username_pw_set(cfg["username"], cfg.get("password"))
    c.connect(cfg.get("host", "127.0.0.1"), cfg.get("port", 1883), keepalive=30)
    return c


def publish_discovery(cfg: dict) -> None:
    """Publish HA discovery messages so sensors auto-appear in Home Assistant."""
    prefix = cfg.get("discovery_prefix", "homeassistant")
    dev_id = cfg.get("device_id", "c6u_router")
    base = f"c6u/{dev_id}"
    device_block = {"identifiers": [dev_id], "name": "TP-Link C6U", "manufacturer": "TP-Link", "model": "Archer C6U"}

    sensors = [
        ("clients", "Clients", "mdi:lan-connect", None, "{{ value_json.clients_total }}"),
        ("cpu", "CPU", "mdi:cpu-32-bit", "%", "{{ (value_json.cpu_usage * 100) | round(0) }}"),
        ("mem", "Memory", "mdi:memory", "%", "{{ (value_json.mem_usage * 100) | round(0) }}"),
        ("wired", "Wired clients", "mdi:ethernet", None, "{{ value_json.wired_total }}"),
        ("wifi", "WiFi clients", "mdi:wifi", None, "{{ value_json.wifi_clients_total }}"),
        ("public_ip", "Public IP", "mdi:earth", None, "{{ value_json.public_ip }}"),
    ]

    c = _client(cfg)
    try:
        for key, name, icon, unit, tpl in sensors:
            cfg_topic = f"{prefix}/sensor/{dev_id}/{key}/config"
            payload = {
                "name": name,
                "unique_id": f"{dev_id}_{key}",
                "state_topic": f"{base}/state",
                "value_template": tpl,
                "icon": icon,
                "device": device_block,
            }
            if unit:
                payload["unit_of_measurement"] = unit
            c.publish(cfg_topic, json.dumps(payload), retain=True)
    finally:
        c.disconnect()


def publish_state(cfg: dict, status, public_ip: str | None = None) -> None:
    dev_id = cfg.get("device_id", "c6u_router")
    state = {
        "ts": int(time.time()),
        "clients_total": status.clients_total,
        "wired_total": status.wired_total,
        "wifi_clients_total": status.wifi_clients_total,
        "guest_clients_total": status.guest_clients_total,
        "cpu_usage": status.cpu_usage,
        "mem_usage": status.mem_usage,
        "wan_ipv4": str(status.wan_ipv4_address) if status.wan_ipv4_address else None,
        "wan_uptime": status.wan_ipv4_uptime,
        "public_ip": public_ip,
    }
    c = _client(cfg)
    try:
        c.publish(f"c6u/{dev_id}/state", json.dumps(state), retain=True)
    finally:
        c.disconnect()
