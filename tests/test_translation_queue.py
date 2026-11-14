from pathlib import Path
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import Qt
from src.models.translation_job import TranslationJob, JobStatus, JobType
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
        mock_worker.isRunning.return_value = False
        mock_worker_cls.return_value = mock_worker

        assert dialog.start_btn.isEnabled()
        with qtbot.waitSignal(qm.queue_state_changed, timeout=5000):
            dialog.start_btn.click()
        assert qm.is_running is True
        assert "Pause" in dialog.start_btn.text()

        dialog.start_btn.click()
        assert qm.is_running is False
        assert "Start" in dialog.start_btn.text() or "Resume" in dialog.start_btn.text()


def test_translation_job_page_selection_helpers():
    p1 = Path("/tmp/ch1/01.png")
    p2 = Path("/tmp/ch1/02.png")
    p3 = Path("/tmp/ch1/03.png")

    job = TranslationJob(
        folder_path=Path("/tmp/ch1"),
        folder_name="ch1",
        image_paths=[p1, p2, p3],
        target_lang="en"
    )

    # Defaults to all selected
    assert job.selected_count == 3
    assert job.total_count == 3
    assert job.is_image_selected(p1) is True

    # Unselect all
    job.unselect_all()
    assert job.selected_count == 0
    assert job.is_image_selected(p1) is False

    # Select single
    job.select_single(p2)
    assert job.selected_count == 1
    assert job.selected_image_paths == [p2]

    # Toggle
    job.toggle_image(p3, True)
    assert job.selected_count == 2
    assert job.selected_image_paths == [p2, p3]

    job.toggle_image(p2, False)
    assert job.selected_count == 1
    assert job.selected_image_paths == [p3]

    # Select all
    job.select_all()
    assert job.selected_count == 3


def test_queue_manager_rasterize_job():
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    p1 = Path("/tmp/ch1")
    job = qm.add_rasterize_job(p1, [p1 / "01.png"], target_lang="en")

    assert job.job_type == JobType.RASTERIZE
    assert job.output_dir == Path("/tmp/ch1_translated")
    assert len(qm.jobs) == 1


def test_queue_dialog_pages_sorting(qtbot, tmp_path):
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    ch_dir = tmp_path / "chapter_sort_test"
    ch_dir.mkdir()

    # Create dummy images: 1.webp, 2.webp, 10.webp, 100.webp
    p1 = ch_dir / "1.webp"
    p2 = ch_dir / "2.webp"
    p10 = ch_dir / "10.webp"
    p100 = ch_dir / "100.webp"
    for p in (p1, p2, p10, p100):
        p.touch()

    # Unordered list to start
    qm.add_job(ch_dir, [p100, p1, p10, p2], target_lang="en")

    dialog = QueueDialog(qm)
    qtbot.addWidget(dialog)
    dialog.list_widget.setCurrentRow(0)

    # By default, sort combo is at index 0: natural_asc
    assert dialog.pages_sort_combo.currentData() == "natural_asc"
    job = qm.jobs[0]
    assert [p.name for p in job.image_paths] == ["1.webp", "2.webp", "10.webp", "100.webp"]
    assert dialog.pages_list.item(0).text().startswith("1.webp")
    assert dialog.pages_list.item(1).text().startswith("2.webp")
    assert dialog.pages_list.item(2).text().startswith("10.webp")
    assert dialog.pages_list.item(3).text().startswith("100.webp")

    # Change to natural_desc
    idx_desc = dialog.pages_sort_combo.findData("natural_desc")
    dialog.pages_sort_combo.setCurrentIndex(idx_desc)
    assert [p.name for p in job.image_paths] == ["100.webp", "10.webp", "2.webp", "1.webp"]
    assert dialog.pages_list.item(0).text().startswith("100.webp")
    assert dialog.pages_list.item(3).text().startswith("1.webp")


def test_queue_dialog_page_selection_ui(qtbot):
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    p1 = Path("/tmp/ch1")
    img1 = p1 / "01.png"
    img2 = p1 / "02.png"
    job = qm.add_job(p1, [img1, img2], target_lang="en")

    dialog = QueueDialog(qm)
    qtbot.addWidget(dialog)

    # Select job row
    dialog.list_widget.setCurrentRow(0)

    # Pages list should have 2 items, both checked
    assert dialog.pages_list.count() == 2
    assert "Selected: 2 / 2 pages" in dialog.pages_count_label.text()
    assert dialog.pages_list.item(0).checkState() == Qt.CheckState.Checked
    assert dialog.pages_list.item(1).checkState() == Qt.CheckState.Checked

    # Click Unselect All
    dialog.btn_unselect_all.click()
    assert job.selected_count == 0
    assert dialog.pages_list.item(0).checkState() == Qt.CheckState.Unchecked
    assert dialog.pages_list.item(1).checkState() == Qt.CheckState.Unchecked
    assert "Selected: 0 / 2 pages" in dialog.pages_count_label.text()

    # Click Select All
    dialog.btn_select_all.click()
    assert job.selected_count == 2
    assert dialog.pages_list.item(0).checkState() == Qt.CheckState.Checked

    # Uncheck first page manually
    dialog.pages_list.item(0).setCheckState(Qt.CheckState.Unchecked)
    assert job.selected_count == 1
    assert job.selected_image_paths == [img2]
    assert dialog.pages_list.item(0).checkState() == Qt.CheckState.Unchecked
    assert dialog.pages_list.item(1).checkState() == Qt.CheckState.Checked


def test_queue_manager_requeues_failed_images():
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    p1 = Path("/tmp/ch1")
    img1 = p1 / "56.webp"
    img2 = p1 / "57.webp"
    img3 = p1 / "70.webp"
    job = qm.add_job(p1, [img1, img2, img3], target_lang="en")

    # Simulate worker finishing with failed images (56.webp and 70.webp)
    mock_worker = MagicMock()
    mock_worker.failed_image_paths = [img1, img3]
    qm._current_job = job
    qm._current_worker = mock_worker

    qm._on_worker_finished(success=True, message="Completed with 2 failed pages")

    # Current job marked completed with retry note
    assert job.status == JobStatus.COMPLETED
    assert "re-queued" in job.status_message

    # A new retry job should have been added
    assert len(qm.jobs) == 2
    retry_job = qm.jobs[1]
    assert retry_job.status == JobStatus.PENDING
    assert retry_job.selected_image_paths == [img1, img3]
    assert retry_job.retry_count == 1
    assert "Retry" in retry_job.folder_name


def test_queue_manager_stops_requeuing_after_max_retries():
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    p1 = Path("/tmp/ch1")
    img1 = p1 / "56.webp"
    job = qm.add_job(p1, [img1], target_lang="en")
    job.retry_count = 2  # Already reached max_retries (default 2)

    mock_worker = MagicMock()
    mock_worker.failed_image_paths = [img1]
    qm._current_job = job
    qm._current_worker = mock_worker

    qm._on_worker_finished(success=False, message="Visual translation timed out")

    # Should not re-queue again
    assert len(qm.jobs) == 1
    assert job.status == JobStatus.FAILED


def test_queue_dialog_manual_label_tag(tmp_path: Path, qtbot):
    from src.models.translation_item import BubbleBlock, PageTranslation
    from src.infra.json_workspace import JsonTempWorkspace as TranslationWorkspace

    ws = TranslationWorkspace(tmp_path)
    # Page 1: cached translation
    b1 = BubbleBlock("p1_b1", (0, 0, 50, 50), "はい", text_en="Yes")
    ws.save_page_ocr(PageTranslation("01.png", 800, 1200, [b1]))
    ws.save_translations({"p1_b1": "Yes"}, target_lang="en")

    # Page 2: manual label awaiting queue translation
    b2 = BubbleBlock("p2_b1", (10, 10, 60, 60), "當然不行!", text_en="", is_manual=True)
    ws.save_page_ocr(PageTranslation("02.png", 800, 1200, [b2]))

    img1 = tmp_path / "01.png"
    img2 = tmp_path / "02.png"
    img1.touch()
    img2.touch()

    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    job = qm.add_job(tmp_path, [img1, img2], target_lang="en")

    dialog = QueueDialog(qm)
    qtbot.addWidget(dialog)
    dialog.list_widget.setCurrentRow(0)

    # 01.png should be tagged [Cached to EN]
    # 02.png should be tagged [Manual Label] [to EN] and checked
    assert "[Cached to EN]" in dialog.pages_list.item(0).text()
    assert "[Manual Label] [to EN]" in dialog.pages_list.item(1).text()
    assert dialog.pages_list.item(1).checkState() == Qt.CheckState.Checked


def test_queue_dialog_ui_fixes(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    img1.touch()

    # Pre-populate log file
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    log_file = temp_dir / "translation.log"
    log_file.write_text("Sample activity log entry\n", encoding="utf-8")

    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    job = qm.add_job(tmp_path, [img1], target_lang="en")

    dialog = QueueDialog(qm)
    qtbot.addWidget(dialog)
    dialog.list_widget.setCurrentRow(0)

    # 1. Horizontal scrollbar must be off
    assert dialog.list_widget.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

    # 2. Tooltip must only show folder name, NOT the folder path
    list_item = dialog.list_widget.item(0)
    assert list_item.toolTip() == job.folder_name
    assert str(tmp_path) not in list_item.toolTip()

    item_widget = dialog.list_widget.itemWidget(list_item)
    assert item_widget.toolTip() == job.folder_name
    assert str(tmp_path) not in item_widget.toolTip()
    assert item_widget.progress_bar.maximumWidth() == 280

    # 3. Tab label
    tab_titles = [dialog.tab_widget.tabText(i) for i in range(dialog.tab_widget.count())]
    assert "API & Translation" in tab_titles or "API && Translation" in tab_titles

    # 4. Activity log and Clear Logs button
    dialog.open_tab("log")
    assert "Sample activity log entry" in dialog.log_edit.toPlainText()
    assert hasattr(dialog, "clear_logs_btn")
    dialog.clear_logs_btn.click()
    assert dialog.log_edit.toPlainText() == ""
    assert log_file.read_text(encoding="utf-8") == ""

    # 5. Hover thumbnail popup exists
    assert hasattr(dialog, "hover_popup")
    assert dialog.pages_list.hasMouseTracking() is True


def test_queue_manager_cancel_and_state_changed():
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    p = Path("/tmp/ch1")
    job = qm.add_job(p, [p / "01.png"])

    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    qm._current_job = job
    qm._current_worker = mock_worker
    qm._is_running = True

    states = []
    qm.queue_state_changed.connect(lambda s: states.append(s))

    qm.stop_queue()
    assert qm.is_running is False
    assert mock_worker.requestInterruption.call_count == 1
    assert states == [False]


def test_queue_manager_extracts_custom_ocr_and_acceleration_credentials():
    # 12-tuple from settings_getter
    getter_12 = lambda: (
        "key", "url", "model", 400, 10, "hybrid", 75, 75, 3, "openai", "custom/ocr-model", True
    )
    qm = TranslationQueueManager(settings_getter=getter_12)
    creds = qm._get_api_credentials()
    assert len(creds) == 12
    assert creds[10] == "custom/ocr-model"
    assert creds[11] is True

    # 10-tuple backward compatibility
    getter_10 = lambda: (
        "key", "url", "model", 400, 10, "hybrid", 75, 75, 3, "openai"
    )
    qm10 = TranslationQueueManager(settings_getter=getter_10)
    creds10 = qm10._get_api_credentials()
    assert len(creds10) == 12
    assert creds10[10] == ""
    assert creds10[11] is False


def test_translation_queue_model_download_interlock(tmp_path):
    qm = TranslationQueueManager()
    folder = tmp_path / "test_folder"
    folder.mkdir()
    img = folder / "01.jpg"
    img.touch()

    job = qm.add_job(folder, [img])
    assert qm.is_model_downloading is False

    # Activate download interlock
    qm.set_model_downloading(True, "Waiting for custom model...")
    assert qm.is_model_downloading is True
    assert job.status_message == "Waiting for custom model..."

    # When starting queue while model is downloading, worker must NOT be started
    qm.start_queue()
    assert qm._current_worker is None

    # Releasing interlock resets pending status message
    qm.set_model_downloading(False)
    assert qm.is_model_downloading is False
    assert job.status_message == "Pending"


def test_translation_queue_pause_and_resume():
    qm = TranslationQueueManager(settings_getter=lambda: ("key", "url", "model"))
    p = Path("/tmp/ch_pause")
    job = qm.add_job(p, [p / "01.png"])

    # Simulate worker cancelled by user
    qm._current_job = job
    qm._on_worker_finished(False, "Cancelled by user")
    assert job.status == JobStatus.PAUSED
    assert job.status_message == "Paused"

    # Start queue should resume paused job to pending
    with patch.object(qm, "_process_next"):
        qm.start_queue()
        assert job.status == JobStatus.PENDING
        assert qm.is_running is True


def test_queue_preflight_worker(tmp_path, qtbot):
    from src.infra.qt_threads import QueuePreflightWorker
    from src.infra.json_workspace import JsonTempWorkspace
    from src.models.translation_item import PageTranslation, BubbleBlock

    folder = tmp_path / "chapter1"
    folder.mkdir()
    img1 = folder / "01.png"
    img2 = folder / "02.png"
    img1.touch()
    img2.touch()

    # Pre-populate translation for img1
    ws = JsonTempWorkspace(folder)
    page1 = PageTranslation("01.png", 400, 600, [BubbleBlock("p1_b1", (0, 0, 10, 10), "こんにちは")])
    ws.save_page_ocr(page1)
    ws.save_translations({"p1_b1": "Hello"}, target_lang="en")

    job = TranslationJob(
        folder_path=folder,
        folder_name="chapter1",
        image_paths=[img1, img2],
        selected_image_paths=[img1, img2],
        target_lang="en"
    )

    worker = QueuePreflightWorker([job])
    conflicts = []
    worker.conflict_found.connect(lambda jid, desc, sel, untrans: conflicts.append((jid, desc, sel, untrans)))

    with qtbot.waitSignal(worker.preflight_finished, timeout=5000):
        worker.start()
    worker.wait()

    assert len(conflicts) == 1
    jid, desc, sel, untrans = conflicts[0]
    assert jid == job.id
    assert "1 of 2 selected image(s)" in desc
    assert len(sel) == 2
    assert len(untrans) == 1
    assert untrans[0] == img2




