"""SQLite-backed event log shared by the pipeline (writer) and the API (reader)."""
import datetime
import json
import sqlite3
import threading
import time

from config import DB_PATH, EMOTION_LABELS

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row
# WAL lets the dashboard's scan-heavy trend queries read a snapshot on their own
# connection without ever blocking the capture thread's writes.
_conn.execute("PRAGMA journal_mode=WAL")


def _read_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock:
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                source TEXT NOT NULL,
                type TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                meta TEXT
            )
            """
        )
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, ts)")
        _conn.commit()


def add_event(source: str, type_: str, label: str, confidence: float, meta: dict | None = None) -> dict:
    ts = time.time()
    with _lock:
        cur = _conn.execute(
            "INSERT INTO events (ts, source, type, label, confidence, meta) VALUES (?, ?, ?, ?, ?, ?)",
            (ts, source, type_, label, confidence, json.dumps(meta or {})),
        )
        _conn.commit()
        row_id = cur.lastrowid
    return {"id": row_id, "ts": ts, "source": source, "type": type_, "label": label, "confidence": confidence, "meta": meta or {}}


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["meta"] = json.loads(d["meta"] or "{}")
    return d


def events_since(ts: float, type_: str | None = None) -> list[dict]:
    with _lock:
        if type_:
            rows = _conn.execute(
                "SELECT * FROM events WHERE ts >= ? AND type = ? ORDER BY ts", (ts, type_)
            ).fetchall()
        else:
            rows = _conn.execute("SELECT * FROM events WHERE ts >= ? ORDER BY ts", (ts,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def recent_events(limit: int = 200, type_: str | None = None) -> list[dict]:
    with _lock:
        if type_:
            rows = _conn.execute(
                "SELECT * FROM events WHERE type = ? ORDER BY ts DESC LIMIT ?", (type_, limit)
            ).fetchall()
        else:
            rows = _conn.execute("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    return [_row_to_dict(r) for r in rows][::-1]


def emotion_counts_since(ts: float) -> dict[str, int]:
    with _lock:
        rows = _conn.execute(
            "SELECT label, COUNT(*) as n FROM events WHERE type = 'emotion' AND ts >= ? GROUP BY label",
            (ts,),
        ).fetchall()
    return {r["label"]: r["n"] for r in rows}


_BUCKET_SQL = {
    "%Y-%m-%d": (
        "SELECT strftime('%Y-%m-%d', ts, 'unixepoch', 'localtime') AS bucket, label, COUNT(*) AS n "
        "FROM events WHERE type = ? AND ts >= ? GROUP BY bucket, label"
    ),
    "%Y-%m-%d %H": (
        "SELECT strftime('%Y-%m-%d %H', ts, 'unixepoch', 'localtime') AS bucket, label, COUNT(*) AS n "
        "FROM events WHERE type = ? AND ts >= ? GROUP BY bucket, label"
    ),
}


def _bucket_grid(range_key: str) -> tuple[list[datetime.datetime], list[str], int, str]:
    """Local-time bucket edges + labels, oldest first, last bucket = the current partial one."""
    now = datetime.datetime.now()
    if range_key == "weekly":
        first = now.replace(hour=0, minute=0, second=0, microsecond=0) - datetime.timedelta(days=6)
        # step by calendar days, not 86400s, so a DST change doesn't shift the day boundaries
        edges = [first + datetime.timedelta(days=i) for i in range(7)]
        return edges, [f"{d:%a} {d.day}" for d in edges], 86400, "%Y-%m-%d"
    first = now.replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=23)
    edges = [first + datetime.timedelta(hours=i) for i in range(24)]
    return edges, [f"{d:%H}:00" for d in edges], 3600, "%Y-%m-%d %H"


def _timeseries(type_: str, range_key: str, order) -> dict:
    range_key = "weekly" if range_key == "weekly" else "hourly"
    edges, labels, bucket_seconds, key_fmt = _bucket_grid(range_key)
    # Grouping by the same local-calendar key the grid is built from keeps the two in
    # step through a DST change, where a day is not 86400s and an hour label repeats.
    index = {f"{d:{key_fmt}}": i for i, d in enumerate(edges)}

    # Its own connection, deliberately outside _lock: scanning the window takes long
    # enough that holding the shared lock would stall the capture thread's writes.
    conn = _read_conn()
    try:
        rows = conn.execute(_BUCKET_SQL[key_fmt], (type_, edges[0].timestamp())).fetchall()
    finally:
        conn.close()

    counts: list[dict[str, int]] = [{} for _ in edges]
    seen: set[str] = set()
    for r in rows:
        i = index.get(r["bucket"])
        if i is None:
            continue
        counts[i][r["label"]] = counts[i].get(r["label"], 0) + r["n"]
        seen.add(r["label"])

    return {
        "range": range_key,
        "bucket_seconds": bucket_seconds,
        "series": order(seen),
        "buckets": [
            {
                "label": labels[i],
                "start": edges[i].timestamp(),
                "counts": counts[i],
                "total": sum(counts[i].values()),
            }
            for i in range(len(edges))
        ],
    }


def _mood_order(seen: set[str]) -> list[str]:
    known = [l for l in EMOTION_LABELS if l in seen]
    return known + sorted(seen - set(EMOTION_LABELS))


def mood_timeseries(range_key: str = "hourly") -> dict:
    return _timeseries("emotion", range_key, _mood_order)


def hazard_timeseries(range_key: str = "hourly") -> dict:
    return _timeseries("hazard_alert", range_key, lambda seen: sorted(seen))


def last_summary_ts(kind: str) -> float:
    """kind: 'mood_summary' or 'hazard_alert:<label>' -- used for batching/cooldowns."""
    with _lock:
        row = _conn.execute(
            "SELECT MAX(ts) as ts FROM events WHERE type = ?", (kind,)
        ).fetchone()
    return row["ts"] or 0.0
