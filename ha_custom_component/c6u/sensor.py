"""Sensors — six gauges pulled from the coordinator."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN

ENTITIES = (
    ("cpu",     "c6u CPU",     PERCENTAGE, lambda v: round(v * 100, 1) if v is not None else None),
    ("mem",     "c6u Memory",  PERCENTAGE, lambda v: round(v * 100, 1) if v is not None else None),
    ("clients", "c6u Clients", None,       lambda v: v),
    ("wired",   "c6u Wired",   None,       lambda v: v),
    ("wifi",    "c6u WiFi",    None,       lambda v: v),
    ("guest",   "c6u Guest",   None,       lambda v: v),
    ("wan_ip",  "c6u WAN IP",  None,       lambda v: v),
    ("uptime",  "c6u Uptime",  "s",        lambda v: v),
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    coord = hass.data[DOMAIN]
    ents = [C6USensor(coord, key, name, unit, transform) for key, name, unit, transform in ENTITIES]
    async_add_entities(ents)


class C6USensor(CoordinatorEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coord, key, name, unit, transform):
        super().__init__(coord)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"c6u_{key}"
        self._attr_native_unit_of_measurement = unit
        self._transform = transform

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return self._transform(data.get(self._key))
