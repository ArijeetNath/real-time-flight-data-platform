from decimal import Decimal

import pandas as pd
import streamlit as st

from pipeline.db import get_conn
from pipeline.run import run_once

st.set_page_config(page_title="SkyFlow — Flight Ops", page_icon="✈️", layout="wide")


@st.cache_data(ttl=30)
def q(sql):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        cols = [c.name for c in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    # Postgres numeric -> Python Decimal, which charts/NumberColumn can't format.
    for col in df.columns:
        s = df[col].dropna()
        if len(s) and isinstance(s.iloc[0], Decimal):
            df[col] = df[col].astype(float)
    return df


# ── Header ──────────────────────────────────────────────────────────────────
head_l, head_r = st.columns([4, 1])
with head_l:
    st.title("SkyFlow ✈️")
    st.caption("Live global flight operations · batch ELT from the OpenSky Network")

# ── Sidebar: controls ───────────────────────────────────────────────────────
st.sidebar.header("⚙️ Controls")
if st.sidebar.button("🔄 Pull new batch", use_container_width=True):
    with st.spinner("Fetching latest snapshot from OpenSky…"):
        run_once()
    st.cache_data.clear()

metrics = q("SELECT * FROM marts.activity_metrics ORDER BY snapshot_ts")
if metrics.empty:
    st.info("No data yet — click **Pull new batch** in the sidebar, or wait for the first ingest.")
    st.stop()

current = q("SELECT * FROM marts.flights_current")
dq_all = q("SELECT * FROM marts.data_quality ORDER BY batch_time")
latest = metrics.iloc[-1]
dq = dq_all.iloc[-1] if not dq_all.empty else None

# Freshness indicator in the header.
age_min = int((pd.Timestamp.now(tz="UTC") - latest.snapshot_ts).total_seconds() // 60)
fresh = "🟢 fresh" if age_min <= 10 else "🟡 aging" if age_min <= 30 else "🔴 stale"
with head_r:
    st.metric("Last update", f"{age_min} min ago", help=f"{latest.snapshot_ts:%Y-%m-%d %H:%M UTC}")
    st.caption(fresh)

# ── Sidebar: filters ────────────────────────────────────────────────────────
st.sidebar.header("🔍 Filters")
countries = sorted(current["origin_country"].dropna().unique())
pick_country = st.sidebar.multiselect("Origin country", countries)
phases = sorted(current["phase"].dropna().unique())
pick_phase = st.sidebar.multiselect("Flight phase", phases)
alt_max = int(current["altitude_ft"].fillna(0).max() or 45000)
lo, hi = st.sidebar.slider("Altitude (ft)", 0, alt_max, (0, alt_max), step=500)

view = current.copy()
if pick_country:
    view = view[view["origin_country"].isin(pick_country)]
if pick_phase:
    view = view[view["phase"].isin(pick_phase)]
view = view[view["altitude_ft"].fillna(0).between(lo, hi)]

# ── KPI cards (always visible) ───────────────────────────────────────────────
st.divider()
cards = [
    ("Aircraft tracked", f"{int(latest.total_aircraft):,}"),
    ("Airborne", f"{int(latest.airborne):,}"),
    ("On ground", f"{int(latest.on_ground):,}"),
    ("Countries", str(int(latest.countries))),
    ("Avg altitude", f"{int(latest.avg_altitude_ft or 0):,} ft"),
    ("Data quality", "PASS ✅" if (dq is not None and dq.passed) else ("FAIL ⚠️" if dq is not None else "—")),
]
for col, (label, value) in zip(st.columns(6), cards):
    with col.container(border=True):
        st.metric(label, value)

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_overview, tab_map, tab_flights, tab_dq = st.tabs(
    ["📊 Overview", "🗺️ Map", "🛫 Flights", "✅ Data Quality"]
)

with tab_overview:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Airborne count over time")
        st.line_chart(metrics.set_index("snapshot_ts")["airborne"], height=280)
    with c2:
        st.subheader("Flight phase")
        st.bar_chart(view["phase"].value_counts(), height=280)
    st.subheader("Top origin countries")
    st.bar_chart(view["origin_country"].value_counts().head(12), height=280)

with tab_map:
    st.caption(f"Showing **{len(view):,}** of {len(current):,} aircraft after filters.")
    if view.empty:
        st.info("No aircraft match the current filters.")
    else:
        st.map(view.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]], size=20)

with tab_flights:
    cols = ["icao24", "callsign", "origin_country", "phase", "altitude_ft",
            "speed_kts", "on_ground", "nearest_airport", "nearest_airport_km"]
    st.dataframe(
        view[cols], hide_index=True, use_container_width=True,
        column_config={
            "icao24": "ICAO24",
            "callsign": "Callsign",
            "origin_country": "Country",
            "phase": "Phase",
            "altitude_ft": st.column_config.NumberColumn("Altitude", format="%d ft"),
            "speed_kts": st.column_config.NumberColumn("Speed", format="%d kts"),
            "on_ground": st.column_config.CheckboxColumn("On ground"),
            "nearest_airport": "Nearest hub",
            "nearest_airport_km": st.column_config.NumberColumn("Distance", format="%d km"),
        },
    )
    st.download_button("📥 Download filtered flights (CSV)",
                       view[cols].to_csv(index=False), "flights.csv", "text/csv")

with tab_dq:
    if dq is None:
        st.info("No data-quality report yet.")
    else:
        d = st.columns(5)
        d[0].metric("Status", "PASS ✅" if dq.passed else "FAIL ⚠️")
        d[1].metric("Rows", f"{int(dq.total_rows):,}")
        d[2].metric("Null callsign", f"{dq.null_callsign_pct:.1f}%")
        d[3].metric("Null altitude", f"{dq.null_altitude_pct:.1f}%")
        d[4].metric("Anomalies", int(dq.out_of_range + dq.speed_anomaly))
        st.subheader("Null rates over time (%)")
        st.line_chart(dq_all.set_index("batch_time")[["null_callsign_pct", "null_altitude_pct"]], height=260)
        st.subheader("Recent quality checks")
        st.dataframe(dq_all.sort_values("batch_time", ascending=False).head(20),
                     hide_index=True, use_container_width=True)
