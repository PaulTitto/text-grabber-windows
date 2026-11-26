# Text Grabber

A clean, modern Windows desktop application for extracting text trapped inside images, videos, PDFs, and non-selectable UI elements — running **100% locally and offline** on your device using the built-in Windows OCR engine (`Windows.Media.Ocr.OcrEngine`).

- **No internet connection required**
- **No cloud service**
- **No per-use cost**
- **Local & private** — screenshots and images are never saved permanently; temporary files are deleted immediately after OCR finishes.

---

## Key Features

### 1. Capture Modes
- **Grab Screen (`Ctrl + Alt + G`, `Ctrl + Shift + G`, `Ctrl + N`, or `Ctrl + G`)**: Capture any region on your screen using a drag-to-select overlay.
- **Grab Frame (`Ctrl + Alt + F` or `Ctrl + Shift + F`)**: Floating always-on-top frame you can position over videos or app windows and click **Grab**, or toggle **`○ Watch (1.5s)`** to automatically capture and append new deduplicated lines live.
- **Open File**: Open images (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.gif`) or `.pdf` documents (with page navigation, single-page OCR, or **OCR All Pages**).
- **Paste (`Ctrl + V`)**: Run OCR directly on an image from the clipboard.
- **Preview Region Selection**: Drag a rectangle directly on the preview image to OCR a specific sub-region.

### 2. Output Modes
- **Standard**: Normal multi-line text extraction.
- **1-Line**: Joins extracted text into a single clean line.
- **Table**: Reconstructs word coordinates into a structured spreadsheet table.
- **Words**: Opens an interactive word-select overlay over the captured image so you can click individual words, drag across specific words, or double-click a word to copy it immediately.

### 3. Editor, Smart Quick-Actions & Post-Grab Cleanup
- **Smart Quick-Actions**: Automatically detects URLs, email addresses, phone numbers, and JSON in grabbed text and surfaces 1-click actions (`↗ Open URL`, `✉ Copy Email`, `☎ Copy Phone`, `{ } Format JSON`).
- **Cleanup Drawer & Presets (`✦ Cleanup`)**: Built-in presets (*Clean PDF Paragraph*, *Single Clean Line*, *Extract Emails*, *Extract URLs*, *Extract Numbers*), custom saved presets (`+ Save Preset`), *Trim Spaces*, *No Blank Lines*, *Unwrap Lines*, *ASCII Only*, *Deduplicate*, *Sort A-Z*, *UPPER / lower / Title Case*, and *Find & Replace* (with Regex support).
- **Auto-Copy**: Automatically copies extracted text to the clipboard after every grab.
- Save results to `.txt` or store reusable **Snippets**.

### 4. System Tray & Silent Background Mode
- Closing the main window minimizes **Text Grabber** to the Windows System Tray.
- Enable **Silent Mode** (`Silent: On` in the header or tray menu) to copy grabs directly to the clipboard with a Windows toast notification without popping open the main window.

### 5. Spreadsheet / Table Editor & Data Engineer Tools
- Double-click any cell to edit inline, or add/remove rows and columns (`+ Row`, `+ Col`, `Del Row`).
- **Copy TSV** to paste directly into Excel or Google Sheets, or **Export CSV**.
- **Data Engineer Exports**: Copy any table as a **SQL CTE** (`WITH grabbed_data AS (...)`), **`CREATE TABLE` DDL** (with inferred column types), **Pandas** (`pd.DataFrame`), **Polars** (`pl.DataFrame`), **JSON Records**, or **Markdown Table**.
- **Editor → Data Tools**:
  - **`SQL IN`**: Formats grabbed IDs/lines into a deduplicated SQL `IN (...)` list.
  - **`→ Table`**: Parses JSON / NDJSON arrays or delimited/terminal-aligned output (`|`, CSV, TSV, `psql`/`duckdb`/`kubectl` tables) into the Table editor.
  - **Log & Data Presets**: Built-in *Extract UUIDs*, *Extract IPv4*, *Extract Timestamps*, and *Filter Error Lines* presets.
- **Image Enhancer**: Toggle **Invert (Dark UI)** and **High Contrast** on the Preview pane to boost OCR accuracy on dark terminals and low-contrast dashboards.

### 6. History & Snippets
- Recent grabs, saved snippets, and custom cleanup presets are stored locally in `data/store.json` (text only, never images) for fast reuse.

---

## Installation & Shortcuts

Run [Install.bat](Install.bat) (or click **Shortcut** in the app) to install Desktop and Start Menu shortcuts with the app icon:

- **`Ctrl + Alt + T`** — Launch **Text Grabber** from anywhere in Windows (via Desktop / Start Menu shortcut).
- **`Ctrl + Alt + G`** (or `Ctrl + Shift + G` if available) — **Grab Screen** globally in any app (even when minimized to System Tray).
- **`Ctrl + Alt + F`** (or `Ctrl + Shift + F` if available) — **Grab Frame** globally in any app.
- **`Ctrl + N` / `Ctrl + G`** — **New Grab Screen** (when the app window is focused).
- **`Ctrl + V`** — **Paste & OCR** an image from the clipboard.

### Direct Launchers & Standalone `.exe`
- [TextGrabber.bat](TextGrabber.bat) — Launches the app without a console window.
- [GrabScreen.bat](GrabScreen.bat) — Launches the app and immediately opens the **Grab Screen** overlay (`--grab`).
- [build_exe.bat](build_exe.bat) — Builds a standalone `dist\TextGrabber.exe` using PyInstaller.

---

## Project Structure

| File | Description |
| --- | --- |
| `ocr_engine.cs` / `ocr_engine.exe` | Native C# helper calling local `Windows.Media.Ocr.OcrEngine` and outputting JSON with text and word bounding boxes. |
| `text_grabber_core.py` | Core module for local OCR, post-grab cleanup, presets, smart action detection, table reconstruction (`ocr_to_table`, TSV/CSV), PDF rendering via PyMuPDF (`fitz`), and local storage (`LocalStore`). |
| `text_grabber_app.py` | Windows desktop UI (Tkinter, DPI-aware, clean light theme, interactive word selector, live watch). |
| `win_tray.py` | Native Windows System Tray icon and toast notifications via Win32 `ctypes`. |
| `TextGrabber.bat` / `GrabScreen.bat` | Windowless launchers (`pythonw.exe`). |
| `Install_Shortcut.ps1` / `Install.bat` | Desktop & Start Menu shortcut installer (`Ctrl + Alt + T`). |
| `build_exe.bat` | PyInstaller script to bundle a standalone `TextGrabber.exe`. |
| `app_icon.ico` | Windows application icon. |
| `test_text_grabber.py` | Automated test suite (`unittest`). |

---

## Running Tests

```powershell
python -m unittest test_text_grabber.py -v
```
