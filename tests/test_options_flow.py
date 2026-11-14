"""Options flow keeps what the form cannot offer. Needs pytest-homeassistant-custom-component."""
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[1]))
from custom_components.mikrotik_manager.const import DOMAIN  # noqa: E402


async def test_options_keep_site_and_offline_ports(hass, enable_custom_integrations):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"site_id": "2", "throughput_ports": ["1/ether1"]})
    entry.add_to_hass(hass)

    async def no_sites():
        raise RuntimeError

    # Device 1 is offline: not in `detail`, and /api/sites fails.
    hass.data[DOMAIN] = {entry.entry_id: SimpleNamespace(
        client=SimpleNamespace(sites=no_sites), data={"devices": [{"id": 1}], "detail": {}})}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"throughput_ports": ["1/ether1"]})
    assert result["data"]["site_id"] == "2"
    assert result["data"]["throughput_ports"] == ["1/ether1"]
