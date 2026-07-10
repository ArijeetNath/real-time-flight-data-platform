"""Extract: pull live state vectors from the OpenSky Network REST API."""
import time

import requests

STATES_URL = "https://opensky-network.org/api/states/all"

# OpenSky state-vector array positions -> (index, field, cast). Indices are
# explicit because we skip 12 (sensors) and 13 (geo_altitude) to reach squawk
# at 14 — the transponder code that powers emergency detection (7500/7600/7700).
# https://openskynetwork.github.io/opensky-api/rest.html#all-state-vectors
_FIELDS = [
    (0, "icao24", str), (1, "callsign", str), (2, "origin_country", str),
    (3, "time_position", int), (4, "last_contact", int),
    (5, "longitude", float), (6, "latitude", float), (7, "baro_altitude", float),
    (8, "on_ground", bool), (9, "velocity", float), (10, "true_track", float),
    (11, "vertical_rate", float), (14, "squawk", str),
]

_RETRYABLE = {429, 500, 502, 503, 504}


def fetch_states(max_retries=5):
    """Return (batch_time, [row dicts]) for all states globally.

    Exponential backoff on rate-limit / 5xx. Anonymous access.
    """
    delay = 2
    for _ in range(max_retries):
        r = requests.get(STATES_URL, timeout=60)
        if r.status_code in _RETRYABLE:
            time.sleep(delay)
            delay *= 2
            continue
        r.raise_for_status()
        payload = r.json()
        return payload["time"], parse_states(payload.get("states") or [])
    raise RuntimeError(f"OpenSky unavailable after {max_retries} retries")


def parse_states(states):
    """Turn OpenSky's positional arrays into typed dicts; drop rows without a position."""
    rows = []
    for s in states:
        row = {}
        for idx, name, cast in _FIELDS:
            val = s[idx] if idx < len(s) else None
            if val is None:
                row[name] = None
            elif cast is bool:
                row[name] = bool(val)
            elif cast is str:
                row[name] = str(val).strip() or None
            else:
                try:
                    row[name] = cast(val)
                except (TypeError, ValueError):
                    row[name] = None
        if row["latitude"] is None or row["longitude"] is None:
            continue  # no position -> useless for an ops map
        rows.append(row)
    return rows
