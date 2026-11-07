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

