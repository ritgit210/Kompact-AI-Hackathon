import { useEffect, useRef, useState } from "react";
import { getEvents, getSources, setSourceWebcam, streamUrl, uploadSourceVideo } from "../api";

const SOURCE = "feed";

function relTime(ts) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s ago`;
  return `${Math.round(s / 60)}m ago`;
}

function FeedCard() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const load = () =>
      getSources()
        .then((all) => setInfo(all[SOURCE]))
        .catch(() => {});
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const handleWebcam = async () => {
    setBusy(true);
    setError("");
    try {
      setInfo(await setSourceWebcam(SOURCE));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleFileChange = async (ev) => {
    const file = ev.target.files?.[0];
    ev.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      setInfo(await uploadSourceVideo(SOURCE, file));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const mode = info?.mode;
  const subLabel = !info ? "..." : mode === "webcam" ? `live webcam (device ${info.device})` : `looping: ${info.label}`;

  return (
    <div className="card live-feed-wrap">
      <div className="feed-label">
        <span className="src-name">Camera</span>
        <span className="src-sub">{subLabel}</span>
      </div>
      <div className="feed-frame">
        <img src={streamUrl(SOURCE)} alt="Live feed" />
      </div>
      <div className="source-controls">
        <button className={mode === "webcam" ? "active" : ""} disabled={busy} onClick={handleWebcam}>
          Webcam
        </button>
        <button
          className={mode === "file" ? "active" : ""}
          disabled={busy}
          onClick={() => fileInputRef.current?.click()}
        >
          Upload video (loops)
        </button>
        <input type="file" accept="video/*" ref={fileInputRef} hidden onChange={handleFileChange} />
      </div>
      {error && <p className="source-error">{error}</p>}
    </div>
  );
}

export default function LiveView() {
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    const load = () =>
      getEvents({ limit: 20 })
        .then((rows) => rows.filter((r) => r.type === "emotion" || r.type === "hazard_raw").slice(-10))
        .then(setRecent)
        .catch(() => {});
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <FeedCard />

      <div className="card ticker" style={{ marginTop: 16 }}>
        <h2>Latest detections</h2>
        {recent.length === 0 && <p className="empty-note">Waiting for the first detection...</p>}
        {[...recent].reverse().map((e) => (
          <div className="ticker-row" key={e.id}>
            <span className="t">{relTime(e.ts)}</span>
            <span className={`badge ${e.type === "emotion" ? "emotion" : "hazard"}`}>{e.type}</span>
            <span>
              <strong>{e.label}</strong> &middot; {Math.round(e.confidence * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
