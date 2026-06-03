"""
landed/db.py
-------------
The data spine. Loads the CSV tables into DuckDB, exposes a *read-only*
run_sql() that the agent will call, and a get_schema() that tells the LLM
what tables and columns exist.

Run it directly to build the DB and see it work:
    python -m landed.db
"""

import math
import os
import re
import duckdb

TABLES = ["companies", "applications", "contacts", "events"]

# Anything that could change data is blocked — the agent only ever reads.
_BLOCKED = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|copy|truncate|pragma)\b",
    re.IGNORECASE,
)


def get_connection(db_path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path)


def load_csvs(con: duckdb.DuckDBPyConnection, data_dir: str) -> duckdb.DuckDBPyConnection:
    """Create one table per CSV. DuckDB infers types (dates become real DATEs)."""
    for t in TABLES:
        path = os.path.join(data_dir, f"{t}.csv").replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE TABLE {t} AS "
            f"SELECT * FROM read_csv_auto('{path}', header=true)"
        )
    return con


def build(data_dir: str = "sample_data", db_path: str = ":memory:"):
    con = get_connection(db_path)
    load_csvs(con, data_dir)
    return con


def get_schema(con: duckdb.DuckDBPyConnection) -> str:
    """A compact schema description to feed the model as grounding."""
    lines = []
    for t in TABLES:
        info = con.execute(f"PRAGMA table_info('{t}')").fetchall()
        cols = ", ".join(f"{row[1]} {row[2]}" for row in info)
        lines.append(f"{t}({cols})")
    return "\n".join(lines)


def _json_safe(v):
    """NaN/inf aren't valid JSON — turn them into None so the API never 500s."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def run_sql(con: duckdb.DuckDBPyConnection, query: str, max_rows: int = 200) -> dict:
    """Run a read-only query. Returns columns + rows, or raises on anything unsafe."""
    q = query.strip().rstrip(";")
    if _BLOCKED.search(q):
        raise ValueError("Only read-only queries are allowed (no insert/update/delete/etc).")
    if not re.match(r"(?is)^\s*(select|with)\b", q):
        raise ValueError("Query must start with SELECT or WITH.")
    rel = con.execute(q)
    columns = [d[0] for d in rel.description]
    rows = [[_json_safe(v) for v in r] for r in rel.fetchmany(max_rows)]
    return {"columns": columns, "rows": rows, "row_count": len(rows)}


def format_result(result: dict, max_show: int = 20) -> str:
    """Turn a result dict into a small text table (for the CLI and for the model)."""
    cols, rows = result["columns"], result["rows"]
    out = [" | ".join(cols), "-" * 40]
    for r in rows[:max_show]:
        out.append(" | ".join("" if v is None else str(v) for v in r))
    if result["row_count"] > max_show:
        out.append(f"... ({result['row_count']} rows total)")
    return "\n".join(out)


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    con = build(os.path.join(here, "sample_data"))

    print("SCHEMA\n------")
    print(get_schema(con))

    print("\nSAMPLE QUESTION: response rate by channel")
    res = run_sql(con, """
        SELECT a.channel,
               COUNT(DISTINCT a.application_id) AS applied,
               COUNT(DISTINCT e.application_id) AS got_a_response,
               ROUND(100.0 * COUNT(DISTINCT e.application_id)
                     / COUNT(DISTINCT a.application_id), 0) AS response_pct
        FROM applications a
        LEFT JOIN events e
          ON e.application_id = a.application_id AND e.event_type <> 'Applied'
        GROUP BY a.channel
        ORDER BY response_pct DESC
    """)
    print(format_result(res))

    print("\nSAFETY CHECK: trying a DELETE")
    try:
        run_sql(con, "DELETE FROM applications")
    except ValueError as e:
        print("blocked ->", e)
