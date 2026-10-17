"""Fleet-level sensors from /api/metrics/summary."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfPower
from homeassistant.helpers.device_registry import DeviceInfo
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

    known: set[tuple[int, str]] = set()

    def _add_poe() -> None:
        new = [
            (did, port)
            for did, det in coordinator.data["detail"].items()
            for port in det["poe"] if (did, port) not in known
        ]
        known.update(new)
        async_add_entities(PoePower(coordinator, entry, did, port) for did, port in new)

    _add_poe()
    entry.async_on_unload(coordinator.async_add_listener(_add_poe))


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


class PoePower(CoordinatorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, device_id, port):
        super().__init__(coordinator)
        self._id, self._port = device_id, port
        self._attr_unique_id = f"{entry.entry_id}_device_{device_id}_{port}_poe"
        self._attr_name = f"{port} PoE power"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, f"{entry.entry_id}_{device_id}")})

    @property
    def _row(self):
        det = self.coordinator.data["detail"].get(self._id)
        return det["poe"].get(self._port) if det else None

    @property
    def available(self) -> bool:
        return super().available and self._row is not None

    @property
    def native_value(self):
        return None if self._row is None else self._row.get("watts")

    @property
    def extra_state_attributes(self):
        r = self._row or {}
        return {"current_ma": r.get("current_ma"), "voltage_v": r.get("voltage_v")}
