"""Capture + detection loop for the single video feed, run in a daemon
thread: read frame, publish latest JPEG for streaming, run detectors on a
throttled interval, write events to SQLite. A second thread turns
accumulated emotion events into a periodic LLM summary. No in-memory
pub/sub -- the frontend polls the API, and SQLite (store.py) is the single
source of truth for events.
"""
import threading
import time
from pathlib import Path

import cv2

import config
import insights
import store
from detectors import EmotionDetector, FallDetector, FireDetector

SOURCES = ("feed",)

emotion_detector = EmotionDetector()
fall_detector = FallDetector()
fire_detector = FireDetector()

_latest_frames: dict[str, bytes] = {}
_frames_lock = threading.Lock()
_last_hazard_alert: dict[str, float] = {}
_threads: list[threading.Thread] = []
_running = False

# The feed's capture target can be switched at runtime (webcam <-> an
# uploaded file). _generation is bumped on every switch so the running
# capture thread knows to release its old VideoCapture and open the new one.
_target_lock = threading.Lock()
_targets: dict[str, dict] = {
    "feed": {"mode": "webcam", "device": config.WEBCAM_INDEX},
}
_generation: dict[str, int] = {"feed": 0}


def model_status() -> dict:
    return {
        "emotion": emotion_detector.available,
        "fall": fall_detector.available,
        "fire": fire_detector.available,
    }


def get_frame(source: str) -> bytes | None:
    with _frames_lock:
        return _latest_frames.get(source)


def get_source_status() -> dict:
    with _target_lock:
        return {s: dict(_targets[s]) for s in SOURCES}


def set_source_webcam(source: str, device: int | None = None) -> dict:
    if source not in SOURCES:
        raise ValueError(f"unknown source '{source}'")
    device = config.WEBCAM_INDEX if device is None else device
    with _target_lock:
        _targets[source] = {"mode": "webcam", "device": device}
        _generation[source] += 1
        return dict(_targets[source])


def set_source_file(source: str, path: str, label: str | None = None) -> dict:
    if source not in SOURCES:
        raise ValueError(f"unknown source '{source}'")
    with _target_lock:
        _targets[source] = {"mode": "file", "path": path, "label": label or Path(path).name}
        _generation[source] += 1
        return dict(_targets[source])


def _open(target: dict) -> cv2.VideoCapture:
    if target["mode"] == "webcam":
        return cv2.VideoCapture(target["device"])
    return cv2.VideoCapture(target["path"])


def _maybe_alert_hazard(source: str, label: str, confidence: float):
    key = f"{source}:{label}"
    now = time.time()
    if now - _last_hazard_alert.get(key, 0.0) < config.HAZARD_COOLDOWN_SEC:
        return
    _last_hazard_alert[key] = now
    text = insights.generate_hazard_alert(label, confidence, source)
    store.add_event(source, "hazard_alert", label, confidence, meta={"text": text})


def _source_loop(source: str):
    with _target_lock:
        target = dict(_targets[source])
        seen_gen = _generation[source]
    cap = _open(target)
    frame_interval = 1.0 / config.DISPLAY_FPS
    last_detect = 0.0

    if not cap.isOpened():
        print(f"[pipeline] could not open source '{source}' ({target}) -- check config.py")

    while _running:
        with _target_lock:
            gen = _generation[source]
        if gen != seen_gen:
            cap.release()
            with _target_lock:
                target = dict(_targets[source])
                seen_gen = _generation[source]
            cap = _open(target)
            with _frames_lock:
                _latest_frames.pop(source, None)
            print(f"[pipeline] source '{source}' switched to {target}")
            if not cap.isOpened():
                print(f"[pipeline] could not open source '{source}' ({target})")
            continue

        ok, frame = cap.read()
        if not ok or frame is None:
            if target["mode"] == "file":
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                time.sleep(0.1)  # guards against a spin loop if the file never opens at all
                continue
            time.sleep(0.5)
            continue

        ok_jpeg, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok_jpeg:
            with _frames_lock:
                _latest_frames[source] = buf.tobytes()

        now = time.time()
        if now - last_detect >= config.DETECT_INTERVAL_SEC:
            last_detect = now
            try:
                for e in emotion_detector.detect(frame):
                    store.add_event(source, "emotion", e["label"], e["confidence"], meta={"bbox": e["bbox"]})
                for e in fall_detector.detect(frame, source):
                    store.add_event(source, "hazard_raw", e["label"], e["confidence"], meta={"bbox": e["bbox"]})
                    _maybe_alert_hazard(source, e["label"], e["confidence"])
                for e in fire_detector.detect(frame):
                    store.add_event(source, "hazard_raw", e["label"], e["confidence"], meta={"bbox": e["bbox"]})
                    _maybe_alert_hazard(source, e["label"], e["confidence"])
            except Exception as ex:
                print(f"[pipeline] detector error on '{source}': {ex}")

        time.sleep(frame_interval)

    cap.release()


def _summary_loop():
    while _running:
        time.sleep(config.BATCH_SUMMARY_INTERVAL_SEC)
        since = store.last_summary_ts("mood_summary") or (time.time() - config.BATCH_SUMMARY_INTERVAL_SEC)
        events = store.events_since(since, type_="emotion")
        window_label = f"{config.BATCH_SUMMARY_INTERVAL_SEC // 60} min"
        text = insights.generate_mood_summary(events, window_label=window_label)
        if text:
            store.add_event("feed", "mood_summary", "summary", 1.0, meta={"text": text, "sample_size": len(events)})


def start():
    global _running
    if _running:
        return
    _running = True
    store.init_db()
    for source in SOURCES:
        t = threading.Thread(target=_source_loop, args=(source,), daemon=True, name=f"capture-{source}")
        t.start()
        _threads.append(t)
    t = threading.Thread(target=_summary_loop, daemon=True, name="summary-loop")
    t.start()
    _threads.append(t)


def stop():
    global _running
    _running = False
