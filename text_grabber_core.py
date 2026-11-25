"""Core local OCR, post-grab cleanup, table extraction, PDF rendering, and storage for Text Grabber."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import fitz  # PyMuPDF
from PIL import Image


def get_resource_path(filename: str) -> str:
    """Resolve bundled resource path for both source runs and PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
OCR_EXE = get_resource_path("ocr_engine.exe")
DATA_DIR = os.path.join(APP_DIR, "data")
STORE_PATH = os.path.join(DATA_DIR, "store.json")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif", ".gif"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class CleanupOptions:
    """Options for post-grab text cleanup."""

    trim_lines: bool = True
    remove_blank_lines: bool = False
    unwrap_paragraphs: bool = False
    single_line: bool = False
    remove_non_ascii: bool = False


def list_ocr_languages() -> list[dict[str, str]]:
    """Return installed Windows OCR languages from the local ocr_engine.exe."""
    if not os.path.exists(OCR_EXE):
        return []
    proc = subprocess.run(
        [OCR_EXE, "--list-langs"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        creationflags=_CREATE_NO_WINDOW,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        data = json.loads(proc.stdout)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def run_ocr(image_or_path: Image.Image | str, lang_tag: str | None = None) -> dict[str, Any]:
    """Run local Windows OCR on a PIL Image or image file path.

    Returns a dict with keys: language, width, height, text, lines.
    """
    if not os.path.exists(OCR_EXE):
        raise FileNotFoundError(f"Local OCR engine not found: {OCR_EXE}")

    temp_path: str | None = None
    try:
        if isinstance(image_or_path, str):
            img = Image.open(image_or_path)
        else:
            img = image_or_path

        # Upscale very small crops slightly so Windows OCR recognizes small UI text reliably.
        w, h = img.size
        scale = 1.0
        if w < 120 or h < 40:
            scale = 2.0
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        fd, temp_path = tempfile.mkstemp(suffix=".png", prefix="tg_ocr_")
        os.close(fd)
        img.save(temp_path, format="PNG")

        cmd = [OCR_EXE, temp_path]
        if lang_tag:
            cmd.append(lang_tag)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=_CREATE_NO_WINDOW,
            check=False,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or f"OCR exited with code {proc.returncode}"
            raise RuntimeError(err)

        result = json.loads(proc.stdout)
        if scale != 1.0 and "lines" in result:
            for line in result["lines"]:
                for word in line.get("words", []):
                    word["x"] = round(word["x"] / scale, 1)
                    word["y"] = round(word["y"] / scale, 1)
                    word["w"] = round(word["w"] / scale, 1)
                    word["h"] = round(word["h"] / scale, 1)
        return result
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def clean_text(text: str, opts: CleanupOptions) -> str:
    """Apply post-grab cleanup options to extracted text."""
    if not text:
        return ""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")

    if opts.trim_lines:
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in lines]

    if opts.remove_blank_lines:
        lines = [ln for ln in lines if ln.strip() != ""]

    if opts.single_line:
        result = " ".join(ln.strip() for ln in lines if ln.strip())
    elif opts.unwrap_paragraphs:
        paragraphs: list[str] = []
        current: list[str] = []
        for ln in lines:
            if ln.strip() == "":
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
            else:
                current.append(ln.strip())
        if current:
            paragraphs.append(" ".join(current))
        result = "\n\n".join(paragraphs)
    else:
        result = "\n".join(lines)

    if opts.remove_non_ascii:
        result = result.encode("ascii", errors="ignore").decode("ascii")

    return result


def deduplicate_lines(text: str) -> str:
    """Remove duplicate lines while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for ln in text.replace("\r\n", "\n").split("\n"):
        if ln not in seen:
            seen.add(ln)
            out.append(ln)
    return "\n".join(out)


def sort_lines(text: str, reverse: bool = False) -> str:
    """Sort non-empty lines alphabetically."""
    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    return "\n".join(sorted(lines, key=str.casefold, reverse=reverse))


def transform_case(text: str, mode: str) -> str:
    """Transform text case: upper, lower, title, or sentence."""
    if mode == "upper":
        return text.upper()
    if mode == "lower":
        return text.lower()
    if mode == "title":
        return text.title()
    if mode == "sentence":
        return re.sub(
            r"(^|[.!?]\s+)([a-z])",
            lambda m: m.group(1) + m.group(2).upper(),
            text.lower(),
        )
    return text


def find_replace(
    text: str,
    pattern: str,
    replacement: str,
    use_regex: bool = False,
    case_sensitive: bool = False,
) -> tuple[str, int]:
    """Replace occurrences in text; returns (new_text, count)."""
    if not pattern:
        return text, 0
    flags = 0 if case_sensitive else re.IGNORECASE
    if use_regex:
        compiled = re.compile(pattern, flags)
        return compiled.subn(replacement, text)
    compiled = re.compile(re.escape(pattern), flags)
    return compiled.subn(lambda _m: replacement, text)


def ocr_to_table(ocr_data: dict[str, Any]) -> list[list[str]]:
    """Reconstruct a 2D spreadsheet table from OCR word bounding boxes.

    Uses Y-coordinate clustering for rows and X-gap analysis for columns.
    """
    words: list[dict[str, Any]] = []
    for line in ocr_data.get("lines", []):
        for w in line.get("words", []):
            if w.get("text", "").strip():
                words.append(w)

    if not words:
        raw_text = (ocr_data.get("text") or "").strip()
        if not raw_text:
            return []
        return [[ln] for ln in raw_text.splitlines() if ln.strip()]

    heights = [max(1.0, float(w["h"])) for w in words]
    median_h = statistics.median(heights)
    row_tol = max(4.0, median_h * 0.55)

    # Sort top-to-bottom, then cluster into rows by vertical center.
    sorted_by_y = sorted(words, key=lambda w: w["y"] + w["h"] / 2.0)
    rows_raw: list[list[dict[str, Any]]] = []
    row_centers: list[float] = []

    for w in sorted_by_y:
        cy = w["y"] + w["h"] / 2.0
        placed = False
        for idx, rc in enumerate(row_centers):
            if abs(cy - rc) <= row_tol:
                rows_raw[idx].append(w)
                row_centers[idx] = sum(x["y"] + x["h"] / 2.0 for x in rows_raw[idx]) / len(rows_raw[idx])
                placed = True
                break
        if not placed:
            rows_raw.append([w])
            row_centers.append(cy)

    # Sort each row left-to-right and measure horizontal gaps to separate cells vs spaces.
    gaps: list[float] = []
    for row in rows_raw:
        row.sort(key=lambda w: w["x"])
        for i in range(len(row) - 1):
            gap = row[i + 1]["x"] - (row[i]["x"] + row[i]["w"])
            if gap > 0:
                gaps.append(gap)

    # Estimate column split threshold: larger than normal word spacing.
    char_widths = [w["w"] / max(1, len(w["text"])) for w in words]
    median_char_w = statistics.median(char_widths) if char_widths else 8.0
    cell_gap_threshold = max(median_char_w * 2.2, median_h * 0.9)

    # Build cell segments per row.
    row_cells: list[list[tuple[float, str]]] = []
    all_cell_starts: list[float] = []

    for row in rows_raw:
        cells: list[tuple[float, str]] = []
        cur_words = [row[0]["text"]]
        cur_x = row[0]["x"]
        prev_end = row[0]["x"] + row[0]["w"]
        for w in row[1:]:
            gap = w["x"] - prev_end
            if gap > cell_gap_threshold:
                cells.append((cur_x, " ".join(cur_words)))
                all_cell_starts.append(cur_x)
                cur_words = [w["text"]]
                cur_x = w["x"]
            else:
                cur_words.append(w["text"])
            prev_end = max(prev_end, w["x"] + w["w"])
        cells.append((cur_x, " ".join(cur_words)))
        all_cell_starts.append(cur_x)
        row_cells.append(cells)

    # Cluster cell X-starts into global column anchors.
    col_tol = max(12.0, median_char_w * 3.0)
    col_anchors: list[float] = []
    for x in sorted(all_cell_starts):
        if not col_anchors or abs(x - col_anchors[-1]) > col_tol:
            col_anchors.append(x)
        else:
            col_anchors[-1] = (col_anchors[-1] + x) / 2.0

    num_cols = max(1, len(col_anchors))
    table: list[list[str]] = []
    for cells in row_cells:
        grid_row = [""] * num_cols
        for cx, text in cells:
            col_idx = min(range(num_cols), key=lambda i: abs(col_anchors[i] - cx))
            if grid_row[col_idx]:
                grid_row[col_idx] += " " + text
            else:
                grid_row[col_idx] = text
        table.append(grid_row)

    return table


def table_to_tsv(table: list[list[str]]) -> str:
    """Format a 2D table as tab-separated values for Excel / Google Sheets paste."""
    return "\n".join("\t".join(cell.replace("\t", " ") for cell in row) for row in table)


def table_to_csv(table: list[list[str]]) -> str:
    """Format a 2D table as RFC-4180 CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerows(table)
    return buf.getvalue()


class PdfDocument:
    """Local PDF renderer using PyMuPDF (fitz)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._doc = fitz.open(path)

    @property
    def page_count(self) -> int:
        return len(self._doc)

    def render_page(self, page_index: int, dpi: int = 200) -> Image.Image:
        if page_index < 0 or page_index >= len(self._doc):
            raise IndexError(f"Page {page_index} out of range (0..{len(self._doc) - 1})")
        page = self._doc[page_index]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    def close(self) -> None:
        self._doc.close()


_URL_RE = re.compile(r"https?://[^\s<>\"'\]\)]+")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-\(\)]{7,}\d)")

DEFAULT_PRESETS: list[dict[str, Any]] = [
    {
        "name": "Clean PDF Paragraph",
        "trim_lines": True,
        "remove_blank_lines": False,
        "unwrap_paragraphs": True,
        "single_line": False,
        "remove_non_ascii": False,
        "extract_pattern": "",
    },
    {
        "name": "Single Clean Line",
        "trim_lines": True,
        "remove_blank_lines": True,
        "unwrap_paragraphs": False,
        "single_line": True,
        "remove_non_ascii": False,
        "extract_pattern": "",
    },
    {
        "name": "Extract Emails",
        "trim_lines": True,
        "remove_blank_lines": True,
        "unwrap_paragraphs": False,
        "single_line": False,
        "remove_non_ascii": False,
        "extract_pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    },
    {
        "name": "Extract URLs",
        "trim_lines": True,
        "remove_blank_lines": True,
        "unwrap_paragraphs": False,
        "single_line": False,
        "remove_non_ascii": False,
        "extract_pattern": r"https?://[^\s<>\"'\]\)]+",
    },
    {
        "name": "Extract Numbers",
        "trim_lines": True,
        "remove_blank_lines": True,
        "unwrap_paragraphs": False,
        "single_line": False,
        "remove_non_ascii": False,
        "extract_pattern": r"-?\d+(?:[.,]\d+)?",
    },
]


def detect_smart_actions(text: str) -> dict[str, Any]:
    """Detect actionable entities (URLs, emails, phones, JSON) in grabbed text."""
    stripped = text.strip()
    urls = list(dict.fromkeys(_URL_RE.findall(text)))
    emails = list(dict.fromkeys(_EMAIL_RE.findall(text)))
    phones = list(dict.fromkeys(p.strip() for p in _PHONE_RE.findall(text) if sum(c.isdigit() for c in p) >= 8))

    formatted_json: str | None = None
    if stripped.startswith(("{", "[")) and stripped.endswith(("}", "]")):
        try:
            parsed = json.loads(stripped)
            formatted_json = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            formatted_json = None

    return {
        "urls": urls,
        "emails": emails,
        "phones": phones,
        "formatted_json": formatted_json,
    }


def extract_new_lines(seen_lines: set[str], new_text: str) -> tuple[list[str], set[str]]:
    """Return newly observed non-empty lines for live Grab Frame watching."""
    added: list[str] = []
    updated = set(seen_lines)
    for raw in new_text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if line and line not in updated:
            updated.add(line)
            added.append(line)
    return added, updated


def apply_preset(text: str, preset: dict[str, Any]) -> str:
    """Apply a named cleanup/extraction preset to text."""
    pattern = preset.get("extract_pattern", "").strip()
    if pattern:
        matches = re.findall(pattern, text)
        return "\n".join(dict.fromkeys(m if isinstance(m, str) else " ".join(m) for m in matches))

    opts = CleanupOptions(
        trim_lines=bool(preset.get("trim_lines", True)),
        remove_blank_lines=bool(preset.get("remove_blank_lines", False)),
        unwrap_paragraphs=bool(preset.get("unwrap_paragraphs", False)),
        single_line=bool(preset.get("single_line", False)),
        remove_non_ascii=bool(preset.get("remove_non_ascii", False)),
    )
    return clean_text(text, opts)


class LocalStore:
    """Persists grab history, reusable text snippets, and custom cleanup presets locally."""

    def __init__(self, path: str = STORE_PATH, max_history: int = 50) -> None:
        self.path = path
        self.max_history = max_history
        self.history: list[dict[str, str]] = []
        self.snippets: list[dict[str, str]] = []
        self.presets: list[dict[str, Any]] = [dict(p) for p in DEFAULT_PRESETS]
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.history = data.get("history", [])[: self.max_history]
            self.snippets = data.get("snippets", [])
            saved_presets = data.get("presets")
            if isinstance(saved_presets, list) and saved_presets:
                self.presets = saved_presets
        except (OSError, json.JSONDecodeError):
            self.history = []
            self.snippets = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "history": self.history[: self.max_history],
                    "snippets": self.snippets,
                    "presets": self.presets,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

    def add_history(self, text: str, source: str, mode: str) -> None:
        if not text.strip():
            return
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "mode": mode,
            "text": text,
        }
        self.history.insert(0, entry)
        self.history = self.history[: self.max_history]
        self.save()

    def clear_history(self) -> None:
        self.history = []
        self.save()

    def add_snippet(self, title: str, text: str) -> None:
        if not text.strip():
            return
        self.snippets.insert(0, {"title": title.strip() or "Snippet", "text": text})
        self.save()

    def delete_snippet(self, index: int) -> None:
        if 0 <= index < len(self.snippets):
            self.snippets.pop(index)
            self.save()

    def add_preset(self, preset: dict[str, Any]) -> None:
        name = (preset.get("name") or "").strip()
        if not name:
            return
        self.presets = [p for p in self.presets if p.get("name") != name]
        self.presets.insert(0, preset)
        self.save()
