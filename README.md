# Windows Folder Image Previewer

Desktop application for scanning and previewing images across nested directory structures with fullscreen reading support, persistent zoom levels, and folder management actions (renaming, batch deletion to Recycle Bin).

## Features

- **Folder Discovery**: Scans a chosen root directory and lists subfolders containing image files.
- **State Persistence**: Saves the last opened root directory across application restarts using `QSettings`.
- **Fullscreen Reading Mode (`F12`)**: Hides all window controls and panels to show only the image on screen.
- **Continuous Reading Navigation**: Automatically advances to the next folder upon reaching the last image, or returns to the previous folder's final image when navigating backwards from the first image.
- **Zoom Presets**: Supports Fit, 50%, 75%, 100%, and 120% zoom modes. The active zoom factor is preserved when changing folders.
- **Horizontal Thumbnail Strip**: Single-row thumbnail container with horizontal scrolling and automatic active item tracking.
- **Asynchronous Image Loading**: Background worker threads decode and scale thumbnails to maintain UI responsiveness.
- **Batch Selection & Deletion**: Supports multi-selection (`Ctrl`, `Shift`, `Ctrl+A`) and moves selected folders to the Windows Recycle Bin (`Delete`). Automatically selects the next remaining folder.
- **Folder Renaming**: Double-click any folder entry in the list or press `F2` to rename it directly on disk.

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Left` / `Right` | Previous / Next image (continuous cross-folder rollover) |
| `Up` / `Down` | Previous / Next folder |
| `F12` / `Escape` | Toggle Fullscreen Reader Mode |
| `Ctrl` + `+` / `Ctrl` + `=` | Zoom In (Preset cycle: 50% -> 75% -> 100% -> 120%) |
| `Ctrl` + `-` | Zoom Out |
| `Double-Click` or `F2` | Rename selected folder |
| `Delete` | Move selected folder(s) to Recycle Bin |
| `Ctrl` + `A` | Select all folders |
| `Ctrl` + `Click` / `Shift` + `Click` | Multi-select folders |

## Requirements

- Python 3.10+
- `PyQt6`
- `Pillow`
- `Send2Trash`
- `pytest` / `pytest-qt` (for testing)

## Installation & Local Run

```bash
git clone https://github.com/miftahulmuhaemen/win-folder-thumbnail.git
cd win-folder-thumbnail
pip install -r requirements.txt
python src/main.py
```

## Building Executable

To build a standalone Windows binary (`.exe`) using PyInstaller:

```powershell
python build.py
```

`build.py` automatically increments the patch/build version and writes the output files to `dist/`:
- `dist/FolderImagePreviewer_v<version>.exe`
- `dist/FolderImagePreviewer.exe`

## Running Tests

```bash
QT_QPA_PLATFORM=offscreen pytest
```

## License

MIT
