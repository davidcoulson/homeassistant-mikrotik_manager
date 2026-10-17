"""Per-device reachability from /api/devices."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[int] = set()

    def _add_new() -> None:
        new = [d for d in coordinator.data["devices"] if d["id"] not in known]
        known.update(d["id"] for d in new)
        async_add_entities(DeviceOnline(coordinator, entry, d["id"]) for d in new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class DeviceOnline(CoordinatorEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry, device_id):
        super().__init__(coordinator)
        self._id = device_id
        self._attr_unique_id = f"{entry.entry_id}_device_{device_id}_online"
        d = self._device or {}
        self._attr_name = "Online"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{device_id}")},
            name=d.get("name"), model=d.get("model"),
            sw_version=d.get("ros_version"), serial_number=d.get("serial_number"),
            configuration_url=entry.data["url"],
        )

    @property
    def _device(self):
        return next((d for d in self.coordinator.data["devices"] if d["id"] == self._id), None)

    @property
    def available(self) -> bool:
        return super().available and self._device is not None

    @property
    def is_on(self):
        d = self._device
        return None if d is None else d.get("status") == "online"
