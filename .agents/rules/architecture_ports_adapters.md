---
trigger: always_on
description: Architectural layering rules and placement decision table for Ports & Adapters
---

# Ports & Adapters Architecture & Placement Decision Table

All code added or modified in `win-folder-thumbnail` must strictly conform to Ports & Adapters (hexagonal-lite) architecture with headless ViewModels.

## 1. Six-Tier Package Hierarchy

```
ui  →  viewmodels  →  services  →  ports  ←  infra
                                        ↑
                                     models
```

| Package | Role | Allowed Imports | Forbidden Imports |
|---|---|---|---|
| `src/models/` | Pure dataclasses & serialization | Standard library only | `PyQt6`, `src.infra`, `src.services`, `src.viewmodels`, `src.ui`, `src.ports` |
| `src/ports/` | Pure `typing.Protocol` definitions | `src.models`, standard library | `src.infra`, `src.services`, `src.viewmodels`, `src.ui`, `PyQt6` |
| `src/services/` | Headless business logic & transformers | `src.models`, `src.ports`, standard library | `PyQt6.QtWidgets`, `src.infra`, `src.viewmodels`, `src.ui` |
| `src/infra/` | Adapters for disk, network, ONNX, QPainter | `src.models`, `src.ports`, `src.services`, PyQt6 | `src.ui`, `src.viewmodels` |
| `src/viewmodels/` | Widget-free UI state & presentation logic | `src.models`, `src.ports`, `src.services`, `PyQt6.QtCore` (`QObject`, `pyqtSignal`, `QSettings`) | `PyQt6.QtWidgets`, `PyQt6.QtGui`, `src.ui` |
| `src/ui/` | PyQt6 widgets, dialogs, paint events | `src.viewmodels`, `src.models`, `src.ports`, PyQt6 | Direct filesystem I/O (`open`, `Path.read_text`), direct network requests |

## 2. Placement Decision Table

| If the new code... | It goes in | Never in |
|---|---|---|
| Reads/writes a file, socket, or external model | `infra/` behind a `ports/` Protocol | `ui/`, `services/`, `viewmodels/` |
| Names a Qt widget class (`QWidget`, `QDialog`, `QMessageBox`) | `ui/` | `services/`, `ports/`, `models/`, `viewmodels/` |
| Names `QThread`, `QRunnable`, `QThreadPool` | `infra/` | `services/`, `ports/`, `models/` |
| Contains orchestration/sequencing of injected collaborators | `services/` or a ViewModel | `ui/` |
| Is pure computation over data (text wrapping, sorting) | `services/` | `infra/`, `ui/` |
| Is a plain data structure + serialization | `models/` | anywhere else |
| Is a new screen, dialog, widget, or paintEvent | `ui/` | anywhere else |
| Mutates UI state, holds selection, or user commands | `viewmodels/` | `ui/` |
| Is used by exactly one module | stays **private** in that module | `ports/` |
| Would need a second implementation to be testable | `ports/` + two adapters | — |

## 3. Strict Prohibitions

1. **`ui/` contains NO direct filesystem I/O or network requests**: Zero `open()`, `Path.read_text()`, `Path.write_text()`, `Image.open()`, `urllib`, or `requests`. All I/O routes through ports/adapters.
2. **`services/` contains NO imports of `PyQt6.QtWidgets`, `src.infra`, `src.viewmodels`, or `src.ui`**: Services are strictly headless and independently testable without UI or adapters.
3. **`viewmodels/` contains NO widget symbols**: ViewModels inherit from `QObject` and emit signals with primitive or model payloads only.

## 4. Agent Stop Rule

> **Stop Rule**: If a task or new feature cannot be unambiguously placed using this decision table, **stop and ask the user**. Do NOT append handlers to `main_window.py` or take shortcuts.
