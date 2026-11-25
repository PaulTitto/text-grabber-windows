# Text Grabber

Aplikasi desktop Windows untuk mengekstrak teks yang terjebak di dalam gambar, video, PDF, atau bagian aplikasi yang tidak bisa di-*select* — berjalan **100% lokal dan offline** di perangkat Anda menggunakan engine OCR bawaan Windows (`Windows.Media.Ocr.OcrEngine`).

- **Tanpa koneksi internet**
- **Tanpa layanan cloud**
- **Tanpa biaya per penggunaan**
- **Privasi terjaga** — gambar tidak disimpan permanen; file sementara dihapus otomatis segera setelah OCR selesai.

---

## Fitur Utama

### 1. Mode Pengambilan Teks (Capture Modes)
- **Grab Screen (`Ctrl + Shift + G`)**: Tangkap area layar mana saja dengan overlay drag-to-select.
- **Grab Frame (`Ctrl + Shift + F`)**: Jendela frame mengambang (*always-on-top*) untuk diarahkan ke video atau jendela aplikasi lalu klik **Grab**.
- **Open Image / PDF**: Buka file gambar (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.gif`) atau dokumen `.pdf` (dengan navigasi per halaman, OCR halaman aktif, atau **OCR All Pages**).
- **Paste Image (`Ctrl + V`)**: Jalankan OCR langsung dari gambar di clipboard.
- **Region Preview**: Tarik kotak langsung pada gambar di panel *Preview* untuk OCR sebagian area saja.

### 2. Mode Output
- **Standard**: Ekstraksi multi-baris normal.
- **1-Line**: Menggabungkan hasil OCR menjadi satu baris rapi.
- **Table**: Merekonstruksi posisi kata berdasarkan koordinat menjadi tabel siap-spreadsheet.

### 3. Editor & Post-Grab Cleanup
- **Cleanup Drawer (`✦ Cleanup`)**: *Trim Spaces*, *No Blank Lines*, *Unwrap Lines*, *ASCII Only*, *Deduplicate*, *Sort A-Z*, *UPPER / lower / Title Case*, dan *Find & Replace* (mendukung Regex).
- **Auto-Copy**: Otomatis menyalin hasil OCR ke clipboard setiap selesai grab.
- Simpan hasil ke file `.txt` atau simpan sebagai **Snippet**.

### 4. Spreadsheet / Table Editor
- Edit sel tabel langsung dengan *double-click*.
- Tambah atau hapus baris/kolom (`+ Row`, `+ Col`, `Del Row`).
- **Copy TSV** untuk langsung di-paste ke Excel atau Google Sheets, atau **Export CSV**.

### 5. History & Snippets
- Riwayat grab terbaru dan snippet tersimpan secara lokal di `data/store.json` (hanya teks, bukan gambar) untuk penggunaan ulang cepat.

---

## Instalasi & Shortcut

Jalankan [Install.bat](Install.bat) (atau klik tombol **Shortcut** di dalam aplikasi) untuk memasang shortcut ke **Desktop** dan **Start Menu** dengan ikon aplikasi:

- **`Ctrl + Alt + T`** — Membuka **Text Grabber** dari mana saja di Windows (melalui shortcut Desktop / Start Menu).
- **`Ctrl + Shift + G`** — **Grab Screen** (saat aplikasi berjalan).
- **`Ctrl + Shift + F`** — **Grab Frame** (saat aplikasi berjalan).
- **`Ctrl + V`** — **Paste & OCR** gambar dari clipboard.

Atau jalankan langsung tanpa instalasi shortcut lewat [TextGrabber.bat](TextGrabber.bat).

---

## Struktur Proyek

| File | Deskripsi |
| --- | --- |
| `ocr_engine.cs` / `ocr_engine.exe` | Helper C# native yang memanggil `Windows.Media.Ocr.OcrEngine` lokal dan menghasilkan JSON teks + koordinat kata. |
| `text_grabber_core.py` | Modul inti untuk OCR lokal, post-grab cleanup, rekonstruksi tabel (`ocr_to_table`, TSV/CSV), render PDF via PyMuPDF (`fitz`), dan penyimpanan lokal (`LocalStore`). |
| `text_grabber_app.py` | Antarmuka desktop Windows (Tkinter, DPI-aware, dark theme Windows 11). |
| `TextGrabber.bat` | Launcher aplikasi tanpa jendela konsol (`pythonw.exe`). |
| `Install_Shortcut.ps1` / `Install.bat` | Installer shortcut Desktop & Start Menu (`Ctrl + Alt + T`). |
| `app_icon.ico` | Ikon aplikasi Windows. |
| `test_text_grabber.py` | Suite pengujian otomatis (`unittest`). |

---

## Pengujian

```powershell
python -m unittest test_text_grabber.py -v
```
