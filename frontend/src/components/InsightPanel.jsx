import { useEffect, useState } from "react";
import { getEvents } from "../api";

function fmtTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function InsightPanel() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    const load = async () => {
      const [moods, hazards] = await Promise.all([
        getEvents({ type: "mood_summary", limit: 30 }),
        getEvents({ type: "hazard_alert", limit: 30 }),
      ]);
      const merged = [...moods, ...hazards].sort((a, b) => b.ts - a.ts);
      setItems(merged);
    };
    load();
    const id = setInterval(load, 4000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="card">
      <h2>LLM-generated insights</h2>
      <p className="empty-note" style={{ paddingTop: 0, marginTop: -6 }}>
        Every line here came out of the small CPU model configured in config.py -- never raw pixels, only
        structured events in.
      </p>
      {items.length === 0 && <p className="empty-note">Nothing generated yet.</p>}
      {items.map((e) => {
        const isMood = e.type === "mood_summary";
        return (
          <div className="insight-item" key={`${e.type}-${e.id}`}>
            <div className="insight-meta">
              <span className={`insight-kind ${isMood ? "mood" : "hazard"}`}>
                {isMood ? "Mood summary" : `Hazard: ${e.label}`}
              </span>
              <span className="insight-time">{fmtTime(e.ts)}</span>
            </div>
            <p className="insight-text">{e.meta.text}</p>
          </div>
        );
      })}
    </div>
  );
}
