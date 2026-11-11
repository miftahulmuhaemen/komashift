from pathlib import Path
from unittest.mock import patch, MagicMock
from src.services.onnx_bubble_detector import OnnxBubbleDetector


def test_onnx_detector_availability():
    detector = OnnxBubbleDetector(model_path=Path("/nonexistent/model.onnx"))
    assert detector.is_available() is False
    assert detector.detect_bubbles(Path("/nonexistent/img.jpg")) == []


def test_onnx_detector_resolve_path():
    detector = OnnxBubbleDetector()
    # If the model file is present in assets/models or ~/.cache, it resolves
    resolved = detector._resolve_model_path()
    assert resolved is None or resolved.is_file()


def test_onnx_detector_mocked_inference(tmp_path: Path):
    from PIL import Image
    import numpy as np

    img_path = tmp_path / "test.png"
    Image.new("RGB", (1000, 1000), color="white").save(img_path)

    detector = OnnxBubbleDetector()
    detector._available = True

    mock_sess = MagicMock()
    # blk shape (1, 64512, 7)
    fake_blk = np.zeros((1, 64512, 7), dtype=np.float32)
    # Set one high confidence box at center (512, 512, 100, 200)
    fake_blk[0, 0] = [512.0, 512.0, 100.0, 200.0, 0.9, 0.05, 0.95]
    mock_sess.run.return_value = [fake_blk]

    with patch.object(detector, "_get_session", return_value=mock_sess):
        boxes = detector.detect_bubbles(img_path)
        assert len(boxes) == 1
        x, y, w, h = boxes[0]
        # Coordinates should scale roughly to 1000x1000
        assert abs(x - 450) <= 20
        assert abs(y - 400) <= 20
        assert abs(w - 100) <= 10
        assert abs(h - 200) <= 10


def test_onnx_detector_memory_inputs():
    from PIL import Image
    import numpy as np

    detector = OnnxBubbleDetector()
    detector._available = True

    mock_sess = MagicMock()
    fake_blk = np.zeros((1, 64512, 7), dtype=np.float32)
    fake_blk[0, 0] = [512.0, 512.0, 100.0, 200.0, 0.9, 0.05, 0.95]
    mock_sess.run.return_value = [fake_blk]

    with patch.object(detector, "_get_session", return_value=mock_sess):
        # 1. Test PIL Image input
        pil_img = Image.new("RGB", (1000, 1000), color="white")
        boxes_pil = detector.detect_bubbles(pil_img)
        assert len(boxes_pil) == 1

        # 2. Test numpy.ndarray input
        arr = np.zeros((1000, 1000, 3), dtype=np.uint8)
        boxes_arr = detector.detect_bubbles(arr)
        assert len(boxes_arr) == 1


def test_onnx_detector_containment_suppression():
    from PIL import Image
    import numpy as np

    detector = OnnxBubbleDetector()
    detector._available = True

    mock_sess = MagicMock()
    fake_blk = np.zeros((1, 64512, 7), dtype=np.float32)
    # Box 1: Parent bubble covering (512, 512, 200, 400)
    fake_blk[0, 0] = [512.0, 512.0, 200.0, 400.0, 0.95, 0.05, 0.95]
    # Box 2: Nested child box inside Box 1 (512, 512, 80, 100) (IoU is small, but IoMin is 1.0)
    fake_blk[0, 1] = [512.0, 512.0, 80.0, 100.0, 0.90, 0.05, 0.95]
    mock_sess.run.return_value = [fake_blk]

    with patch.object(detector, "_get_session", return_value=mock_sess):
        arr = np.zeros((1000, 1000, 3), dtype=np.uint8)
        boxes = detector.detect_bubbles(arr)
        # Child box must be suppressed by IoMin containment deduplication, leaving only 1 parent box
        assert len(boxes) == 1


def test_onnx_detector_provider_selection(tmp_path: Path):
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"dummy")

    # 1. Force CPU
    detector_cpu = OnnxBubbleDetector(model_path=model_file, force_cpu=True)
    with patch("onnxruntime.InferenceSession") as mock_session:
        detector_cpu._get_session()
        assert mock_session.call_count == 1
        _, kwargs = mock_session.call_args
        assert kwargs["providers"] == ["CPUExecutionProvider"]

    # 2. Auto GPU detection with CUDA & DirectML available
    detector_gpu = OnnxBubbleDetector(model_path=model_file, force_cpu=False)
    with patch("onnxruntime.get_available_providers", return_value=["DmlExecutionProvider", "CPUExecutionProvider"]), \
         patch("onnxruntime.InferenceSession") as mock_session_gpu:
        detector_gpu._get_session()
        assert mock_session_gpu.call_count == 1
        _, kwargs_gpu = mock_session_gpu.call_args
        assert kwargs_gpu["providers"] == ["DmlExecutionProvider", "CPUExecutionProvider"]

    # 3. get_detected_providers static method
    with patch("onnxruntime.get_available_providers", return_value=["CUDAExecutionProvider", "CPUExecutionProvider"]):
        providers = OnnxBubbleDetector.get_detected_providers()
        assert "CUDAExecutionProvider" in providers


