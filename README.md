# Windows Folder Image Previewer

A fast, lightweight desktop utility to browse and preview images across nested subfolders, navigate smoothly in distraction-free fullscreen reader mode, and manage folders (rename, batch delete to Windows Recycle Bin).

---

## ✨ Features

- 📁 **Instant Subfolder Discovery**: Automatically scans a parent directory and lists all subfolders containing image files.
- 💾 **Persistent Folder State**: Automatically remembers and restores the last opened directory on startup.
- 🖼️ **Distraction-Free Fullscreen Reader (`F12`)**: Hides all surrounding UI chrome for an immersive, uninterrupted image reading experience.
- 🔄 **Continuous Rollover Reading**: Navigating past the last image in a folder automatically moves to the first image of the next folder; navigating backwards before the first image seamlessly opens the last image of the previous folder.
- 🔍 **Persistent Zoom Presets**: Choose between **Fit**, **50%**, **75%**, **100%**, and **120%** zoom levels (using dropdown or `Ctrl + +` / `Ctrl + -`). Zoom settings remain active across folder switches.
- 🎞️ **Horizontal Thumbnail Strip**: Single-row left-to-right thumbnail strip with smooth auto-scrolling.
- ⚡ **Fast Asynchronous Caching**: Background worker threads decode and cache thumbnails smoothly without blocking the GUI.
- 🗑️ **Batch Selection & Safe Deletion**: Multi-select folders (`Ctrl+Click`, `Shift+Click`, `Ctrl+A`) and move them directly to the Windows Recycle Bin (`Delete`). Automatically selects the next immediate folder upon deletion.
- ✏️ **Double-Click Renaming**: Double-click any folder item in the list (or press `F2`) to quickly rename it on disk.

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Left` / `Right` | Move to Previous / Next image (*continuous cross-folder reading*) |
| `Up` / `Down` | Move to Previous / Next folder |
| `F12` / `Escape` | Toggle Distraction-Free Fullscreen Mode |
| `Ctrl` + `+` / `Ctrl` + `=` | Zoom In (Preset cycle: 50% → 75% → 100% → 120%) |
| `Ctrl` + `-` | Zoom Out |
| `Double-Click` or `F2` | Rename active folder |
| `Delete` | Move selected folder(s) to Recycle Bin |
| `Ctrl` + `A` | Select all folders in the list |
| `Ctrl` + `Click` / `Shift` + `Click` | Multi-select folders for batch actions |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- `pip`

### Installation
```bash
git clone https://github.com/miftahulmuhaemen/win-folder-thumbnail.git
cd win-folder-thumbnail
pip install -r requirements.txt
```

### Running Locally
```bash
python src/main.py
```

---

## 🛠️ Building Standalone Windows Executable (.exe)

You can build a standalone single-file `.exe` that runs independently without needing Python installed on the host machine.

### Building via PowerShell on Windows
1. Open PowerShell (`Win + R`, type `powershell`, press Enter).
2. Navigate to the project directory:
   ```powershell
   cd \\wsl$\Ubuntu\home\sahana\Code_Repository\personal\win-folder-thumbnail
   pip install -r requirements.txt
   ```
3. Run the build script:
   ```powershell
   python build.py
   ```
4. The build script automatically increments the version and generates the binary in `dist/`:
   - `dist/FolderImagePreviewer_v1.0.x.exe` (version-stamped)
   - `dist/FolderImagePreviewer.exe` (latest alias)

---

## 🧪 Running Tests

Run the test suite with `pytest`:
```bash
QT_QPA_PLATFORM=offscreen pytest
```

---

## 📄 License

MIT License. Feel free to use and modify!
