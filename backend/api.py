"""FastAPI app: MJPEG live streams, polled event feed, mood/hazard summaries.
Run with: uvicorn api:app --reload --port 8000
"""
import shutil
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import config
import pipeline
import store

UPLOAD_DIR = config.BASE_DIR / "sample_videos" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_VIDEO_EXT = (".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline.start()
    yield
    pipeline.stop()


app = FastAPI(title="Vigil Pipeline API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/status")
def status():
    provider = config.LLM_PROVIDERS[config.LLM_PROVIDER]
    return {
        "sources": list(pipeline.SOURCES),
        "models": pipeline.model_status(),
        "llm_provider": config.LLM_PROVIDER,
        "llm_model": provider["model"],
        "llm_configured": bool(provider["base_url"]),
    }


def _mjpeg_generator(source: str):
    boundary = b"--frame"
    interval = 1.0 / config.DISPLAY_FPS
    while True:
        frame = pipeline.get_frame(source)
        if frame is not None:
            yield boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        time.sleep(interval)


@app.get("/api/stream/{source}")
def stream(source: str):
    if source not in pipeline.SOURCES:
        raise HTTPException(404, f"unknown source '{source}', expected one of {pipeline.SOURCES}")
    return StreamingResponse(_mjpeg_generator(source), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/sources")
def sources():
    return pipeline.get_source_status()


@app.post("/api/sources/{source}/webcam")
def switch_to_webcam(source: str, device: int = 0):
    if source not in pipeline.SOURCES:
        raise HTTPException(404, f"unknown source '{source}'")
    return pipeline.set_source_webcam(source, device=device)


@app.post("/api/sources/{source}/upload")
async def upload_video(source: str, file: UploadFile = File(...)):
    if source not in pipeline.SOURCES:
        raise HTTPException(404, f"unknown source '{source}'")
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix not in ALLOWED_VIDEO_EXT:
        raise HTTPException(400, f"unsupported file type '{suffix}', expected one of {ALLOWED_VIDEO_EXT}")

    dest = UPLOAD_DIR / f"{source}_{int(time.time())}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    return pipeline.set_source_file(source, str(dest), label=file.filename)


@app.get("/api/events")
def get_events(since: float = 0, type: str | None = None, limit: int = 200):
    if since:
        return store.events_since(since, type_=type)
    return store.recent_events(limit=limit, type_=type)


@app.get("/api/mood/stats")
def mood_stats(window_sec: int = 300):
    since = time.time() - window_sec
    return {
        "counts": store.emotion_counts_since(since),
        "summaries": store.recent_events(limit=5, type_="mood_summary"),
    }


@app.get("/api/mood/timeseries")
def mood_timeseries(range: str = "hourly"):
    return store.mood_timeseries(range)


@app.get("/api/hazards")
def hazards(limit: int = 50):
    return {
        "alerts": store.recent_events(limit=limit, type_="hazard_alert"),
        "raw": store.recent_events(limit=limit, type_="hazard_raw"),
    }


@app.get("/api/hazards/timeseries")
def hazard_timeseries(range: str = "hourly"):
    return store.hazard_timeseries(range)
