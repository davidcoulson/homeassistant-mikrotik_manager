"""Fleet-level sensors from /api/metrics/summary."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

# (key, name, path into the summary payload)
FLEET_SENSORS = [
    ("devices_online", "Devices online", ("devices", "online")),
    ("devices_total", "Devices total", ("devices", "total")),
    ("clients_active", "Active clients", ("clients", "active")),
    ("alerts_errors_24h", "Errors (24h)", ("alerts", "critical")),
    ("alerts_warnings_24h", "Warnings (24h)", ("alerts", "warning")),
    ("fleet_uptime_30d", "Fleet uptime (30d)", ("availability", "fleetUptimePct30d")),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(FleetSensor(coordinator, entry, *s) for s in FLEET_SENSORS)


class FleetSensor(CoordinatorEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, key, name, path):
        super().__init__(coordinator)
        self._path = path
        self._attr_name = f"MikroTik Manager {name}"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        if key == "fleet_uptime_30d":
            self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self):
        node = self.coordinator.data["summary"]
        for part in self._path:
            node = node.get(part) if isinstance(node, dict) else None
        return node
