"""CV detectors. Each one is self-contained and fails soft: if a model can't
load, the detector reports itself unavailable instead of crashing the pipeline.
"""
import time

import cv2
import numpy as np

import config


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


class EmotionDetector:
    """YuNet (OpenCV's built-in DNN face detector) finds the face; FERPlus
    (ONNX) classifies the crop into one of 8 emotions. OpenCV 5.x dropped the
    old Haar cascade XML files from the pip wheel, so YuNet is the
    zero-extra-dependency option -- it ships as part of cv2 itself, only the
    small ONNX weight file needs downloading."""

    def __init__(self):
        self.available = False
        self._last_size: tuple[int, int] | None = None
        try:
            import onnxruntime as ort

            self.face_detector = cv2.FaceDetectorYN.create(
                str(config.FACE_MODEL_PATH), "", (320, 320), score_threshold=0.7
            )
            self.session = ort.InferenceSession(str(config.EMOTION_MODEL_PATH), providers=["CPUExecutionProvider"])
            self.input_name = self.session.get_inputs()[0].name
            self.available = True
        except Exception as e:
            print(f"[detectors] EmotionDetector disabled: {e}")

    def detect(self, frame: np.ndarray) -> list[dict]:
        if not self.available:
            return []
        h, w = frame.shape[:2]
        if self._last_size != (w, h):
            self.face_detector.setInputSize((w, h))
            self._last_size = (w, h)

        _, faces = self.face_detector.detect(frame)
        if faces is None or len(faces) == 0:
            return []
        fx, fy, fw, fh = faces[0][:4].astype(int)
        fx, fy = max(fx, 0), max(fy, 0)
        fw, fh = max(fw, 1), max(fh, 1)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        crop = cv2.resize(gray[fy : fy + fh, fx : fx + fw], (64, 64)).astype(np.float32)
        inp = crop.reshape(1, 1, 64, 64)
        scores = self.session.run(None, {self.input_name: inp})[0][0]
        probs = _softmax(scores)
        idx = int(np.argmax(probs))
        conf = float(probs[idx])
        if conf < config.EMOTION_CONF_THRESHOLD:
            return []
        return [
            {
                "label": config.EMOTION_LABELS[idx],
                "confidence": conf,
                "bbox": [int(fx), int(fy), int(fx + fw), int(fy + fh)],
            }
        ]


class FallDetector:
    """YOLOv8n (COCO, class 0 = person). Fall is a heuristic on top, not a
    trained classifier: the largest person in frame goes wide-not-tall and
    stays that way for FALL_STILL_SECONDS."""

    def __init__(self):
        self.available = False
        self._down_since: dict[str, float | None] = {}
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(config.PERSON_MODEL_PATH))
            self.available = True
        except Exception as e:
            print(f"[detectors] FallDetector disabled: {e}")

    def detect(self, frame: np.ndarray, source: str) -> list[dict]:
        if not self.available:
            return []
        results = self.model.predict(frame, classes=[0], conf=0.5, verbose=False)[0]
        boxes = results.boxes.xyxy.cpu().numpy() if len(results.boxes) else np.empty((0, 4))
        if len(boxes) == 0:
            self._down_since[source] = None
            return []
        confs = results.boxes.conf.cpu().numpy()
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        idx = int(areas.argmax())
        x1, y1, x2, y2 = boxes[idx]
        aspect = (x2 - x1) / max(y2 - y1, 1e-6)

        now = time.time()
        if aspect <= config.FALL_ASPECT_RATIO:
            self._down_since[source] = None
            return []

        if self._down_since.get(source) is None:
            self._down_since[source] = now
        elapsed = now - self._down_since[source]
        if elapsed < config.FALL_STILL_SECONDS:
            return []
        return [
            {
                "label": "person_down",
                "confidence": float(confs[idx]),
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
            }
        ]


class FireDetector:
    """YOLOv8 fine-tuned on a fire/smoke dataset. The checkpoint is the
    riskiest download in this stack -- if it fails to load or its class
    names look wrong, this detector disables itself rather than crash."""

    def __init__(self):
        self.available = False
        self.class_names: dict[int, str] = {}
        try:
            from ultralytics import YOLO

            self.model = YOLO(str(config.FIRE_MODEL_PATH))
            self.class_names = self.model.names
            self.available = True
            print(f"[detectors] FireDetector loaded, classes={self.class_names}")
        except Exception as e:
            print(f"[detectors] FireDetector disabled: {e}")

    def detect(self, frame: np.ndarray) -> list[dict]:
        if not self.available:
            return []
        results = self.model.predict(frame, conf=config.HAZARD_CONF_THRESHOLD, verbose=False)[0]
        out = []
        for box, conf, cls in zip(
            results.boxes.xyxy.cpu().numpy(),
            results.boxes.conf.cpu().numpy(),
            results.boxes.cls.cpu().numpy(),
        ):
            out.append(
                {
                    "label": self.class_names.get(int(cls), str(int(cls))),
                    "confidence": float(conf),
                    "bbox": [float(v) for v in box.tolist()],
                }
            )
        return out
