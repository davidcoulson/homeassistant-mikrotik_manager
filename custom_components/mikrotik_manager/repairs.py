"""Repairs issues derived from each coordinator refresh (informational, not fixable)."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN
from .logic import high_findings


def _wanted(entry_id: str, data: dict) -> dict[str, tuple[str, ir.IssueSeverity, dict]]:
    """issue_id -> (translation_key, severity, placeholders) for current conditions."""
    out: dict[str, tuple[str, ir.IssueSeverity, dict]] = {}
    for d in data["devices"]:
        name = d.get("name") or f"device {d['id']}"
        base = f"{entry_id}_device_{d['id']}"
        if d.get("status") != "online":
            out[f"{base}_offline"] = ("device_offline", ir.IssueSeverity.WARNING, {"name": name})
        if d.get("routerboard_upgrade_available"):
            out[f"{base}_routerboot"] = (
                "routerboot_upgrade", ir.IssueSeverity.WARNING,
                {"name": name, "version": d.get("upgrade_firmware_version") or "unknown"},
            )
        if d.get("firmware_update_available"):
            out[f"{base}_ros_update"] = (
                "ros_update", ir.IssueSeverity.WARNING,
                {"name": name, "installed": d.get("ros_version") or "unknown",
                 "latest": d.get("latest_ros_version") or "unknown"},
            )
    names = {d["id"]: d.get("name") or f"device {d['id']}" for d in data["devices"]}
    for did, parsed in (data.get("config_health") or {}).items():
        for f in high_findings(parsed):
            out[f"{entry_id}_device_{did}_config_{f['rule']}"] = (
                "config_health_finding", ir.IssueSeverity.ERROR,
                {"name": names.get(did, f"device {did}"),
                 "title": f.get("title") or f["rule"],
                 "detail": f.get("detail") or "See the device's Config health in MikroTik Manager."},
            )
    alerts = (data.get("summary") or {}).get("alerts") or {}
    errors = alerts.get("critical") or 0
    if isinstance(errors, (int, float)) and errors > 0:
        out[f"{entry_id}_fleet_errors"] = (
            "fleet_errors", ir.IssueSeverity.ERROR, {"count": str(int(errors))}
        )
    return out


def sync_issues(hass: HomeAssistant, entry_id: str, data: dict, current: set[str]) -> None:
    """Create/refresh wanted issues and delete ones no longer true. Mutates `current`."""
    wanted = _wanted(entry_id, data)
    for issue_id, (key, severity, placeholders) in wanted.items():
        ir.async_create_issue(
            hass, DOMAIN, issue_id, is_fixable=False, severity=severity,
            translation_key=key, translation_placeholders=placeholders,
        )
    for issue_id in current - wanted.keys():
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    current.clear()
    current.update(wanted)


def clear_issues(hass: HomeAssistant, current: set[str]) -> None:
    for issue_id in current:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    current.clear()
