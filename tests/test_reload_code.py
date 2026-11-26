"""mikrotik_manager.reload_code: unload, re-import the modules from disk, set up again."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
from homeassistant.config_entries import ConfigEntryState  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1]))
from custom_components.mikrotik_manager.const import DOMAIN  # noqa: E402

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
