import pytest
from unittest.mock import patch, MagicMock
from src.ui.cache_conflict_dialog import prompt_cache_conflict


@pytest.mark.parametrize("target_btn_idx, expected", [
    (0, "text_only"),
    (1, "skip"),
    (2, "full"),
    (3, "cancel"),
])
def test_prompt_cache_conflict_options(target_btn_idx, expected):
    with patch("src.ui.cache_conflict_dialog.QMessageBox") as mock_box_cls:
        buttons = []
        mock_box = MagicMock()
        mock_box.addButton.side_effect = lambda text, role: buttons.append(MagicMock()) or buttons[-1]
        mock_box.exec.side_effect = lambda: setattr(mock_box, "_clicked", buttons[target_btn_idx])
        mock_box.clickedButton.side_effect = lambda: getattr(mock_box, "_clicked", None)
        mock_box_cls.return_value = mock_box

        res = prompt_cache_conflict(None, "chapter1", "EN", "1 of 2 images")
        assert res == expected
