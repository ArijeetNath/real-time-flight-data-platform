-- SkyFlow · analyst query library
-- Ready-to-run questions against the modeled warehouse. Paste into psql or any
-- SQL client:  docker compose exec postgres psql -U flight -d flight

-- 1. Busiest origin countries in the current snapshot.
SELECT origin_country, count(*) AS aircraft
FROM marts.flights_current
GROUP BY origin_country
ORDER BY aircraft DESC
LIMIT 15;

-- 2. Fleet split by flight phase right now.
SELECT phase, count(*) AS aircraft,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM marts.flights_current
GROUP BY phase
ORDER BY aircraft DESC;

-- 3. Altitude distribution in 10k-ft bands (airborne only).
SELECT (width_bucket(altitude_ft, 0, 50000, 5) - 1) * 10000 AS band_ft_floor,
       count(*) AS aircraft
FROM marts.flights_current
WHERE NOT on_ground AND altitude_ft IS NOT NULL
GROUP BY band_ft_floor
ORDER BY band_ft_floor;

-- 4. Peak traffic: the batch with the most aircraft airborne.
SELECT snapshot_ts, airborne, total_aircraft, avg_altitude_ft, avg_speed_kts
FROM marts.activity_metrics
ORDER BY airborne DESC
LIMIT 5;

-- 5. Airborne trend: change vs the previous batch (window function).
SELECT snapshot_ts, airborne,
       airborne - lag(airborne) OVER (ORDER BY batch_time) AS delta_vs_prev
FROM marts.activity_metrics
ORDER BY batch_time DESC
LIMIT 20;

-- 6. Congestion around each major hub (aircraft within 50 km).
SELECT nearest_airport, nearest_airport_name, count(*) AS aircraft_within_50km
FROM marts.flights_current
WHERE nearest_airport_km <= 50
GROUP BY nearest_airport, nearest_airport_name
ORDER BY aircraft_within_50km DESC
LIMIT 15;

-- 7. Fastest aircraft currently airborne (sanity-bounded).
SELECT icao24, callsign, origin_country, speed_kts, altitude_ft, phase
FROM marts.flights_current
WHERE NOT on_ground AND speed_kts BETWEEN 1 AND 700
ORDER BY speed_kts DESC
LIMIT 20;

-- 8. Data-quality trend: null rates and failures over time.
SELECT to_timestamp(batch_time) AS checked_at, total_rows,
       null_callsign_pct, null_altitude_pct, out_of_range, speed_anomaly, passed
FROM marts.data_quality
ORDER BY batch_time DESC
LIMIT 20;

-- 9. History depth: how many batches retained and the window they cover.
SELECT count(DISTINCT batch_time) AS batches,
       to_timestamp(min(batch_time)) AS earliest,
       to_timestamp(max(batch_time)) AS latest
FROM raw.state_vectors;
