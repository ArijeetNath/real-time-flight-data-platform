"""Second page (auto-added to the sidebar by Streamlit's multipage support).

Threshold-based anomaly alerts, computed live from marts.flights_current — no
new SQL or schema: everything here is derived from columns the mart already has.
Fixed thresholds are a coarse heuristic, not statistical outliers;
the sidebar sliders are the calibration knob. Swap for per-type baselines
(e.g. rolling percentiles) if false-positive rate matters.
"""
import pandas as pd
import streamlit as st

from pipeline.db import get_conn

st.set_page_config(page_title="SkyFlow — Anomaly Alerts", layout="wide")
st.title("SkyFlow  🚨  Anomaly Alerts")
st.caption("Live threshold alerts from the current snapshot. Tune thresholds in the sidebar.")


@st.cache_data(ttl=30)
def q(sql):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql)
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


df = q("SELECT * FROM marts.flights_current")
if df.empty:
    st.warning("No data yet — pull a batch from the main page first.")
    st.stop()

st.sidebar.header("Thresholds")
descent = st.sidebar.slider("Steep descent (ft/min down)", 1000, 6000, 2500, 250)
climb = st.sidebar.slider("Steep climb (ft/min up)", 1000, 6000, 3000, 250)
overspeed = st.sidebar.slider("Overspeed (kts)", 400, 800, 650, 10)
ceiling = st.sidebar.slider("Extreme altitude (ft)", 40000, 60000, 50000, 1000)

# Each rule is one boolean mask over the mart — label -> matching rows.
rules = {
    f"Steep descent (< -{descent} fpm)": df.vertical_rate_fpm <= -descent,
    f"Steep climb (> {climb} fpm)": df.vertical_rate_fpm >= climb,
    f"Overspeed (≥ {overspeed} kts)": df.speed_kts >= overspeed,
    f"Extreme altitude (≥ {ceiling} ft)": df.altitude_ft >= ceiling,
}

cols = st.columns(len(rules))
for col, (label, mask) in zip(cols, rules.items()):
    col.metric(label.split(" (")[0], int(mask.sum()))

flagged = pd.concat([df[mask].assign(anomaly=label) for label, mask in rules.items()])
if flagged.empty:
    st.success("No anomalies against the current thresholds.")
    st.stop()

st.subheader("Flagged aircraft")
st.dataframe(
    flagged[[
        "anomaly", "icao24", "callsign", "airline", "origin_country",
        "altitude_ft", "speed_kts", "vertical_rate_fpm", "on_ground",
        "nearest_airport",
    ]],
    use_container_width=True,
    hide_index=True,
)

st.subheader("Where they are")
st.map(flagged.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
