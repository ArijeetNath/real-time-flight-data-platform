"""Runnable check for the one piece of non-trivial pure logic: state parsing.
Run: `pytest` or `python tests/test_pipeline.py` (no DB needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.extract import parse_states  # noqa: E402


def test_parse_drops_rows_without_position():
    states = [
        # icao24, callsign, country, time_pos, last_contact, lon, lat, baro_alt, on_ground, vel, track, vrate
        ["abc123", "DLH123 ", "Germany", 1700000000, 1700000001, 8.5, 50.1, 10000.0, False, 250.0, 90.0, 0.0],
        ["def456", "        ", "France", None, 1700000002, None, None, None, True, None, None, None],  # no lat/lon
    ]
    rows = parse_states(states)
    assert len(rows) == 1
    r = rows[0]
    assert r["icao24"] == "abc123"
    assert r["callsign"] == "DLH123"        # trimmed
    assert r["on_ground"] is False
    assert r["latitude"] == 50.1
    assert r["velocity"] == 250.0


def test_parse_handles_truncated_rows():
    # OpenSky sometimes returns short arrays; missing trailing fields -> None.
    rows = parse_states([["x", "Y", "US", 1, 2, -70.0, 40.0]])
    assert len(rows) == 1
    assert rows[0]["baro_altitude"] is None
    assert rows[0]["longitude"] == -70.0


if __name__ == "__main__":
    test_parse_drops_rows_without_position()
    test_parse_handles_truncated_rows()
    print("ok")
