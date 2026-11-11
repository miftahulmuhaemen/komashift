from typing import Protocol


class LogSink(Protocol):
    """Port defining logging persistence and inspection contract."""

    def append(self, message: str) -> None:
        """Append a log entry."""
        ...

    def read(self) -> str:
        """Read all log entries as a string."""
        ...

    def clear(self) -> None:
        """Clear all log entries."""
        ...
