"""Pure helpers (no Home Assistant or aiohttp imports) so they can be unit tested."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

SITE_HEADER = "X-Site-Id"
SIGNATURE_HEADER = "X-MTM-Signature"
MAX_FINDINGS = 20
MAX_INSIGHTS = 20
MAX_OBJECTS = 10
MAX_TEXT = 300

# Findings the manager marks critical raise a Repairs issue.
HIGH_SEVERITIES = frozenset({"critical", "high", "error"})

# Events that mean a device's reachability changed: refresh straight away.
REFRESH_EVENTS = frozenset({"device_offline", "device_online"})
_ERROR_EVENTS = frozenset({
    "device_offline", "device_degraded", "device_identity_changed", "log_error",
    "high_cpu", "high_memory", "rollout_failed", "cve_active",
})
_INFO_EVENTS = frozenset({
    "device_online", "device_health_restored", "device_discovered",
    "rollout_completed", "test",
})


def build_headers(token: str, site_id: int | str | None = None) -> dict[str, str]:
    """Request headers; X-Site-Id only when a site is chosen (absent = whole fleet)."""
    headers = {"Authorization": f"Bearer {token}"}
    if site_id not in (None, "", "all"):
        headers[SITE_HEADER] = str(site_id)
    return headers


def verify_signature(secret: str | None, body: bytes, header: str | None) -> bool:
    """Check the manager's `X-MTM-Signature: sha256=<hex hmac of the raw body>`.

    No secret configured means signatures are not required. With a secret, a
    missing or malformed header fails.
    """
    if not secret:
        return True
    if not header:
        return False
    value = header.strip()
    if value.lower().startswith("sha256="):
        value = value[7:]
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, value.lower())


def event_severity(event: str) -> str:
    if event in _ERROR_EVENTS:
        return "error"
    if event in _INFO_EVENTS:
        return "info"
    return "warning"


def parse_webhook(body: bytes) -> dict[str, Any] | None:
    """Bus-event payload from a manager webhook body, or None if it is not JSON."""
    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    event = str(doc.get("event") or "unknown")
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    return {
        "event": event,
        "device_id": data.get("device_id"),
        "device_name": data.get("device_name"),
        "severity": event_severity(event),
        "message": data.get("message"),
        "details": data.get("details"),
        "timestamp": doc.get("timestamp"),
    }


def _clip(value: Any, limit: int = MAX_TEXT) -> Any:
    return value[:limit] if isinstance(value, str) else value


def parse_config_health(payload: Any) -> dict[str, Any]:
    """Normalise GET /api/devices/:id/config-health.

    Returns {"count", "critical", "findings" (capped), "checked_at"}; every row
    the manager returns is an open finding.
    """
    payload = payload if isinstance(payload, dict) else {}
    rows = [f for f in (payload.get("findings") or []) if isinstance(f, dict)]
    findings = []
    for f in rows:
        objects = f.get("objects") if isinstance(f.get("objects"), list) else []
        findings.append({
            "rule": f.get("rule"),
            "severity": f.get("severity"),
            "title": _clip(f.get("title")),
            "detail": _clip(f.get("detail")),
            "objects": [str(o) for o in objects[:MAX_OBJECTS]],
            "first_seen": f.get("first_seen"),
            "last_seen": f.get("last_seen"),
        })
    return {
        "count": len(findings),
        "critical": sum(1 for f in findings if str(f["severity"]).lower() in HIGH_SEVERITIES),
        "findings": findings,
        "checked_at": payload.get("checked_at"),
    }


def high_findings(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """High-severity findings that have a rule id (the repairs issue key)."""
    return [
        f for f in parsed.get("findings", [])
        if f.get("rule") and str(f.get("severity")).lower() in HIGH_SEVERITIES
    ]


def parse_insights(payload: Any) -> dict[str, Any]:
    """Normalise GET /api/operations/insights into a count plus capped items."""
    payload = payload if isinstance(payload, dict) else {}
    rows = [i for i in (payload.get("attention") or []) if isinstance(i, dict)]
    return {
        "count": len(rows),
        "items": [
            {"severity": i.get("sev"), "category": i.get("category"),
             "title": _clip(i.get("title")), "body": _clip(i.get("body")), "path": i.get("path")}
            for i in rows[:MAX_INSIGHTS]
        ],
    }
