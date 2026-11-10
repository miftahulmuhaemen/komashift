from pathlib import Path
from src.infra.file_log_sink import FileLogSink
from src.ports.log_sink import LogSink

def test_file_log_sink_lifecycle(tmp_path: Path):
    log_file = tmp_path / "temp" / "test.log"
    sink: LogSink = FileLogSink(log_file)

    # Initial read
    assert sink.read() == ""

    # Append
    sink.append("Line 1")
    sink.append("Line 2")
    content = sink.read()
    assert "Line 1" in content
    assert "Line 2" in content

    # Clear
    sink.clear()
    assert sink.read() == ""
