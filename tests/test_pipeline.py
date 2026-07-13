import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.extract import parse_states


def test_parse_drops_rows_without_position():
    states = [
        ["abc123", "DLH123 ", "Germany", 1700000000, 1700000001, 8.5, 50.1, 10000.0, False, 250.0, 90.0, 0.0],
        ["def456", "        ", "France", None, 1700000002, None, None, None, True, None, None, None],
    ]
    rows = parse_states(states)
    assert len(rows) == 1
    r = rows[0]
    assert r["icao24"] == "abc123"
    assert r["callsign"] == "DLH123"
    assert r["on_ground"] is False
    assert r["latitude"] == 50.1
    assert r["velocity"] == 250.0


def test_parse_handles_truncated_rows():
    rows = parse_states([["x", "Y", "US", 1, 2, -70.0, 40.0]])
    assert len(rows) == 1
    assert rows[0]["baro_altitude"] is None
    assert rows[0]["longitude"] == -70.0
    assert rows[0]["squawk"] is None


def test_parse_captures_squawk_at_index_14():
    full = ["abc123", "SWA42", "United States", 1, 2, -100.0, 40.0, 9000.0,
            False, 200.0, 45.0, -3000.0, None, 9100.0, "7700", False, 0]
    rows = parse_states([full])
    assert rows[0]["squawk"] == "7700"
    assert rows[0]["vertical_rate"] == -3000.0


if __name__ == "__main__":
    test_parse_drops_rows_without_position()
    test_parse_handles_truncated_rows()
    test_parse_captures_squawk_at_index_14()
    print("ok")
