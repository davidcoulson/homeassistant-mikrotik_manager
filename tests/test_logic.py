"""Run with pytest or `python3 tests/test_logic.py`."""
import hashlib
import hmac
import importlib.util
import json
import pathlib

_p = pathlib.Path(__file__).parents[1] / "custom_components/mikrotik_manager/logic.py"
_spec = importlib.util.spec_from_file_location("logic", _p)
logic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(logic)

BODY = b'{"event":"device_offline","data":{"device_id":3,"device_name":"sw1"}}'


def sign(secret, body=BODY):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_signature_ok():
    assert logic.verify_signature("s3cret", BODY, sign("s3cret"))


def test_signature_bad_and_missing():
    assert not logic.verify_signature("s3cret", BODY, sign("other"))
    assert not logic.verify_signature("s3cret", BODY, None)
    assert not logic.verify_signature("s3cret", BODY, "sha256=")
    assert not logic.verify_signature("s3cret", BODY + b" ", sign("s3cret"))


def test_signature_not_required_without_secret():
    assert logic.verify_signature(None, BODY, None)
    assert logic.verify_signature("", BODY, "garbage")


def test_webhook_parse():
    p = logic.parse_webhook(BODY)
    assert (p["event"], p["device_id"], p["device_name"], p["severity"]) == ("device_offline", 3, "sw1", "error")
    assert "device_offline" in logic.REFRESH_EVENTS


def test_webhook_unknown_event_still_parsed():
    p = logic.parse_webhook(json.dumps({"event": "brand_new", "data": {}}).encode())
    assert p["event"] == "brand_new" and p["severity"] == "warning" and p["device_id"] is None
    assert logic.parse_webhook(b"not json") is None
    assert logic.parse_webhook(b"[1]") is None


def test_severity():
    assert logic.event_severity("device_online") == "info"
    assert logic.event_severity("config_drift") == "warning"


def test_site_header():
    assert logic.build_headers("t") == {"Authorization": "Bearer t"}
    assert logic.build_headers("t", None) == {"Authorization": "Bearer t"}
    assert logic.build_headers("t", "all") == {"Authorization": "Bearer t"}
    assert logic.build_headers("t", 2)["X-Site-Id"] == "2"
    assert logic.build_headers("t", "4")["X-Site-Id"] == "4"


def test_config_health():
    rows = [
        {"rule": "a", "severity": "critical", "title": "T", "detail": "x" * 1000, "objects": list(range(30))},
        {"rule": "b", "severity": "warning", "title": "W", "objects": None},
    ]
    r = logic.parse_config_health({"findings": rows, "checked_at": "now"})
    assert (r["count"], r["critical"], r["checked_at"]) == (2, 1, "now")
    assert len(r["findings"][0]["detail"]) == logic.MAX_TEXT
    assert len(r["findings"][0]["objects"]) == logic.MAX_OBJECTS
    assert [f["rule"] for f in logic.high_findings(r)] == ["a"]


def test_config_health_empty_or_bad():
    assert logic.parse_config_health(None)["count"] == 0
    assert logic.parse_config_health({"findings": ["x", None]})["count"] == 0


def test_insights():
    r = logic.parse_insights({"attention": [{"sev": "error", "category": "c", "title": "t", "body": "b", "path": "/p"}] * 30})
    assert r["count"] == 30 and len(r["items"]) == logic.MAX_INSIGHTS
    assert r["items"][0]["severity"] == "error"
    assert logic.parse_insights({}) == {"count": 0, "items": []}


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
    print("ok")
