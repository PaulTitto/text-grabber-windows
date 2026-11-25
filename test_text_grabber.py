"""Automated tests for Text Grabber local OCR, cleanup, table parser, PDF, and storage."""

from __future__ import annotations

import os
import tempfile
import unittest

import fitz
from PIL import Image, ImageDraw, ImageFont

from text_grabber_core import (
    CleanupOptions,
    DEFAULT_PRESETS,
    LocalStore,
    PdfDocument,
    apply_preset,
    clean_text,
    deduplicate_lines,
    detect_smart_actions,
    extract_new_lines,
    find_replace,
    list_ocr_languages,
    ocr_to_table,
    run_ocr,
    sort_lines,
    table_to_csv,
    table_to_tsv,
    transform_case,
)


def _make_text_image(lines: list[tuple[int, int, str]], size: tuple[int, int] = (700, 260)) -> Image.Image:
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    for x, y, txt in lines:
        draw.text((x, y), txt, fill="black", font=font)
    return img


class TestTextGrabber(unittest.TestCase):
    def test_languages_available(self) -> None:
        langs = list_ocr_languages()
        self.assertGreater(len(langs), 0)
        self.assertTrue(any("tag" in l and "name" in l for l in langs))

    def test_local_ocr_on_image(self) -> None:
        img = _make_text_image([(30, 30, "Hello Text Grabber"), (30, 80, "Offline Local OCR")])
        res = run_ocr(img)
        text = res["text"]
        self.assertIn("Hello", text)
        self.assertIn("Offline", text)
        self.assertGreaterEqual(len(res["lines"]), 2)

    def test_table_reconstruction_from_ocr(self) -> None:
        img = _make_text_image(
            [
                (30, 30, "Item"),
                (280, 30, "Qty"),
                (480, 30, "Price"),
                (30, 90, "Apple"),
                (280, 90, "10"),
                (480, 90, "250"),
                (30, 150, "Banana"),
                (280, 150, "20"),
                (480, 150, "400"),
            ],
            size=(720, 240),
        )
        res = run_ocr(img)
        table = ocr_to_table(res)
        self.assertGreaterEqual(len(table), 3)
        self.assertGreaterEqual(len(table[0]), 3)
        tsv = table_to_tsv(table)
        csv_out = table_to_csv(table)
        self.assertIn("\t", tsv)
        self.assertIn(",", csv_out)

    def test_cleanup_and_transforms(self) -> None:
        raw = "  hello   world  \n\n  second line \nhello   world  "
        cleaned = clean_text(raw, CleanupOptions(trim_lines=True, remove_blank_lines=True))
        self.assertEqual(cleaned, "hello world\nsecond line\nhello world")

        dedup = deduplicate_lines(cleaned)
        self.assertEqual(dedup, "hello world\nsecond line")

        unwrapped = clean_text("line one\nline two\n\npara two", CleanupOptions(unwrap_paragraphs=True))
        self.assertEqual(unwrapped, "line one line two\n\npara two")

        single = clean_text("a\nb\nc", CleanupOptions(single_line=True))
        self.assertEqual(single, "a b c")

        self.assertEqual(sort_lines("beta\nalpha"), "alpha\nbeta")
        self.assertEqual(transform_case("hello world", "upper"), "HELLO WORLD")
        self.assertEqual(transform_case("HELLO WORLD", "title"), "Hello World")

        replaced, cnt = find_replace("foo 123 bar 456", r"\d+", "NUM", use_regex=True)
        self.assertEqual(cnt, 2)
        self.assertEqual(replaced, "foo NUM bar NUM")

    def test_pdf_render_and_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "sample.pdf")
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 100), "Local PDF OCR Test", fontsize=24)
            doc.save(pdf_path)
            doc.close()

            pdf = PdfDocument(pdf_path)
            try:
                self.assertEqual(pdf.page_count, 1)
                img = pdf.render_page(0, dpi=150)
                res = run_ocr(img)
                self.assertIn("PDF", res["text"])
            finally:
                pdf.close()

    def test_local_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store_path = os.path.join(tmp, "store.json")
            s1 = LocalStore(path=store_path)
            s1.add_history("Grabbed text", "Screenshot", "Standard")
            s1.add_snippet("Greeting", "Hello!")

            s2 = LocalStore(path=store_path)
            self.assertEqual(len(s2.history), 1)
            self.assertEqual(s2.history[0]["text"], "Grabbed text")
            self.assertEqual(len(s2.snippets), 1)
            self.assertEqual(s2.snippets[0]["title"], "Greeting")

    def test_app_module_imports(self) -> None:
        import text_grabber_app
        import win_tray

        self.assertTrue(hasattr(text_grabber_app, "TextGrabberApp"))
        self.assertTrue(hasattr(text_grabber_app, "WordSelectOverlay"))
        self.assertTrue(hasattr(win_tray, "WinTrayIcon"))

    def test_smart_actions_and_presets(self) -> None:
        sample = "Contact support@example.com or visit https://example.com/docs and call +62 812-3456-7890"
        detected = detect_smart_actions(sample)
        self.assertEqual(detected["urls"], ["https://example.com/docs"])
        self.assertEqual(detected["emails"], ["support@example.com"])
        self.assertEqual(len(detected["phones"]), 1)

        json_detected = detect_smart_actions('{"name":"TextGrabber","offline":true}')
        self.assertIsNotNone(json_detected["formatted_json"])
        self.assertIn("\n", json_detected["formatted_json"])

        email_preset = next(p for p in DEFAULT_PRESETS if p["name"] == "Extract Emails")
        self.assertEqual(apply_preset(sample, email_preset), "support@example.com")

    def test_extract_new_lines_for_live_watch(self) -> None:
        seen: set[str] = set()
        added1, seen = extract_new_lines(seen, "Line A\nLine B\n")
        self.assertEqual(added1, ["Line A", "Line B"])
        added2, seen = extract_new_lines(seen, "Line B\nLine C\n")
        self.assertEqual(added2, ["Line C"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
