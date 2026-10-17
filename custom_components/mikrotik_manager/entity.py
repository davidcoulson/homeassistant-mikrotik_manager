"""Shared device-info helpers so every platform attaches entities to the same devices."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def router_device_info(entry, coordinator, device_id: int) -> DeviceInfo:
    """DeviceInfo for one managed router/switch (full details so the name is always set)."""
    d = next((x for x in coordinator.data["devices"] if x["id"] == device_id), None) or {}
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{device_id}")},
        name=d.get("name") or f"Device {device_id}",
        model=d.get("model"),
        sw_version=d.get("ros_version"),
        serial_number=d.get("serial_number"),
        configuration_url=entry.data.get("url"),
    )


def fleet_device_info(entry) -> DeviceInfo:
    """DeviceInfo for the manager itself, home of the fleet-level sensors."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="MikroTik Manager",
        manufacturer="MikroTik Manager",
        configuration_url=entry.data.get("url"),
    )

