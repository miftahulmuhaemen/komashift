from pathlib import Path
from unittest.mock import MagicMock, patch
from src.models.translation_job import TranslationJob, JobStatus
from src.services.translation_queue import TranslationQueueManager
from src.ui.queue_dialog import QueueDialog


def test_translation_job_model():
    job = TranslationJob(
        folder_path=Path("/tmp/manga1"),
        folder_name="manga1",
        image_paths=[Path("/tmp/manga1/01.png"), Path("/tmp/manga1/02.png")],
        target_lang="en"
    )
    assert job.lang_display == "EN"
    assert job.status == JobStatus.PENDING
    assert job.progress_pct == 0

    job.update_progress("Scanning 1/2", 1, 2)
    assert job.progress_pct == 50
    assert job.status_message == "Scanning 1/2"

    job_id = TranslationJob(
        folder_path=Path("/tmp/manga2"),
        folder_name="manga2",
        image_paths=[],
        target_lang="id"
    )
    assert job_id.lang_display == "ID"


def test_queue_manager_add_remove_reorder():
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))

    # Add two jobs
    p1 = Path("/tmp/ch1")
    p2 = Path("/tmp/ch2")
    j1 = qm.add_job(p1, [p1 / "01.png"], target_lang="en")
    j2 = qm.add_job(p2, [p2 / "01.png"], target_lang="id")

    assert len(qm.jobs) == 2
    assert qm.pending_count == 2
    assert qm.jobs[0].folder_name == "ch1"
    assert qm.jobs[1].folder_name == "ch2"

    # Add duplicate should update language, not duplicate item
    qm.add_job(p1, [p1 / "01.png"], target_lang="id")
    assert len(qm.jobs) == 2
    assert qm.jobs[0].target_lang == "id"

    # Reorder
    qm.move_job(0, 1)
    assert qm.jobs[0].folder_name == "ch2"
    assert qm.jobs[1].folder_name == "ch1"

    # Remove
    qm.remove_job(j1.id)
    assert len(qm.jobs) == 1
    assert qm.jobs[0].id == j2.id


def test_queue_dialog_ui(qtbot):
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    p1 = Path("/tmp/ch1")
    qm.add_job(p1, [p1 / "01.png", p1 / "02.png"], target_lang="en")

    dialog = QueueDialog(qm)
    qtbot.addWidget(dialog)

    assert dialog.list_widget.count() == 1
    assert "1 jobs pending" in dialog.pending_label.text()

    # Select job and check inspector summary
    dialog.list_widget.setCurrentRow(0)
    assert "ch1" in dialog.summary_text.text()
    assert "English (EN)" in dialog.summary_text.text()

    # Test toggling queue start/pause with mocked worker
    with patch("src.services.translation_queue.TranslationWorker") as mock_worker_cls:
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker

        assert dialog.start_btn.isEnabled()
        dialog.start_btn.click()
        assert qm.is_running is True
        assert "Pause" in dialog.start_btn.text()

        dialog.start_btn.click()
        assert qm.is_running is False
        assert "Start" in dialog.start_btn.text()
