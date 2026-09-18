# Vigil

Webcam frames go through small, CPU-only CV models (face + emotion, person
fall, fire/smoke), which write short structured events to SQLite. A small
LLM (Ollama locally, or Groq/Kompact via an OpenAI-compatible endpoint)
turns those events into text: an immediate alert for hazards, a batched
narrative summary for mood. The LLM never sees a frame, only event logs.

**Stack:** Python 3.12 - FastAPI - OpenCV - ONNX Runtime - YOLOv8 - SQLite
- React - Vite

## Features

- **Mood analysis** -- face detection + 8-class emotion classification on
  every sampled frame, aggregated into rolling counts and a periodic
  natural-language summary ("you seemed focused, with a stretch of stress
  around 2pm").
- **Hazard detection** -- fire/smoke (fine-tuned YOLOv8) and a person
  falling (YOLOv8 person detection + a wide-not-tall-for-N-seconds rule),
  each producing an immediate LLM-written alert, not just a raw label.
- **One feed, switchable live** -- starts on your device webcam; upload
  any video through the UI and it loops that clip instead, in place, no
  backend restart. Lets you demo hazards without an actual fire.
- **LLM insight generation, provider-agnostic** -- one OpenAI-compatible
  adapter (`insights.py`) drives Ollama (local, default), Groq, or
  Kompact's runtime interchangeably via a single env var.
- **Live dashboard** -- four tabs (Live / Mood / Hazards / Insights)
  polling a FastAPI backend; MJPEG stream for the video, SQLite-backed
  event feed for everything else.
- **Fails soft** -- every detector and the LLM call independently degrade
  to a safe default (detector disables itself, LLM falls back to a
  template) instead of crashing the pipeline.

## Folder structure

```
backend/
  api.py              FastAPI app: MJPEG stream, source switch/upload, polled events
  pipeline.py         capture loop (1 feed) + detection + LLM triggers
  detectors.py        EmotionDetector, FallDetector, FireDetector
  insights.py         OpenAI-compatible LLM adapter (Ollama/Groq/Kompact)
  store.py            SQLite event log
  config.py           all thresholds, paths, provider config
  download_models.py  fetches the model weights below
  requirements.txt
  models/             downloaded weights (created by download_models.py, gitignored)
  sample_videos/
    uploads/          videos uploaded from the UI land here (created on first
                      upload, gitignored)
frontend/
  src/
    App.jsx             tab shell + status header
    api.js              fetch client
    components/         LiveView, MoodPanel, HazardPanel, InsightPanel,
                        TrendChart
    index.css
```

## One-time setup

```bash
# backend
cd backend
python3.12 -m venv .venv        # project was built against 3.12 -- your
.venv/bin/pip install -r requirements.txt   # system python is 3.14, too new
                                             # for onnxruntime/torch wheels
.venv/bin/python download_models.py

# frontend
cd ../frontend
npm install
```

## Running

```bash
# terminal 1
cd backend && .venv/bin/uvicorn api:app --port 8420

# terminal 2
cd frontend && npm run dev
# open http://localhost:5173
```

Port 8000 was already taken by something else on this machine, so
everything here defaults to **8420**. Change it with `--port` on uvicorn
and `VITE_API_BASE` for the frontend if needed.

## Configuring the LLM provider

Kompact's REST API and Groq are both OpenAI-compatible, and so is Ollama's
`/v1` endpoint -- `insights.py` uses the `openai` SDK against whichever
`base_url`/`api_key`/`model` triple `config.py` resolves. Switch with one
env var, nothing else changes:

```bash
# default: local Ollama, zero setup, already pulled (gemma3:270m)
LLM_PROVIDER=ollama uvicorn api:app --port 8420

# Groq
LLM_PROVIDER=groq GROQ_API_KEY=... uvicorn api:app --port 8420

# Kompact
LLM_PROVIDER=kompact KOMPACT_BASE_URL=... KOMPACT_API_KEY=... KOMPACT_MODEL=... \
  uvicorn api:app --port 8420
```

`gemma3:270m` is genuinely tiny -- good for the "small model on CPU" story,
but swap `OLLAMA_MODEL=qwen2.5:1.5b-instruct` (`ollama pull` it first) if
you want noticeably better prose for the demo.

## One feed, two modes

There's a single video feed. It starts on the live device webcam
(`WEBCAM_INDEX` in `config.py`, default `0`). In the **Live** tab, two
buttons switch what it shows:

- **Webcam** -- back to the live device camera.
- **Upload video (loops)** -- pick any `.mp4`/`.mov`/etc. and the feed
  switches to loop that clip instead, as if the scene in front of the
  camera changed. Uploading a different file later replaces whatever's
  currently looping and starts looping the new one. This is the way to
  demo the hazard detectors without setting an actual fire -- a phone clip
  of a candle flame, played on loop, is enough to show `FireDetector`
  actually fire.

Mechanically: `POST /api/sources/feed/webcam` or
`POST /api/sources/feed/upload` (multipart file) -- `pipeline.py` releases
the current `cv2.VideoCapture` and reopens on the new target without
restarting the process, so switching is a couple hundred milliseconds,
not a server restart. Nothing ships in `sample_videos/` -- bring your own
clip; any short `.mp4` of a candle, a lighter, or smoke is enough to see
`FireDetector` trigger end to end.

## Models -- what's pretrained vs. what's a heuristic

| Stage | Model | Download | Notes |
|---|---|---|---|
| Face detection | YuNet (OpenCV's built-in DNN detector) | `face_yunet.onnx`, ~230KB | OpenCV 5.x dropped the old Haar cascade XMLs from the pip wheel, so this replaces the Haar-cascade plan from earlier discussion -- same idea, better model, still zero extra dependency. |
| Emotion | FER+ (ONNX, 8 classes) | `emotion_ferplus.onnx`, ~35MB | Runs on the YuNet face crop. |
| Fall | YOLOv8n (COCO, class 0 = person) + a hand-written rule | `yolov8n.pt`, ~6.5MB | "Fallen" is not a trained class -- it's the largest person's bbox going wide-not-tall (`FALL_ASPECT_RATIO`) and staying that way for `FALL_STILL_SECONDS`. Simple on purpose: no multi-object tracking. |
| Fire / smoke | YOLOv8, community fine-tune (classes: Fire, Smoke) | `fire_yolov8.pt`, ~546MB | The one real risk in this stack. This checkpoint is a raw training checkpoint (hence the unusually large size for a "nano" model), not a clean weights-only export. `FireDetector` wraps loading in try/except -- if it ever fails on another machine, the backend logs `FireDetector disabled` and keeps running without it rather than crashing. Swap in a Roboflow Universe checkpoint or your own fine-tune if this one underperforms on your footage. |
| Insight LLM | gemma3:270m (already pulled via Ollama) | -- | Swappable, see above. |

Re-run `download_models.py` any time to re-fetch anything missing; it
skips files that already exist.

## Known environment gotcha: camera contention

macOS gives one process real access to the webcam at a time. Any app with
a camera-capable helper process -- Teams, Zoom, FaceTime, and (this one's
easy to miss) **any open Chrome/Brave/Edge window**, since Chromium spins
up its own `video_capture.mojom.VideoCaptureService` helper -- can grab
the device out from under this pipeline. `cv2.VideoCapture` still reports
`isOpened() == True`, but frames come back black or just never arrive
(`GET /api/stream/feed` returns a `200` with the right headers and zero
body bytes). This isn't a bug in `pipeline.py`; it's the OS handing the
device to whichever process asked first, and I hit this twice while
building it -- once from Teams, once from having three Chromium-based
browsers open at once. If the feed goes black or freezes in webcam mode,
close other camera-capable apps and switch back to Webcam mode to
reconnect. The **Upload video** mode is unaffected either way, since it
never touches the camera.

## What still needs you

- **Kompact's actual endpoint** -- wire it up via `KOMPACT_BASE_URL` /
  `KOMPACT_API_KEY` / `KOMPACT_MODEL` once you have credentials. The
  adapter is already proven against two other OpenAI-compatible
  providers (Ollama and Groq's `openai/gpt-oss-120b`), so this should
  just be three env vars, not new code.
- **Real hazard footage** -- upload real fire/smoke or fall clips through
  the UI to test the detectors against something other than a demo loop.
- **Fire model validation** -- confirm `fire_yolov8.pt` actually fires on
  your test footage; it's the one download that wasn't verified beyond
  "loads and reports classes {0: Fire, 1: Smoke}".

## Author

**Ritesh Gond** -- built for the Kompact AI Hackathon.
