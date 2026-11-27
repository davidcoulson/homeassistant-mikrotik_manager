"""mikrotik_manager.reload_code: unload, re-import the modules from disk, set up again."""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1]))
from custom_components.mikrotik_manager import _CODE_VERSION, _clear_marketplace_restart  # noqa: E402
from custom_components.mikrotik_manager.const import DOMAIN
from homeassistant.helpers import issue_registry as ir  # noqa: E402

PACKAGE = "custom_components.mikrotik_manager"


async def test_reload_code_replaces_the_modules(hass, aioclient_mock, enable_custom_integrations):
    base = "http://manager.test"
    aioclient_mock.get(f"{base}/api/devices", json=[])
    aioclient_mock.get(f"{base}/api/metrics/summary", json={})
    entry = MockConfigEntry(domain=DOMAIN, data={"url": base, "token": "t"}, options={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    old = {n: m for n, m in sys.modules.items() if n.startswith(PACKAGE)}

    await hass.services.async_call(DOMAIN, "reload_code", {}, blocking=True)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert sys.modules[PACKAGE] is not old[PACKAGE]
    assert hass.services.has_service(DOMAIN, "reload_code")
    assert list(hass.data[DOMAIN]) == [entry.entry_id]


async def test_reload_clears_only_the_running_versions_restart_repair(hass, monkeypatch) -> None:
    monkeypatch.setitem(_clear_marketplace_restart.__globals__, "_CODE_VERSION", "1.2.3")
    for domain, issue_id, issue_domain in (
        ("marketplace", "restart_required_1_tags/1.2.3", DOMAIN),
        ("marketplace", "restart_required_2_tags/v1.2.3", DOMAIN),
        ("marketplace", "restart_required_3_tags/1.2.4", DOMAIN),
        ("marketplace", "restart_required_4_tags/1.2.3", "ssh"),
        ("marketplace", "critical_x", DOMAIN),
        (DOMAIN, "restart_required_x", DOMAIN),
    ):
        ir.async_create_issue(
            hass, domain, issue_id, is_fixable=False, issue_domain=issue_domain,
            severity=ir.IssueSeverity.WARNING, translation_key="x",
        )
    _clear_marketplace_restart(hass)
    assert set(ir.async_get(hass).issues) == {
        ("marketplace", "restart_required_3_tags/1.2.4"),
        ("marketplace", "restart_required_4_tags/1.2.3"),
        ("marketplace", "critical_x"),
        (DOMAIN, "restart_required_x"),
    }


def test_code_version_is_the_manifest_version() -> None:
    manifest = Path(__file__).parents[1] / "custom_components" / "mikrotik_manager" / "manifest.json"
    assert _CODE_VERSION == json.loads(manifest.read_text())["version"]
