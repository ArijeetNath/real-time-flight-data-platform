"""Data Quality page (auto-added to the sidebar by Streamlit multipage).

Per-batch reliability view from raw.state_vectors (append-only history) — no new
SQL objects. Alerts when the latest batch drops below a coverage/freshness bar.

Note: "position coverage" isn't measurable downstream — parse_states drops
no-position rows at extract, so every stored row has a position by construction.
We measure what survives: null coverage (altitude/callsign/squawk) and position
staleness (time_position age). Add an extract-time counter of dropped rows if you
want true ingest coverage.
"""
import pandas as pd
import streamlit as st

from pipeline.db import get_conn

st.set_page_config(page_title="SkyFlow — Data Quality", layout="wide")
st.title("SkyFlow  🩺  Data Quality")
st.caption("Per-batch freshness & field coverage from the raw landing zone.")


@st.cache_data(ttl=30)
def q(sql):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


# 30s position-staleness window is a fixed heuristic; make it a slider
# if OpenSky's update cadence varies for your use.
df = q("""
    SELECT
        batch_time,
        to_timestamp(batch_time)                                              AS snapshot_ts,
        count(*)                                                              AS rows,
        round(100.0 * count(*) FILTER (WHERE baro_altitude IS NOT NULL) / count(*), 1) AS altitude_cov,
        round(100.0 * count(*) FILTER (WHERE nullif(callsign, '') IS NOT NULL) / count(*), 1) AS callsign_cov,
        round(100.0 * count(*) FILTER (WHERE squawk IS NOT NULL) / count(*), 1)         AS squawk_cov,
        round(100.0 * count(*) FILTER (
            WHERE time_position IS NOT NULL AND batch_time - time_position <= 30
        ) / count(*), 1)                                                      AS fresh_pos_pct
    FROM raw.state_vectors
    GROUP BY batch_time
    ORDER BY batch_time
""")
if df.empty:
    st.warning("No data yet — pull a batch from the main page first.")
    st.stop()

age_s = int(q("SELECT extract(epoch FROM now()) - max(batch_time) AS age FROM raw.state_vectors").iloc[0].age)

st.sidebar.header("Alert thresholds")
min_cov = st.sidebar.slider("Min altitude coverage (%)", 50, 100, 90, 1)
max_age_min = st.sidebar.slider("Max batch age (min)", 5, 60, 15, 5)

latest = df.iloc[-1]
m = st.columns(4)
m[0].metric("Latest batch age", f"{age_s // 60}m {age_s % 60}s")
m[1].metric("Rows in batch", int(latest.rows))
m[2].metric("Altitude coverage", f"{latest.altitude_cov}%")
m[3].metric("Position fresh (≤30s)", f"{latest.fresh_pos_pct}%")

problems = []
if age_s > max_age_min * 60:
    problems.append(f"latest batch is {age_s // 60}m old (> {max_age_min}m)")
if latest.altitude_cov < min_cov:
    problems.append(f"altitude coverage {latest.altitude_cov}% (< {min_cov}%)")
if problems:
    st.error("🔴 " + " · ".join(problems))
else:
    st.success("✅ Latest batch is fresh and above coverage thresholds.")

st.subheader("Altitude coverage over time (%)")
st.line_chart(df.set_index("snapshot_ts")["altitude_cov"])
st.subheader("Position freshness over time (%)")
st.line_chart(df.set_index("snapshot_ts")["fresh_pos_pct"])
st.subheader("Rows per batch")
st.line_chart(df.set_index("snapshot_ts")["rows"])

st.subheader("Recent batches")
recent = df.tail(20).iloc[::-1].copy()
recent["below_threshold"] = recent["altitude_cov"] < min_cov
st.dataframe(
    recent[["snapshot_ts", "rows", "altitude_cov", "callsign_cov",
            "squawk_cov", "fresh_pos_pct", "below_threshold"]],
    use_container_width=True,
    hide_index=True,
)
