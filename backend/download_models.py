"""Downloads the CV model weights used by this project into backend/models/.
Idempotent -- skips files that already exist. Run once after
`pip install -r requirements.txt`.
"""
import urllib.request
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent / "models"

FILES = {
    "face_yunet.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "emotion_ferplus.onnx": "https://huggingface.co/onnxmodelzoo/emotion-ferplus-8/resolve/main/emotion-ferplus-8.onnx",
    "yolov8n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
    "fire_yolov8.pt": "https://huggingface.co/SHOU-ISD/fire-and-smoke/resolve/main/yolov8n_1.pt",
}


def download(name: str, url: str):
    dest = MODEL_DIR / name
    if dest.exists():
        print(f"  {name} already present ({dest.stat().st_size / 1e6:.1f} MB), skipping")
        return
    print(f"  downloading {name} ...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)
    print(f"  done: {name} ({dest.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    print("Downloading model weights into backend/models/\n")
    for name, url in FILES.items():
        download(name, url)
    print(
        "\nNote: fire_yolov8.pt is a community checkpoint (~546MB -- a raw training "
        "checkpoint, not just clean weights). If the backend logs "
        "'FireDetector disabled' at startup, swap this file for a checkpoint from "
        "Roboflow Universe or your own fine-tune; the rest of the pipeline runs fine "
        "without it."
    )
