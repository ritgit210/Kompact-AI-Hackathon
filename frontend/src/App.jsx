import { useEffect, useState } from "react";
import { getStatus } from "./api";
import LiveView from "./components/LiveView";
import MoodPanel from "./components/MoodPanel";
import HazardPanel from "./components/HazardPanel";
import InsightPanel from "./components/InsightPanel";

const TABS = [
  { key: "live", label: "Live" },
  { key: "mood", label: "Mood" },
  { key: "hazards", label: "Hazards" },
  { key: "insights", label: "Insights" },
];

export default function App() {
  const [tab, setTab] = useState("live");
  const [status, setStatus] = useState(null);

  useEffect(() => {
    const load = () => getStatus().then(setStatus).catch(() => setStatus(null));
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <>
      <header className="app-header">
        <div className="app-title">
          <h1>Vigil</h1>
          <span>webcam &rarr; cv &rarr; small llm</span>
        </div>
        <div className="status-pills">
          {status ? (
            <>
              <Pill on={status.models.emotion} label="mood model" />
              <Pill on={status.models.fall} label="fall model" />
              <Pill on={status.models.fire} label="fire model" />
              <Pill on={status.llm_configured} label={`llm: ${status.llm_provider}/${status.llm_model}`} />
            </>
          ) : (
            <span className="pill off">
              <span className="dot" /> backend unreachable
            </span>
          )}
        </div>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main>
        {tab === "live" && <LiveView />}
        {tab === "mood" && <MoodPanel />}
        {tab === "hazards" && <HazardPanel />}
        {tab === "insights" && <InsightPanel />}
      </main>
    </>
  );
}

function Pill({ on, label }) {
  return (
    <span className={`pill ${on ? "on" : "off"}`}>
      <span className="dot" />
      {label}
    </span>
  );
}
