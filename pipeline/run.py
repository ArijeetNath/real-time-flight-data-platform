"""Orchestration: run the ELT once, or loop on an interval.

A sleep-loop is the smallest thing that satisfies "batch, re-runs on
reload". Swap for Airflow/Dagster when you need retries, backfills, or DAGs.
"""
import argparse
import os
import time
from pathlib import Path

from pipeline.db import get_conn, run_sql_file
from pipeline.extract import fetch_states
from pipeline.load import init_db, load_batch

SQL_DIR = Path(__file__).parent / "sql"


def run_once():
    batch_time, rows = fetch_states()
    n = load_batch(batch_time, rows)
    with get_conn() as conn, conn.cursor() as cur:
        run_sql_file(cur, SQL_DIR / "transform.sql")
    print(f"batch {batch_time}: loaded {n} aircraft, transformed marts.")
    return n


def main():
    p = argparse.ArgumentParser(description="SkyFlow ELT")
    p.add_argument("mode", choices=["once", "loop"])
    p.add_argument("--interval", type=int, default=int(os.getenv("INGEST_INTERVAL", "300")))
    args = p.parse_args()

    init_db()
    if args.mode == "once":
        run_once()
        return
    while True:
        try:
            run_once()
        except Exception as e:  # keep looping; a skipped batch is harmless (idempotent)
            print(f"ingest error: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
