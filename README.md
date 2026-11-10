# Windows Folder Image Previewer

Windows Folder Image Previewer is a desktop application designed for fast manga reading, effortless library organization, and intelligent on-screen translation. Whether you are navigating massive multi-chapter folders or organizing messy image archives, it delivers a smooth, distraction-free reading experience with powerful folder management tools built right in.

## Read Raw Manga with Clean, Non-Destructive Overlays

Unlike traditional translation tools that blur or redraw your pages, this app leaves your original manga artwork completely untouched. The AI simply analyzes the page and returns dialogue text with position coordinates in JSON format. The app then paints sharp, vector-quality text right over the speech bubbles on your screen. You can tap the T key at any time to instantly switch between the translated dialogue and the original Japanese artwork.

To fit your budget and hardware, the app offers two flexible translation modes:

1. **Token-Efficient Mode (Local Detection + Text LLM)**
   Best for reading large volume batches on a budget. Speech bubble detection (ONNX Runtime) and Japanese text reading (Manga OCR) run entirely on your local machine. Because only extracted dialogue text is sent to your configured OpenAI-compatible API, token consumption is kept minimal.
   
   Measured benchmark on a sample manga page using `deepseek-v4.1-flash`:
   - Prompt Tokens: 2,347
   - Completion Tokens: 155
   - Total Tokens: 2,502
   
   Because text dialogue from multiple pages can be bundled into a single batch request, token efficiency compounds significantly across entire chapters compared to sending individual image payloads. This mode runs comfortably on standard consumer laptops without needing high-end graphics cards.

2. **Highest Quality Mode (Local ONNX Segmentation + Vision LLM)**
   Best for story-rich chapters where emotional nuance and visual context matter. Speech bubble geometry and whitewash masks are precisely extracted locally using ONNX Runtime and OpenCV to prevent coordinate drift. The compressed WebP page and bubble bounds are then sent to vision-capable models (such as Gemini, GPT-4o, or local vision runners). The AI reads dialogue directly in scene context, effortlessly understands character expressions and reading order, and eliminates OCR transcription typos.
   
   Measured benchmark on the same sample page using `deepseek-v4.1-flash`:
   - Prompt Tokens: 3,013 (+666 tokens for the WebP image and vision instructions)
   - Completion Tokens: 689 (returning dialogue mapped to detected bubbles)
   - Total Tokens: 3,702
   
   On a single page, visual hybrid translation uses approximately 48 percent more total tokens and 4.4 times more completion tokens than the hybrid text mode. Each page requires its own image payload, trading higher token usage for maximum visual and contextual translation accuracy.

## Features

- **Local Manga Reader / Image Viewer**: Enjoy a smooth, distraction-free reading experience with fullscreen support, continuous cross-folder rollover, persistent zoom presets, and asynchronous image loading for peak performance.
- **Sub-folder Discovery**: Automatically scan and index complex root directories to find every image-containing sub-folder, remembering your last opened library location across sessions.
- **Batch Rename**: Speed up your library cleanup with quick, in-place folder renaming and convenient batch disk operations directly within the workspace.
- **Translation**: An adaptable localization pipeline featuring both a token-saving hybrid mode (using ONNX Runtime, OpenCV, Manga OCR, and OpenAI text APIs) and a context-aware visual hybrid mode (combining ONNX bubble geometry with Vision LLM reading). Measured single-page benchmarks show 2,502 total tokens for hybrid text translation versus 3,702 total tokens for visual hybrid translation, giving users direct control over API expenditure versus contextual visual precision.

## Architecture

The codebase follows a Ports & Adapters (hexagonal-lite) architecture mechanically validated on every test run by `import-linter`:

```
ui  →  viewmodels  →  services  →  ports  ←  infra
                                        ↑
                                     models
```

- **`src/models/`**: Pure domain data models with zero external or Qt dependencies (`FolderItem`, `PageTranslation`, `BubbleBlock`, `TranslationJob`).
- **`src/ports/`**: Pure `typing.Protocol` contracts defining seams (`PageRepository`, `TranslationProvider`, `LogSink`, `ComicTextRenderer`).
- **`src/services/`**: Headless business logic, directory scanners, and typography layout math (`comic_text.py`, `folder_service.py`, `trash_service.py`, `manga_ocr_detector.py`). Strictly headless with zero `PyQt6.QtWidgets` imports.
- **`src/infra/`**: Outside-world adapters implementing ports (`json_workspace.py`, `file_log_sink.py`, `qt_comic_renderer.py`, `image_rasterizer.py`).
- **`src/viewmodels/`**: Headless presentation logic (`SettingsViewModel`, `LibraryViewModel`, `TranslationViewModel`) binding UI to services without widget dependencies.
- **`src/ui/`**: PyQt6 presentation layer and custom widgets. Contains zero direct disk I/O or network requests.

## Installation & Local Run

```bash
git clone https://github.com/miftahulmuhaemen/win-folder-thumbnail.git
cd win-folder-thumbnail
pip install -r requirements.txt
python src/main.py
```

## Running Tests

```bash
QT_QPA_PLATFORM=offscreen pytest
```

## License

MIT
