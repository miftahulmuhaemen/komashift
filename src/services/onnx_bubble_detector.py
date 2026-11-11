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
    def __init__(self, model_path: Optional[Path] = None, force_cpu: bool = False):
        if model_path:
            self.model_path = Path(model_path)
        else:
            self.model_path = self._resolve_model_path()
        self.force_cpu = bool(force_cpu)
        self._session = None
        self._available = None

    @staticmethod
    def get_detected_providers() -> List[str]:
        """Returns the list of available ONNX Runtime execution providers."""
        try:
            import onnxruntime as ort
            return ort.get_available_providers()
        except Exception:
            return ["CPUExecutionProvider"]

    def _resolve_model_path(self) -> Optional[Path]:
        from src.services.ai_assets_manager import AiAssetsManager
        return AiAssetsManager().get_comic_model_path()

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
            import os
            import onnxruntime as ort
            opts = ort.SessionOptions()
            # Soft CPU allocation: reserve core headroom for the OS and UI thread
            total_cores = os.cpu_count() or 4
            opts.intra_op_num_threads = max(1, min(4, total_cores - 1))
            opts.inter_op_num_threads = max(1, min(2, total_cores // 2))
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            if self.force_cpu:
                providers = ["CPUExecutionProvider"]
            else:
                available_providers = ort.get_available_providers()
                preferred_providers = [
                    "TensorrtExecutionProvider",
                    "CUDAExecutionProvider",
                    "CoreMLExecutionProvider",
                    "DmlExecutionProvider",
                    "OpenVINOExecutionProvider",
                    "ROCmExecutionProvider",
                    "CPUExecutionProvider",
                ]
                providers = [p for p in preferred_providers if p in available_providers]
                if not providers:
                    providers = ["CPUExecutionProvider"]

            logger.info(f"OnnxBubbleDetector initialized with execution providers: {providers}")
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=opts,
                providers=providers
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

        nms_boxes = [tuple(boxes[idx]) for idx in indices.flatten()]

        # Containment (IoMin) suppression: drop duplicate child boxes largely inside another larger box
        nms_boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
        filtered_boxes = []
        for b in nms_boxes:
            bx, by, bw, bh = b
            b_area = bw * bh
            is_contained = False
            for kx, ky, kw, kh in filtered_boxes:
                ix1 = max(bx, kx)
                iy1 = max(by, ky)
                ix2 = min(bx + bw, kx + kw)
                iy2 = min(by + bh, ky + kh)
                iw = max(0, ix2 - ix1)
                ih = max(0, iy2 - iy1)
                inter_area = iw * ih
                if inter_area > 0 and b_area > 0:
                    io_min = inter_area / float(b_area)
                    if io_min >= 0.65:
                        is_contained = True
                        break
            if not is_contained:
                filtered_boxes.append(b)

        filtered_boxes.sort(key=lambda b: (b[1] // 160, -b[0]))

        return filtered_boxes
