# MikroTik Manager for Home Assistant

Reads fleet data from [mikrotik-manager](https://github.com/2GT-Media-Group-LLC/mikrotik-manager) with one read-scope API token, instead of polling every router and switch.

Status: skeleton. Provides fleet sensors (devices online/total, active clients, 24h errors/warnings, 30-day uptime) and a per-device Online sensor. Planned: per-port link and PoE, latest CPU/memory (needs upstream issue #298), webhook-driven events.
