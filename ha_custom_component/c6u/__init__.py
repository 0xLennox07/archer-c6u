"""TP-Link Archer C6U — Home Assistant custom component.

Copy this folder into config/custom_components/c6u/ in your HA installation, then
add to configuration.yaml:

    c6u:
      host: http://192.168.0.1
      username: admin
      password: !secret c6u_password

    sensor:
      - platform: c6u
"""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

DOMAIN = "c6u"
_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=60)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    if DOMAIN not in config:
        return True
    cfg = config[DOMAIN]
    coordinator = C6UCoordinator(hass, cfg[CONF_HOST], cfg[CONF_USERNAME], cfg[CONF_PASSWORD])
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN] = coordinator
    return True


class C6UCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host, user, pw):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.host, self.user, self.pw = host, user, pw

    async def _async_update_data(self):
        return await self.hass.async_add_executor_job(self._sync_fetch)

    def _sync_fetch(self):
        from tplinkrouterc6u import TplinkRouter
        r = TplinkRouter(self.host, self.pw, username=self.user)
        r.authorize()
        try:
            s = r.get_status()
            return {
                "cpu": s.cpu_usage, "mem": s.mem_usage,
                "clients": s.clients_total,
                "wired": s.wired_total,
                "wifi": s.wifi_clients_total,
                "guest": s.guest_clients_total,
                "wan_ip": str(s.wan_ipv4_address) if s.wan_ipv4_address else None,
                "uptime": s.wan_ipv4_uptime,
            }
        finally:
            try:
                r.logout()
            except Exception:
                pass
