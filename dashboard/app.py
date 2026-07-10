import pandas as pd
import streamlit as st

from pipeline.db import get_conn
from pipeline.run import run_once

st.set_page_config(page_title="SkyFlow — Flight Ops", layout="wide")
st.title("SkyFlow  ✈️  Live Flight Ops")


@st.cache_data(ttl=30)
def q(sql):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


if st.button("\U0001F504 Refresh (pull new batch)"):
    with st.spinner("Fetching latest snapshot from OpenSky..."):
        run_once()
    st.cache_data.clear()

metrics = q("SELECT * FROM marts.activity_metrics ORDER BY snapshot_ts")
if metrics.empty:
    st.warning("No data yet — click **Refresh**, or wait for the first ingest batch.")
    st.stop()

current = q("SELECT * FROM marts.flights_current")
latest = metrics.iloc[-1]

m = st.columns(6)
m[0].metric("Aircraft tracked", int(latest.total_aircraft))
m[1].metric("Airborne", int(latest.airborne))
m[2].metric("On ground", int(latest.on_ground))
m[3].metric("Countries", int(latest.countries))
m[4].metric("Avg altitude (ft)", int(latest.avg_altitude_ft or 0))
m[5].metric("Emergencies", int(latest.emergencies or 0))

# --- Emergency alerts (computed live from the current snapshot) ---
st.subheader("⚠️ Active alerts")
alerts = current[current["alert"].notna()]
if alerts.empty:
    st.success("No aircraft squawking an emergency code right now.")
else:
    for _, a in alerts.iterrows():
        st.error(
            f"**{a['alert']}** — {a['callsign'] or a['icao24']} "
            f"({a['airline'] or a['origin_country']}), "
            f"nearest hub {a['nearest_airport']} ~{int(a['nearest_airport_km'])} km"
        )
    st.map(alerts.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])

st.subheader("Where they are now")
st.map(current.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])

left, right = st.columns(2)
with left:
    st.subheader("Airborne count over time")
    st.line_chart(metrics.set_index("snapshot_ts")["airborne"])
    st.subheader("Avg altitude over time (ft)")
    st.line_chart(metrics.set_index("snapshot_ts")["avg_altitude_ft"])
with right:
    st.subheader("Top airlines (current)")
    airlines = current["airline"].fillna("Other / GA").value_counts().head(10)
    st.bar_chart(airlines)
    st.subheader("Busiest hubs — nearest airport (current)")
    st.bar_chart(current["nearest_airport"].value_counts().head(10))

st.subheader("Top origin countries (current)")
st.bar_chart(current["origin_country"].value_counts().head(10))

st.subheader("Flights (current snapshot)")
st.dataframe(
    current[[
        "icao24", "callsign", "airline", "origin_country", "altitude_ft",
        "speed_kts", "vertical_rate_fpm", "on_ground", "squawk", "alert",
        "nearest_airport", "nearest_airport_km",
    ]],
    use_container_width=True,
    hide_index=True,
)
