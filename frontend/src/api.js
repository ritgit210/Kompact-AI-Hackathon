export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8420";

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function postJSON(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", ...opts });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${path} -> ${res.status}`);
  }
  return res.json();
}

export const getStatus = () => getJSON("/api/status");

export const getEvents = ({ since = 0, type, limit = 200 } = {}) => {
  const params = new URLSearchParams();
  if (since) params.set("since", String(since));
  if (type) params.set("type", type);
  if (limit) params.set("limit", String(limit));
  return getJSON(`/api/events?${params}`);
};

export const getMoodStats = (windowSec = 300) => getJSON(`/api/mood/stats?window_sec=${windowSec}`);

export const getHazards = (limit = 50) => getJSON(`/api/hazards?limit=${limit}`);

export const getMoodTimeseries = (range = "hourly") => getJSON(`/api/mood/timeseries?range=${range}`);

export const getHazardTimeseries = (range = "hourly") => getJSON(`/api/hazards/timeseries?range=${range}`);

export const streamUrl = (source) => `${API_BASE}/api/stream/${source}`;

export const getSources = () => getJSON("/api/sources");

export const setSourceWebcam = (source, device = 0) =>
  postJSON(`/api/sources/${source}/webcam?device=${device}`);

export function uploadSourceVideo(source, file) {
  const form = new FormData();
  form.append("file", file);
  return postJSON(`/api/sources/${source}/upload`, { body: form });
}
