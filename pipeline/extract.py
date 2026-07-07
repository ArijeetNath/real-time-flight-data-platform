"""Extract: pull live state vectors from the OpenSky Network REST API."""
import os
import time

import requests

STATES_URL = "https://opensky-network.org/api/states/all"
TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/"
    "opensky-network/protocol/openid-connect/token"
)

# OpenSky state-vector array positions -> (field, cast). We keep indices 0..11.
# https://openskynetwork.github.io/opensky-api/rest.html#all-state-vectors
_FIELDS = [
    ("icao24", str), ("callsign", str), ("origin_country", str),
    ("time_position", int), ("last_contact", int),
    ("longitude", float), ("latitude", float), ("baro_altitude", float),
    ("on_ground", bool), ("velocity", float), ("true_track", float),
    ("vertical_rate", float),
]

_RETRYABLE = {429, 500, 502, 503, 504}


def _get_token():
    """OAuth2 client-credentials token, or None for anonymous access."""
    cid, secret = os.getenv("OPENSKY_CLIENT_ID"), os.getenv("OPENSKY_CLIENT_SECRET")
    if not cid or not secret:
        return None
    r = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_states(max_retries=5):
    """Return (batch_time, [row dicts]) for all states globally.

    Exponential backoff on rate-limit / 5xx. Anonymous unless creds are in env.
    """
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    delay = 2
    for _ in range(max_retries):
        r = requests.get(STATES_URL, headers=headers, timeout=60)
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
        for i, (name, cast) in enumerate(_FIELDS):
            val = s[i] if i < len(s) else None
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
