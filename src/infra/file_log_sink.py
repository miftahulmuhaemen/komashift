import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class FileLogSink:
    """Concrete filesystem adapter implementing LogSink writing to a text log file."""

    def __init__(self, log_file_path: Path):
        self.log_file = Path(log_file_path)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def append(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}\n"
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.error(f"Failed to append to log at {self.log_file}: {e}")

    def read(self) -> str:
        if not self.log_file.exists():
            return ""
        try:
            return self.log_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read log at {self.log_file}: {e}")
            return ""

    def clear(self) -> None:
        if self.log_file.exists():
            try:
                self.log_file.write_text("", encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to clear log at {self.log_file}: {e}")
