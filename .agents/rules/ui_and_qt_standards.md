---
trigger: always_on
description: PyQt6 UI design standards, dark theme palette, keyboard navigation invariants, continuous reading flow, comic typography, and translation overlay rendering.
---

# UI & PyQt6 Desktop Application Standards

Strict design, component hierarchy, keyboard navigation, and comic typography standards for the Windows Folder Image Previewer.

---

## 1. PyQt6 Dark Theme Palette & Widget Consistency

1. **Consistent Neutral Dark Palette**:
   - All windows, dialogs, lists, and overlays must adhere to the established dark aesthetic:
     - Window / Viewport Background: `#1e1e1e`
     - Panel / Sidebar / Toolbar: `#252526`
     - Item Selection (Focused): `#094771`
     - Item Selection (Unfocused): `#37373d`
     - Borders & Separators: `#3c3c3c`
     - Primary Text: `#ffffff` or `#cccccc`
     - Muted Text / Badges: `#858585`
2. **Universal Dialog Styling**:
   - Modal dialogs (`SettingsDialog`, `LogDialog`, `QueueDialog`, `BatchRenameDialog`, `RenameDialog`) must inherit the application stylesheet and maintain consistent font scales, button alignments, and dark backgrounds.
   - White or unstyled default Qt widgets are strictly prohibited.
3. **Empty States & Zero Artifacts**:
   - Empty lists or viewports must render helpful centered text ("No images found in folder" or "Select a folder to begin") rather than bare white canvases.

---

## 2. Keyboard Navigation & Continuous Reading Invariants

1. **Continuous Reading Navigation**:
   - `Left` / `Right` arrows must navigate previous/next images seamlessly.
   - **Cross-Folder Rollover Invariant**:
     - Advancing past the final image in a folder must automatically select the next folder and display its first image.
     - Moving backward past the first image must select the previous folder and display its final image.
     - Seamless rollover must never raise index errors or desynchronize the folder list selection.
2. **Direct Folder Navigation**:
   - `Up` / `Down` arrows move selection across folders in `FolderList`.
3. **Fullscreen Reading Mode (`F12` / `Escape`)**:
   - `F12` toggles fullscreen mode. In fullscreen mode, window chrome, menu bars, folder tree, and thumbnail strip are hidden, devoting the entire display to the image.
   - `Escape` exits fullscreen mode and restores previous window geometry, scroll position, and panel visibility.
4. **Persistent Zoom Presets**:
   - Zoom presets: `Fit`, `50%`, `75%`, `100%`, `120%`.
   - Keyboard shortcuts: `Ctrl` + `+` / `Ctrl` + `=` (Zoom In), `Ctrl` + `-` (Zoom Out).
   - The selected zoom factor must persist across folder transitions and application restarts via `QSettings`.

---

## 3. Image Rendering & Aspect Ratio Standards

1. **Strict Aspect Ratio Preservation**:
   - Image scaling in `PreviewPane` must strictly enforce `Qt.AspectRatioMode.KeepAspectRatio`. Anisotropic stretching or squishing is strictly prohibited.
2. **Smooth Transformation**:
   - All image decodes and downscales must use `Qt.TransformationMode.SmoothTransformation` to eliminate aliasing and jagged edges during zoom or thumbnail generation.

---

## 4. Comic Typography & Translation Overlay Standards

1. **Intelligent Inpainting & Bubble Contours**:
   - Speech bubble whitening must respect morphological boundaries (`cv2.morphologyEx` and floodfill).
   - Inpainting must never bleed into surrounding character artwork or panel borders.
2. **Dynamic Typography Engine**:
   - Line wrapping and font point size must dynamically fit within the computed bubble bounding polygon.
   - Long words must support hyphenation via `pyphen` to prevent orphaned words or text overflow.
   - Text blocks must center around the true bubble centroid computed via image moments (`cv2.moments`).
3. **Interactive Inspection Canvas**:
   - Pressing `T` toggles the translation overlay on and off instantaneously.
   - Hovering over a translated bubble must present an inspection tooltip showing the original Japanese OCR transcription and bubble ID.
