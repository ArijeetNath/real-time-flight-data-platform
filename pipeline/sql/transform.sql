-- Transform: raw -> staging -> marts. Rebuilt each run. metrics accumulate.

-- staging.flights: the latest snapshot (most recent batch), typed & unit-converted.
DROP TABLE IF EXISTS staging.flights;
CREATE TABLE staging.flights AS
WITH latest AS (SELECT max(batch_time) AS bt FROM raw.state_vectors)
SELECT
    r.icao24,
    nullif(r.callsign, '')                          AS callsign,
    r.origin_country,
    r.longitude,
    r.latitude,
    r.baro_altitude,
    round((r.baro_altitude * 3.28084)::numeric, 0)  AS altitude_ft,
    r.on_ground,
    r.velocity,
    round((r.velocity * 1.94384)::numeric, 0)       AS speed_kts,
    r.vertical_rate,
    round((r.vertical_rate * 196.85)::numeric, 0)   AS vertical_rate_fpm,  -- m/s -> ft/min
    nullif(r.squawk, '')                            AS squawk,
    r.batch_time
FROM raw.state_vectors r
JOIN latest ON r.batch_time = latest.bt;

-- marts.flights_current: each aircraft + nearest seed airport (haversine, km),
-- its airline (from the ICAO callsign prefix), and an emergency alert label.
-- 40-airport seed => coarse "nearest major hub", not true proximity.
--           swap seeds/airports.csv for full OurAirports (~80k rows) when it matters.
DROP TABLE IF EXISTS marts.flights_current;
CREATE TABLE marts.flights_current AS
SELECT DISTINCT ON (f.icao24)
    f.*,
    al.name AS airline,
    -- Emergency transponder codes are internationally reserved and unambiguous.
    CASE f.squawk
        WHEN '7500' THEN 'Hijack (7500)'
        WHEN '7600' THEN 'Radio failure (7600)'
        WHEN '7700' THEN 'General emergency (7700)'
    END AS alert,
    a.iata AS nearest_airport,
    round((6371 * acos(greatest(-1, least(1,
        cos(radians(f.latitude)) * cos(radians(a.latitude)) *
        cos(radians(a.longitude) - radians(f.longitude)) +
        sin(radians(f.latitude)) * sin(radians(a.latitude))
    ))))::numeric, 0) AS nearest_airport_km
FROM staging.flights f
CROSS JOIN seed.airports a
LEFT JOIN seed.airlines al ON al.icao = upper(left(f.callsign, 3))
ORDER BY f.icao24, nearest_airport_km;

-- marts.activity_metrics: one row per batch, idempotent.
INSERT INTO marts.activity_metrics
    (batch_time, snapshot_ts, total_aircraft, airborne, on_ground, countries,
     avg_altitude_ft, p95_altitude_ft, avg_speed_kts, emergencies)
SELECT
    batch_time,
    to_timestamp(batch_time),
    count(*),
    count(*) FILTER (WHERE NOT on_ground),
    count(*) FILTER (WHERE on_ground),
    count(DISTINCT origin_country),
    round(avg(altitude_ft))::int,
    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY altitude_ft))::int,
    round(avg(speed_kts))::int,
    count(*) FILTER (WHERE squawk IN ('7500', '7600', '7700'))
FROM staging.flights
GROUP BY batch_time
ON CONFLICT (batch_time) DO NOTHING;
