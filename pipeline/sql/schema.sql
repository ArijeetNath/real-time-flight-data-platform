-- Layered warehouse: raw (landing) -> staging (clean) -> marts (serve).
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;
CREATE SCHEMA IF NOT EXISTS seed;

-- Append-only history: every batch is kept -> a cheap time-series of the sky.
CREATE TABLE IF NOT EXISTS raw.state_vectors (
    batch_time      bigint      NOT NULL,
    icao24          text        NOT NULL,
    callsign        text,
    origin_country  text,
    time_position   bigint,
    last_contact    bigint,
    longitude       double precision,
    latitude        double precision,
    baro_altitude   double precision,
    on_ground       boolean,
    velocity        double precision,
    true_track      double precision,
    vertical_rate   double precision,
    ingested_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (icao24, batch_time)
);
CREATE INDEX IF NOT EXISTS ix_raw_batch_time ON raw.state_vectors (batch_time);

-- Scratch table for the COPY -> ON CONFLICT idempotent load.
CREATE UNLOGGED TABLE IF NOT EXISTS raw.state_vectors_stage (
    batch_time bigint, icao24 text, callsign text, origin_country text,
    time_position bigint, last_contact bigint, longitude double precision,
    latitude double precision, baro_altitude double precision, on_ground boolean,
    velocity double precision, true_track double precision, vertical_rate double precision
);

-- Reference data for enrichment (nearest airport).
CREATE TABLE IF NOT EXISTS seed.airports (
    iata      text,
    name      text,
    country   text,
    latitude  double precision,
    longitude double precision
);

-- Per-batch aggregates accumulate here (idempotent on batch_time).
CREATE TABLE IF NOT EXISTS marts.activity_metrics (
    batch_time      bigint PRIMARY KEY,
    snapshot_ts     timestamptz,
    total_aircraft  int,
    airborne        int,
    on_ground       int,
    countries       int,
    avg_altitude_ft int,
    p95_altitude_ft int,
    avg_speed_kts   int
);

-- Data-quality report, one row per batch (idempotent on batch_time).
CREATE TABLE IF NOT EXISTS marts.data_quality (
    batch_time        bigint PRIMARY KEY,
    checked_at        timestamptz DEFAULT now(),
    total_rows        int,
    null_callsign_pct numeric,
    null_altitude_pct numeric,
    out_of_range      int,      -- impossible lat/lon (should be 0)
    speed_anomaly     int,      -- velocity > 400 m/s (~777 kts), faster than any airliner
    passed            boolean
);
