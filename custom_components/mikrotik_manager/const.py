"""Constants for MikroTik Manager."""

DOMAIN = "mikrotik_manager"
CONF_VERIFY_SSL = "verify_ssl"
DEFAULT_SCAN_INTERVAL = 60
PLATFORMS = ["sensor", "binary_sensor", "update"]
CONF_THROUGHPUT_PORTS = "throughput_ports"
CONF_ALL_PORTS = "all_physical_ports"

CONF_SITE_ID = "site_id"
CONF_WEBHOOK_SECRET = "webhook_secret"
SITE_ALL = "all"
EVENT_NAME = "mikrotik_manager_event"
CONFIG_HEALTH_EVERY = 5  # refresh config-health every Nth coordinator cycle
