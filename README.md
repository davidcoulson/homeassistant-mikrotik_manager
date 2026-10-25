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

Also provided (v0.4.0):

- **Config health.** A "Config findings" sensor per online device counts the open findings from the manager's standing audit (`/api/devices/:id/config-health`), with the findings (rule, severity, title, detail, objects; capped at 20) as attributes. Critical findings raise a Repairs issue that clears when the finding is resolved. The audit is cached by the manager, and the integration re-reads it every fifth refresh.
- **Needs attention.** A fleet sensor counting the items on the manager's attention list (`/api/operations/insights`), with the first 20 as attributes. If the endpoint returns 404 or 403 the sensor stays unavailable and nothing else breaks.
- **Webhook push.** Each config entry registers a Home Assistant webhook. Offline/online events trigger an immediate refresh, and every event (known or not) fires `mikrotik_manager_event` on the HA bus with `event`, `device_id`, `device_name`, `severity`, `message`, `details`, `timestamp` and `entry_id`.
- **Site selector.** If the manager has more than one site, the setup flow asks which to follow (or all). The choice is sent as `X-Site-Id` on every request and can be changed under Configure, which reloads the integration. Existing setups keep following all sites.

### Webhook setup

1. In Home Assistant open the integration, choose Configure, and copy the webhook URL shown.
2. In the manager go to Settings, Alerting, Outbound webhooks, add the URL and tick the events (for example `device_offline` and `device_online`). Optionally set a secret.
3. If you set a secret, enter the same one in Configure. The signature is checked as HMAC-SHA256 of the raw body in the `X-MTM-Signature: sha256=<hex>` header; bad or missing signatures get a 401. With no secret, requests are accepted unsigned.
4. Use the manager's Send test button; a `mikrotik_manager_event` with `event: test` should appear in Developer tools, Events.

The manager refuses to post to private or loopback addresses, so the URL must resolve to a public address (Nabu Casa, or a reverse proxy in front of Home Assistant). Webhooks follow the manager's alert rules, cooldowns and maintenance windows.
