import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
DB_PATH = BASE_DIR / "events.db"

load_dotenv(BASE_DIR / ".env")  # local secrets (GROQ_API_KEY etc.) -- gitignored, never hardcoded here

# --- Video source ---
# One feed. It starts on the live device webcam; uploading a video through
# the UI switches it to loop that file instead, as if the scene in front of
# the camera changed. See pipeline.py's set_source_webcam/set_source_file.
WEBCAM_INDEX = int(os.environ.get("WEBCAM_INDEX", "0"))

# --- Model paths ---
FACE_MODEL_PATH = MODEL_DIR / "face_yunet.onnx"
EMOTION_MODEL_PATH = MODEL_DIR / "emotion_ferplus.onnx"
PERSON_MODEL_PATH = MODEL_DIR / "yolov8n.pt"
FIRE_MODEL_PATH = MODEL_DIR / "fire_yolov8.pt"

# --- Pipeline timing ---
DISPLAY_FPS = 12  # frames/sec streamed to the frontend
DETECT_INTERVAL_SEC = 1.0  # how often detectors run per source
BATCH_SUMMARY_INTERVAL_SEC = 90  # mood insight cadence
HAZARD_COOLDOWN_SEC = 30  # don't re-alert the same hazard type faster than this

# --- Detection thresholds ---
FACE_CONF_THRESHOLD = 0.7
EMOTION_CONF_THRESHOLD = 0.4
HAZARD_CONF_THRESHOLD = 0.55
FALL_ASPECT_RATIO = 1.3  # bbox width/height above this looks "lying down"
FALL_STILL_SECONDS = 4.0  # must hold that pose this long to count as a fall

EMOTION_LABELS = [
    "neutral", "happy", "surprise", "sad",
    "angry", "disgust", "fear", "contempt",
]

# --- LLM (OpenAI-compatible) ---
# Works with Kompact's REST API, Groq, or a local Ollama server -- same
# client shape, only base_url/api_key/model change. See insights.py.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")  # ollama | groq | kompact

LLM_PROVIDERS = {
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",  # unused by ollama, the SDK just requires a value
        "model": os.environ.get("OLLAMA_MODEL", "gemma3:270m"),
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        "model": os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant"),
    },
    "kompact": {
        "base_url": os.environ.get("KOMPACT_BASE_URL", ""),
        "api_key": os.environ.get("KOMPACT_API_KEY", ""),
        "model": os.environ.get("KOMPACT_MODEL", ""),
    },
}
