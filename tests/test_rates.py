"""Run with pytest or `python3 tests/test_rates.py`."""
import importlib.util
import pathlib

_p = pathlib.Path(__file__).parents[1] / "custom_components/mikrotik_manager/rates.py"
_spec = importlib.util.spec_from_file_location("rates", _p)
rates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rates)


def s(rx, tx, t):
    return {"rx_bytes": rx, "tx_bytes": tx, "time": t}


def test_basic_rate():
    r = rates.compute_rates(s(0, 0, "2026-01-01T00:00:00Z"), s(1000, 500, "2026-01-01T00:00:10Z"))
    assert r == (800.0, 400.0)


def test_missing_prior():
    assert rates.compute_rates(None, s(1, 1, "2026-01-01T00:00:00Z")) == (None, None)


def test_counter_reset():
    r = rates.compute_rates(s(5000, 100, "2026-01-01T00:00:00Z"), s(10, 300, "2026-01-01T00:00:10Z"))
    assert r == (None, 160.0)


def test_bad_time():
    assert rates.compute_rates(s(0, 0, "2026-01-01T00:00:10Z"), s(1, 1, "2026-01-01T00:00:10Z")) == (None, None)
    assert rates.compute_rates(s(0, 0, "x"), s(1, 1, "y")) == (None, None)


def test_tracker():
    t = rates.RateTracker()
    t.update({"1": {"ether1": s(0, 0, "2026-01-01T00:00:00Z")}})
    assert t.rates[("1", "ether1")] == (None, None)
    t.update({"1": {"ether1": s(100, 200, "2026-01-01T00:00:08Z")}})
    assert t.rates[("1", "ether1")] == (100.0, 200.0)
    t.update({"1": {"ether1": s(100, 200, "2026-01-01T00:00:08Z")}})  # same sample
    assert t.rates[("1", "ether1")] == (100.0, 200.0)


def test_delta_mode():
    rates.COUNTERS_ARE_CUMULATIVE = False
    try:
        assert rates.compute_rates(s(0, 0, "2026-01-01T00:00:00Z"), s(100, 50, "2026-01-01T00:00:10Z")) == (80.0, 40.0)
    finally:
        rates.COUNTERS_ARE_CUMULATIVE = True


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
    print("ok")
