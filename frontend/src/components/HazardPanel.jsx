import { useEffect, useState } from "react";
import { getHazards, getHazardTimeseries } from "../api";
import TrendChart from "./TrendChart";

const HAZARD_SLOT = { Smoke: 1, Fire: 2, person_down: 3 };

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function hazardColor(label) {
  const slot = HAZARD_SLOT[label];
  return slot ? `var(--viz-${slot})` : "var(--viz-muted)";
}

export default function HazardPanel() {
  const [alerts, setAlerts] = useState([]);
  const [range, setRange] = useState("hourly");
  const [trend, setTrend] = useState({ series: [], buckets: [] });

  useEffect(() => {
    const load = () =>
      getHazards(50)
        .then((r) => setAlerts([...r.alerts].reverse()))
        .catch(() => {});
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let active = true;
    const load = () =>
      getHazardTimeseries(range)
        .then((r) => {
          if (active) setTrend(r);
        })
        .catch(() => {});
    load();
    const id = setInterval(load, 10000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [range]);

  const series = trend.series || [];
  const colors = series.map(hazardColor);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="card">
        <div className="trend-head">
          <h2>Incidents over time</h2>
          <div className="range-toggle hazard">
            <button className={range === "hourly" ? "active" : ""} onClick={() => setRange("hourly")}>Hourly</button>
            <button className={range === "weekly" ? "active" : ""} onClick={() => setRange("weekly")}>Weekly</button>
          </div>
        </div>
        <p className="empty-note" style={{ paddingTop: 0, marginTop: -6 }}>
          Each bar counts raised alerts, not detected frames -- repeat detections inside a cooldown stay one incident.
        </p>
        <TrendChart
          buckets={trend.buckets || []}
          series={series}
          colors={colors}
          unit="alerts"
          emptyMessage="No hazards raised in this window."
        />
      </div>

      <div className="card">
        <h2>Hazard alerts</h2>
        {alerts.length === 0 && (
          <p className="empty-note">No hazards raised yet. Alerts fire once a detection clears its confidence threshold and cooldown.</p>
        )}
        {alerts.map((a) => (
          <div className="alert-card" key={a.id}>
            <div className="stripe" />
            <div className="body">
              <div className="head">
                <span className="label">{a.label}</span>
                <span className="conf">
                  {Math.round(a.confidence * 100)}% &middot; {fmtTime(a.ts)}
                </span>
              </div>
              <p className="text">{a.meta.text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
