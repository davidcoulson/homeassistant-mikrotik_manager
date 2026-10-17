# MikroTik Manager for Home Assistant

Reads fleet data from [mikrotik-manager](https://github.com/2GT-Media-Group-LLC/mikrotik-manager) with one read-scope API token, instead of polling every router and switch.

Provides fleet sensors (devices online/total, active clients, 24h errors/warnings, 30-day uptime), a per-device Online sensor, a link sensor per physical port (admin-disabled shown as an attribute) and PoE watts per port.

Also provided (v0.2.0):

- A read-only **RouterOS update** entity per device (installed vs latest version; RouterBOOT upgrade state in attributes). Installing is deliberately not supported: update in the manager so backups and Change Guard apply.
- **Repairs** issues, raised and cleared on each refresh: device offline, RouterBOOT upgrade pending, RouterOS update available, and one fleet issue while the 24h error count is above zero.
- Optional **throughput sensors** (rx/tx bit rate per physical port). None are created by default; choose ports, or all physical ports, under Configure. They need a manager version with `/api/metrics/interfaces/latest` (tracking issue: https://github.com/2GT-Media-Group-LLC/mikrotik-manager/issues/298); on older managers they stay unavailable and nothing breaks. Rates are computed between successive polls from the byte counters, so the first value appears after the second poll.

Also provided (v0.3.0):

- **CPU load** and **Memory usage** (%) sensors per device, from `/api/metrics/resources/latest`. Only devices present in the response get them; on older managers the endpoint 404s and the sensors are simply not created.
- **Entity naming** now follows the Home Assistant pattern (`has_entity_name`): every entity is attached to its device and has a short name, so ids look like `sensor.djc_sw_r02_ether10_poe_power` and `binary_sensor.djc_sw_r02_online`. Fleet sensors live on a "MikroTik Manager" device. Unique ids are unchanged, so existing entities keep their old entity_ids; to get the new ids, remove and re-add the integration, or rename the entities.
- **Fix:** the RouterOS update entities were never created (an integer `supported_features` made Home Assistant raise while adding them). There is now one `RouterOS` update entity per device.

Planned: webhook-driven events.
