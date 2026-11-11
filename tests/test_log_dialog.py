from pathlib import Path
from src.ui.log_dialog import LogDialog

def test_log_dialog_display(qtbot, tmp_path: Path):
    log_file = tmp_path / "translation.log"
    log_file.write_text("Line 1: Started\nLine 2: Finished", encoding="utf-8")

    dialog = LogDialog(log_path=log_file)
    qtbot.addWidget(dialog)

    assert "Line 1: Started" in dialog.log_text_edit.toPlainText()
    assert "Line 2: Finished" in dialog.log_text_edit.toPlainText()

def test_log_dialog_missing_file(qtbot, tmp_path: Path):
    log_file = tmp_path / "non_existent.log"
    dialog = LogDialog(log_path=log_file)
    qtbot.addWidget(dialog)

    assert "No log file found" in dialog.log_text_edit.toPlainText()
