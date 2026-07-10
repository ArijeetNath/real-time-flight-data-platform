# SkyFlow ✈️ — Flight Data Engineering Platform

A batch **ELT pipeline** that ingests **live global flight positions** from the
[OpenSky Network](https://opensky-network.org/), lands them in **Postgres**,
models them into analytics tables with plain SQL, and serves an **airline-ops
dashboard** in Streamlit — the whole thing comes up with one command.

```bash
docker compose up --build
# dashboard:  http://localhost:8501
```

That's it. No API key required — SkyFlow uses anonymous OpenSky access.

**Stack:** Python 3.12 · PostgreSQL 16 · plain SQL (ELT) · Streamlit · Docker
Compose · pytest.

---

## What it does

An **airline ops analyst** opens the dashboard and sees, right now: how many
aircraft are airborne, where they are on a world map, the split by origin
country **and airline**, the **busiest nearby hubs**, altitude/speed stats, and
how the airborne count and average altitude have moved over recent history. An
**alerts panel** surfaces any aircraft squawking an emergency transponder code
(7500 hijack / 7600 radio failure / 7700 general emergency). **Refresh** pulls a
fresh snapshot on demand; a background service also pulls one every 5 minutes.

## Architecture

```
                        docker compose
  ┌──────────┐   ┌────────────────┐   ┌─────────────────┐   ┌────────────┐
  │ OpenSky  │──▶│  ingest        │──▶│   Postgres      │◀──│ Streamlit  │
  │  REST    │   │  (Python ELT)  │   │  raw ▸ staging  │   │ dashboard  │
  │  API     │   │  loop / on-    │   │       ▸ marts   │   │  + Refresh │
  └──────────┘   │  demand        │   └─────────────────┘   └────────────┘
                 └────────────────┘
```

Three services: **postgres** (warehouse), **ingest** (extract → load →
transform, every `INGEST_INTERVAL` seconds), **dashboard** (reads the marts,
Refresh button triggers an ingest).

## The data model — a layered warehouse

| Layer | Table | Purpose |
|-------|-------|---------|
| **raw** | `state_vectors` | Append-only landing zone. Every batch kept → a cheap time-series of the sky. Includes the transponder `squawk` code. |
| **staging** | `flights` | Latest snapshot, typed & unit-converted (m→ft, m/s→kts, climb→ft/min), callsigns cleaned. |
| **seed** | `airports` | Static reference data (major global hubs) for nearest-airport enrichment. |
| **seed** | `airlines` | ICAO callsign-prefix → airline name, for the airline breakdown. |
| **marts** | `flights_current` | One row per aircraft + **nearest airport** (haversine join), **airline**, and an **emergency alert** label. |
| **marts** | `activity_metrics` | One row per batch: counts, country spread, altitude/speed percentiles, emergency count. Powers the trends. |

Data flow lives in [`pipeline/sql/`](pipeline/sql/): `schema.sql` (DDL),
`transform.sql` (the raw→staging→marts ELT).

## Engineering choices worth calling out

- **Idempotent loads.** Batches `COPY` into a stage table, then
  `INSERT … ON CONFLICT DO NOTHING` on `(icao24, batch_time)`. Re-running a
  batch is a safe no-op — the pipeline can crash and restart without dupes.
- **Real-world API handling.** The OpenSky client uses anonymous access with
  exponential backoff on 429/5xx.
- **Append-only history.** Keeping every batch turns a boring live snapshot
  into a queryable time-series for near-zero extra code.
- **Emergency detection in SQL.** The reserved transponder codes
  (7500/7600/7700) are labelled in `flights_current` with a plain `CASE`, then
  surfaced live on the dashboard — real alerting logic, fully auditable.
- **Plain SQL transforms**, versioned in-repo — no hidden ORM magic, every
  line is auditable.

## What this project demonstrates

For anyone reviewing this as a work sample, SkyFlow shows end-to-end data
engineering in a small, readable footprint:

- **ELT pipeline design** — a clean extract → load → transform split with a
  layered warehouse (raw → staging → marts).
- **Data modeling in SQL** — typed staging, unit conversions, a haversine
  spatial join, and windowed metrics, all in version-controlled `.sql`.
- **Reliability engineering** — idempotent loads, retry/backoff on a real
  third-party API, and a crash-safe ingest loop.
- **Productionization basics** — containerized with Docker Compose, healthchecks,
  a one-command bring-up, and unit tests for the non-trivial logic.
- **Judgment** — explicit, documented scope decisions (see *Deliberate
  simplifications*) rather than half-built features.

## Deliberate simplifications (and when I'd change them)

Honest scope for a focused build:

| Simplification | Upgrade when |
|----------------|--------------|
| Sleep-loop scheduler | You need retries / backfills / DAG deps → **Airflow** or **Dagster**. |
| 40-airport seed for "nearest hub" | You need true proximity → full **OurAirports** (~80k rows). |
| Local Postgres | You need scale / sharing → managed warehouse (BigQuery / Snowflake). |

None of these are missing by accident — they're the next steps, sized to the
problem.

## Getting started

**Prerequisites:** Docker + Docker Compose. Nothing else — no Python, no API key.

```bash
git clone <this-repo> && cd skyflow
docker compose up --build     # postgres + ingest + dashboard
```

Then open **http://localhost:8501**. On first run the pipeline creates the
schema, pulls an initial snapshot, and builds the marts — the dashboard is
populated within a few seconds. After that, a fresh batch lands every
`INGEST_INTERVAL` seconds (default 300), or immediately when you hit **Refresh**.

```bash
# one-off ingest instead of the background loop:
docker compose run --rm ingest python -m pipeline.run once

# stop everything (data survives in the pgdata volume):
docker compose down

# stop and wipe the warehouse for a clean slate:
docker compose down -v
```

**Configuration** (optional) — copy `.env.example` to `.env` to tune settings:

| Var | Default | Meaning |
|-----|---------|---------|
| `INGEST_INTERVAL` | `300` | Seconds between batches in loop mode. |

### Quick start without Docker

Needs **Python 3.12** and a local **Postgres**. Create the role + database once
(matches the built-in default DSN):

```bash
createuser flight --pwprompt      # enter password: flight
createdb flight -O flight
```

Then bring it up:

```bash
pip install -r requirements.txt
python -m pipeline.run once       # create schema, pull one batch, build marts
streamlit run dashboard/app.py    # dashboard on http://localhost:8501
```

That's the whole app — the dashboard's **Refresh** button pulls new batches on
demand, so no scheduler is needed. Want the background loop instead? Run
`python -m pipeline.run loop`. Point at a different Postgres by setting
`DATABASE_URL` (default `postgresql://flight:flight@localhost:5432/flight`).

## Tests

```bash
pytest                        # pure-logic checks, no DB needed
```

## Layout

```
pipeline/
  extract.py      OpenSky client: anonymous fetch, retry/backoff, parsing (incl. squawk)
  load.py         idempotent COPY → stage → raw; seeds airports + airlines
  run.py          orchestration: once | loop
  db.py           connection + SQL-file runner
  sql/            schema.sql, transform.sql
  seeds/          airports.csv, airlines.csv (reference data)
dashboard/app.py  Streamlit ops dashboard: alerts, map, airlines, hubs, trends
dashboard/pages/  Anomaly Alerts + Data Quality pages (threshold alerts, sidebar nav)
tests/            parsing checks (incl. squawk capture)
```
