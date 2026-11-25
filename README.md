# Text Grabber

A clean, modern Windows desktop application for extracting text trapped inside images, videos, PDFs, and non-selectable UI elements — running **100% locally and offline** on your device using the built-in Windows OCR engine (`Windows.Media.Ocr.OcrEngine`).

- **No internet connection required**
- **No cloud service**
- **No per-use cost**
- **Local & private** — screenshots and images are never saved permanently; temporary files are deleted immediately after OCR finishes.

---

## Key Features

### 1. Capture Modes
- **Grab Screen (`Ctrl + Shift + G`)**: Capture any region on your screen using a drag-to-select overlay.
- **Grab Frame (`Ctrl + Shift + F`)**: Floating always-on-top frame you can position over videos or app windows and click **Grab**.
- **Open File**: Open images (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.gif`) or `.pdf` documents (with page navigation, single-page OCR, or **OCR All Pages**).
- **Paste (`Ctrl + V`)**: Run OCR directly on an image from the clipboard.
- **Preview Region Selection**: Drag a rectangle directly on the preview image to OCR a specific sub-region.

### 2. Output Modes
- **Standard**: Normal multi-line text extraction.
- **1-Line**: Joins extracted text into a single clean line.
- **Table**: Reconstructs word coordinates into a structured spreadsheet table.

### 3. Editor & Post-Grab Cleanup
- **Cleanup Drawer (`✦ Cleanup`)**: *Trim Spaces*, *No Blank Lines*, *Unwrap Lines*, *ASCII Only*, *Deduplicate*, *Sort A-Z*, *UPPER / lower / Title Case*, and *Find & Replace* (with Regex support).
- **Auto-Copy**: Automatically copies extracted text to the clipboard after every grab.
- Save results to `.txt` or store reusable **Snippets**.

### 4. Spreadsheet / Table Editor
- Double-click any cell to edit inline.
- Add or remove rows and columns (`+ Row`, `+ Col`, `Del Row`).
- **Copy TSV** to paste directly into Excel or Google Sheets, or **Export CSV**.

### 5. History & Snippets
- Recent grabs and saved snippets are stored locally in `data/store.json` (text only, never images) for fast reuse.

---

## Installation & Shortcuts

Run [Install.bat](Install.bat) (or click the **Shortcut** button in the app) to install Desktop and Start Menu shortcuts with the app icon:

- **`Ctrl + Alt + T`** — Launch **Text Grabber** from anywhere in Windows (via Desktop / Start Menu shortcut).
- **`Ctrl + Shift + G`** — **Grab Screen** (while the app is running).
- **`Ctrl + Shift + F`** — **Grab Frame** (while the app is running).
- **`Ctrl + V`** — **Paste & OCR** an image from the clipboard.

You can also launch the app directly without installing shortcuts via [TextGrabber.bat](TextGrabber.bat).

---

## Project Structure

| File | Description |
| --- | --- |
| `ocr_engine.cs` / `ocr_engine.exe` | Native C# helper calling local `Windows.Media.Ocr.OcrEngine` and outputting JSON with text and word bounding boxes. |
| `text_grabber_core.py` | Core module for local OCR, post-grab cleanup, table reconstruction (`ocr_to_table`, TSV/CSV), PDF rendering via PyMuPDF (`fitz`), and local storage (`LocalStore`). |
| `text_grabber_app.py` | Windows desktop UI (Tkinter, DPI-aware, clean light theme). |
| `TextGrabber.bat` | Windowless launcher (`pythonw.exe`). |
| `Install_Shortcut.ps1` / `Install.bat` | Desktop & Start Menu shortcut installer (`Ctrl + Alt + T`). |
| `app_icon.ico` | Windows application icon. |
| `test_text_grabber.py` | Automated test suite (`unittest`). |

---

## Running Tests

```powershell
python -m unittest test_text_grabber.py -v
```
