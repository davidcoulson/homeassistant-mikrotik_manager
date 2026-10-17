"""Read-only RouterOS update status per device (updates are applied in the manager)."""
from __future__ import annotations

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import router_device_info


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[int] = set()

    def _add_new() -> None:
        new = [d["id"] for d in coordinator.data["devices"] if d["id"] not in known]
        known.update(new)
        async_add_entities(RouterOsUpdate(coordinator, entry, did) for did in new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class RouterOsUpdate(CoordinatorEntity, UpdateEntity):
    """No install support: updates go through the manager so backups and Change Guard apply."""

    _attr_has_entity_name = True
    # Must be an UpdateEntityFeature flag, not a bare int: HA does `FLAG in supported_features`
    # when registering the entity, and a plain 0 raised TypeError so no entity was ever added.
    _attr_supported_features = UpdateEntityFeature(0)

    def __init__(self, coordinator, entry, device_id):
        super().__init__(coordinator)
        self._id = device_id
        self._attr_unique_id = f"{entry.entry_id}_device_{device_id}_ros_update"
        self._attr_name = "RouterOS"
        self._attr_device_info = router_device_info(entry, coordinator, device_id)

    @property
    def _device(self):
        return next((d for d in self.coordinator.data["devices"] if d["id"] == self._id), None)

    @property
    def available(self) -> bool:
        return super().available and self._device is not None

    @property
    def installed_version(self):
        d = self._device
        return None if d is None else d.get("ros_version")

    @property
    def latest_version(self):
        d = self._device
        if d is None:
            return None
        # null latest means nothing newer is known: report installed == latest.
        return d.get("latest_ros_version") or d.get("ros_version")

    @property
    def extra_state_attributes(self):
        d = self._device or {}
        return {
            "firmware_update_available": bool(d.get("firmware_update_available")),
            "routerboard_upgrade_available": bool(d.get("routerboard_upgrade_available")),
            "routerboard_upgrade_version": d.get("upgrade_firmware_version"),
        }
