from pathlib import Path
import sys
import logging
from typing import List, Tuple, Optional, Union, Any

logger = logging.getLogger(__name__)


class OnnxBubbleDetector:
    """
    Local manga speech bubble detector using ONNX Runtime.
    Fast, offline, and produces exact pixel bounding boxes for speech bubbles.
    """
    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = model_path or self._resolve_model_path()
        self._session = None
        self._available = None

    def _resolve_model_path(self) -> Optional[Path]:
        candidates = [
            # PyInstaller bundle path
            Path(getattr(sys, "_MEIPASS", "")) / "assets" / "models" / "comic-text-detector.onnx",
            # Repo source path
            Path(__file__).parent.parent.parent / "assets" / "models" / "comic-text-detector.onnx",
            # Cache directory
            Path.home() / ".cache" / "comic_text_detector" / "comic-text-detector.onnx",
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        if not self.model_path or not self.model_path.is_file():
            self._available = False
            return False

        try:
            import cv2  # noqa: F401
            import numpy as np  # noqa: F401
            import onnxruntime as ort  # noqa: F401
            self._available = True
        except ImportError as e:
            logger.warning(f"ONNX detector dependencies missing: {e}")
            self._available = False

        return self._available

    def _get_session(self):
        if self._session is None and self.is_available():
            import onnxruntime as ort
            opts = ort.SessionOptions()
            # 0 lets ONNX Runtime automatically leverage all available CPU cores
            opts.intra_op_num_threads = 0
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=["CPUExecutionProvider"]
            )
        return self._session

    def detect_bubbles(
        self,
        image_input: Union[Path, str, Any],
        min_score: float = 0.45,
        nms_iou: float = 0.35
    ) -> List[Tuple[int, int, int, int]]:
        """
        Returns list of (x, y, w, h) bounding boxes in original image coordinates,
        ordered in manga reading order (top-to-bottom, right-to-left).
        Accepts Path, str, numpy.ndarray, or PIL.Image.
        """
        if not self.is_available():
            return []

        import cv2
        import numpy as np
        from PIL import Image

        if isinstance(image_input, np.ndarray):
            img = image_input
        elif isinstance(image_input, Image.Image):
            rgb_arr = np.array(image_input.convert("RGB"))
            img = cv2.cvtColor(rgb_arr, cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imread(str(image_input))

        if img is None:
            return []

        orig_h, orig_w = img.shape[:2]
        if orig_w <= 0 or orig_h <= 0:
            return []

        resized = cv2.resize(img, (1024, 1024))
        blob = resized.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))
        blob = np.expand_dims(blob, axis=0)

        session = self._get_session()
        if session is None:
            return []

        outputs = session.run(None, {"images": blob})
        blk = outputs[0][0]

        conf = blk[:, 4] * np.max(blk[:, 5:7], axis=1)
        mask = conf > min_score
        filtered = blk[mask]
        if len(filtered) == 0:
            return []

        boxes, scores = [], []
        for row in filtered:
            cx, cy, w, h = row[:4]
            score = float(row[4] * np.max(row[5:7]))
            x1 = int((cx - w / 2.0) * orig_w / 1024.0)
            y1 = int((cy - h / 2.0) * orig_h / 1024.0)
            x2 = int((cx + w / 2.0) * orig_w / 1024.0)
            y2 = int((cy + h / 2.0) * orig_h / 1024.0)

            x1 = max(0, min(x1, orig_w - 1))
            y1 = max(0, min(y1, orig_h - 1))
            x2 = max(x1 + 1, min(x2, orig_w))
            y2 = max(y1 + 1, min(y2, orig_h))

            bw = x2 - x1
            bh = y2 - y1

            if bw > orig_w * 0.5 and bh < 250:
                continue
            if bw < 10 or bh < 10:
                continue

            boxes.append([x1, y1, bw, bh])
            scores.append(score)

        if not boxes:
            return []

        indices = cv2.dnn.NMSBoxes(boxes, scores, score_threshold=min_score, nms_threshold=nms_iou)
        if len(indices) == 0:
            return []

        filtered_boxes = [tuple(boxes[idx]) for idx in indices.flatten()]
        filtered_boxes.sort(key=lambda b: (b[1] // 160, -b[0]))

        return filtered_boxes
