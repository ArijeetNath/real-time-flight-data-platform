"""Load: land a batch of state vectors into raw (append-only, idempotent)."""
from pathlib import Path

from pipeline.db import get_conn, run_sql_file

SQL_DIR = Path(__file__).parent / "sql"
SEEDS_CSV = Path(__file__).parent / "seeds" / "airports.csv"

_COLS = (
    "batch_time", "icao24", "callsign", "origin_country", "time_position",
    "last_contact", "longitude", "latitude", "baro_altitude", "on_ground",
    "velocity", "true_track", "vertical_rate",
)

# COPY into a stage table, then INSERT ... ON CONFLICT so re-running a batch
# is a no-op (idempotent). COPY itself can't do ON CONFLICT; the stage does.
_PROMOTE = f"""
INSERT INTO raw.state_vectors ({", ".join(_COLS)})
SELECT {", ".join(_COLS)} FROM raw.state_vectors_stage
ON CONFLICT (icao24, batch_time) DO NOTHING
"""


def init_db():
    with get_conn() as conn, conn.cursor() as cur:
        run_sql_file(cur, SQL_DIR / "schema.sql")
        _seed_airports(cur)


def _seed_airports(cur):
    cur.execute("SELECT count(*) FROM seed.airports")
    if cur.fetchone()[0] > 0:
        return
    copy_sql = (
        "COPY seed.airports (iata, name, country, latitude, longitude) "
        "FROM STDIN WITH (FORMAT csv, HEADER true)"
    )
    with cur.copy(copy_sql) as cp:
        cp.write(SEEDS_CSV.read_text(encoding="utf-8"))


def load_batch(batch_time, rows):
    if not rows:
        return 0
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE raw.state_vectors_stage")
        with cur.copy(f"COPY raw.state_vectors_stage ({', '.join(_COLS)}) FROM STDIN") as cp:
            for r in rows:
                cp.write_row((batch_time, *(r[c] for c in _COLS[1:])))
        cur.execute(_PROMOTE)
        cur.execute("TRUNCATE raw.state_vectors_stage")
    return len(rows)
