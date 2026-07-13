import os
from pathlib import Path

import psycopg


def get_conn():
    dsn = os.getenv("DATABASE_URL", "postgresql://flight:flight@localhost:5432/flight")
    return psycopg.connect(dsn, autocommit=True)


def run_sql_file(cur, path):
    sql = Path(path).read_text(encoding="utf-8")
    for stmt in sql.split(";"):
        if stmt.strip():
            cur.execute(stmt)
