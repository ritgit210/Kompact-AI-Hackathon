import { useEffect, useState } from "react";
import { getMoodStats, getMoodTimeseries } from "../api";
import TrendChart from "./TrendChart";

const MOOD_SLOT = {
  neutral: 1,
  happy: 2,
  surprise: 3,
  sad: 4,
  angry: 5,
  disgust: 6,
  fear: 7,
  contempt: 8,
};

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function moodColors(series) {
  return series.map((k) => (MOOD_SLOT[k] ? `var(--viz-${MOOD_SLOT[k]})` : "var(--viz-muted)"));
}

export default function MoodPanel() {
  const [stats, setStats] = useState({ counts: {}, summaries: [] });
  const [range, setRange] = useState("hourly");
  const [trend, setTrend] = useState({ series: [], buckets: [] });

  useEffect(() => {
    const load = () => getMoodStats(300).then(setStats).catch(() => {});
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let active = true;
    const load = () =>
      getMoodTimeseries(range)
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

  const entries = Object.entries(stats.counts).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, n]) => n));
  const latest = stats.summaries[stats.summaries.length - 1];
  const series = trend.series || [];

  return (
    <div>
      <div className="grid-2">
        <div className="card">
          <h2>Expression counts &middot; last 5 min</h2>
          {entries.length === 0 && <p className="empty-note">No faces detected yet.</p>}
          {entries.map(([label, n]) => (
            <div className="bar-row" key={label}>
              <span>{label}</span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(n / max) * 100}%` }} />
              </div>
              <span className="count">{n}</span>
            </div>
          ))}
        </div>

        <div className="card">
          <h2>Latest mood insight</h2>
          {!latest && (
            <p className="empty-note">
              The first summary lands after the batch window closes (see BATCH_SUMMARY_INTERVAL_SEC in config.py).
            </p>
          )}
          {latest && (
            <div>
              <div className="insight-time" style={{ marginBottom: 6 }}>
                {fmtTime(latest.ts)} &middot; {latest.meta.sample_size} readings
              </div>
              <p className="insight-text">{latest.meta.text}</p>
            </div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="trend-head">
          <h2>Mood over time</h2>
          <div className="range-toggle">
            <button className={range === "hourly" ? "active" : ""} onClick={() => setRange("hourly")}>Hourly</button>
            <button className={range === "weekly" ? "active" : ""} onClick={() => setRange("weekly")}>Weekly</button>
          </div>
        </div>
        <TrendChart
          buckets={trend.buckets || []}
          series={series}
          colors={moodColors(series)}
          unit="reads"
          emptyMessage="No mood readings in this window yet."
        />
      </div>
    </div>
  );
}
