from typing import Optional
from PyQt6.QtWidgets import QMessageBox, QWidget


def prompt_cache_conflict(parent: Optional[QWidget], folder_name: str, lang_display: str, page_desc: str) -> str:
    """
    Prompts the user when pre-existing translation cache is detected for a chapter.
    Returns one of:
      - 'text_only': Re-translate dialogue text using existing OCR / bubble contours.
      - 'full': Re-scan speech bubbles and run OCR from scratch.
      - 'skip': Skip already translated pages and only process untranslated ones.
      - 'cancel': Abort queue start.
    """
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("Translation Cache Found")
    msg_box.setText(
        f"Translation ({lang_display}) data already exists for {page_desc} in '{folder_name}'.\n\n"
        "How would you like to proceed?"
    )
    msg_box.setStyleSheet("""
        QMessageBox {
            background-color: #1e1e24;
            color: #f1f5f9;
        }
        QLabel {
            color: #f1f5f9;
            font-size: 13px;
        }
        QPushButton {
            background-color: #27272a;
            color: #f1f5f9;
            border: 1px solid #3f3f46;
            border-radius: 4px;
            padding: 6px 14px;
            font-size: 12px;
        }
        QPushButton:hover {
            background-color: #3f3f46;
        }
    """)

    btn_retranslate = msg_box.addButton("Re-translate Text (Keep OCR)", QMessageBox.ButtonRole.AcceptRole)
    btn_retranslate.setToolTip("Fast: Keeps speech bubble segmentation and Japanese OCR, only re-sending dialogue to LLM.")

    btn_skip = msg_box.addButton("Skip Translated", QMessageBox.ButtonRole.RejectRole)
    btn_skip.setToolTip("Only translates pages that do not yet have translations.")

    btn_full = msg_box.addButton("Re-scan Everything", QMessageBox.ButtonRole.DestructiveRole)
    btn_full.setToolTip("Slow: Purges all cache to re-run speech bubble detection and MangaOCR from scratch.")

    btn_cancel = msg_box.addButton("Cancel", QMessageBox.ButtonRole.ActionRole)

    msg_box.setDefaultButton(btn_retranslate)
    msg_box.exec()

    clicked = msg_box.clickedButton()
    if clicked == btn_retranslate:
        return "text_only"
    if clicked == btn_full:
        return "full"
    if clicked == btn_skip:
        return "skip"
    return "cancel"
