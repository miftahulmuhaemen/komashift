import sys
from pathlib import Path

# Ensure project root is in sys.path when invoked directly as python src/main.py
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from src.ui.main_window import MainWindow

def get_app_icon() -> QIcon:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        icon_path = Path(sys._MEIPASS) / "assets" / "icon.png"
    else:
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()

def main():
    app = QApplication(sys.argv)
    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
