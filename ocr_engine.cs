using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage;
using Windows.Storage.Streams;

namespace TextGrabberOcr
{
    class Program
    {
        static int Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;
            if (args.Length == 0)
            {
                Console.Error.WriteLine("Usage: ocr_engine.exe --list-langs | <image_path> [lang_tag]");
                return 1;
            }

            if (args[0] == "--list-langs")
            {
                var langs = OcrEngine.AvailableRecognizerLanguages;
                var sb = new StringBuilder();
                sb.Append("[");
                for (int i = 0; i < langs.Count; i++)
                {
                    if (i > 0) sb.Append(",");
                    sb.Append("{\"tag\":\"").Append(EscapeJson(langs[i].LanguageTag)).Append("\",");
                    sb.Append("\"name\":\"").Append(EscapeJson(langs[i].DisplayName)).Append("\"}");
                }
                sb.Append("]");
                Console.WriteLine(sb.ToString());
                return 0;
            }

            string imagePath = Path.GetFullPath(args[0]);
            if (!File.Exists(imagePath))
            {
                Console.Error.WriteLine("File not found: " + imagePath);
                return 2;
            }

            string langTag = args.Length > 1 ? args[1] : null;
            try
            {
                string json = RunOcrAsync(imagePath, langTag).GetAwaiter().GetResult();
                Console.WriteLine(json);
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("OCR Error: " + ex.Message);
                return 3;
            }
        }

        static async Task<string> RunOcrAsync(string imagePath, string langTag)
        {
            OcrEngine engine = null;
            if (!string.IsNullOrEmpty(langTag))
            {
                var lang = new Language(langTag);
                if (OcrEngine.IsLanguageSupported(lang))
                {
                    engine = OcrEngine.TryCreateFromLanguage(lang);
                }
            }
            if (engine == null)
            {
                engine = OcrEngine.TryCreateFromUserProfileLanguages();
            }
            if (engine == null && OcrEngine.AvailableRecognizerLanguages.Count > 0)
            {
                engine = OcrEngine.TryCreateFromLanguage(OcrEngine.AvailableRecognizerLanguages[0]);
            }
            if (engine == null)
            {
                throw new InvalidOperationException("No Windows OCR language packs are available on this device.");
            }

            StorageFile file = await StorageFile.GetFileFromPathAsync(imagePath);
            using (IRandomAccessStream stream = await file.OpenAsync(FileAccessMode.Read))
            {
                BitmapDecoder decoder = await BitmapDecoder.CreateAsync(stream);
                SoftwareBitmap bitmap = await decoder.GetSoftwareBitmapAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied);

                OcrResult result = await engine.RecognizeAsync(bitmap);
                return SerializeResult(result, engine.RecognizerLanguage.LanguageTag, bitmap.PixelWidth, bitmap.PixelHeight);
            }
        }

        static string SerializeResult(OcrResult result, string langTag, int width, int height)
        {
            var sb = new StringBuilder();
            sb.Append("{");
            sb.Append("\"language\":\"").Append(EscapeJson(langTag)).Append("\",");
            sb.Append("\"width\":").Append(width).Append(",");
            sb.Append("\"height\":").Append(height).Append(",");
            sb.Append("\"text\":\"").Append(EscapeJson(result.Text ?? "")).Append("\",");
            sb.Append("\"lines\":[");
            for (int i = 0; i < result.Lines.Count; i++)
            {
                if (i > 0) sb.Append(",");
                OcrLine line = result.Lines[i];
                sb.Append("{");
                sb.Append("\"text\":\"").Append(EscapeJson(line.Text ?? "")).Append("\",");
                sb.Append("\"words\":[");
                for (int j = 0; j < line.Words.Count; j++)
                {
                    if (j > 0) sb.Append(",");
                    OcrWord w = line.Words[j];
                    sb.Append("{");
                    sb.Append("\"text\":\"").Append(EscapeJson(w.Text ?? "")).Append("\",");
                    sb.Append("\"x\":").Append(w.BoundingRect.X.ToString("F1", CultureInfo.InvariantCulture)).Append(",");
                    sb.Append("\"y\":").Append(w.BoundingRect.Y.ToString("F1", CultureInfo.InvariantCulture)).Append(",");
                    sb.Append("\"w\":").Append(w.BoundingRect.Width.ToString("F1", CultureInfo.InvariantCulture)).Append(",");
                    sb.Append("\"h\":").Append(w.BoundingRect.Height.ToString("F1", CultureInfo.InvariantCulture));
                    sb.Append("}");
                }
                sb.Append("]");
                sb.Append("}");
            }
            sb.Append("]}");
            return sb.ToString();
        }

        static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < ' ')
                            sb.AppendFormat("\\u{0:X4}", (int)c);
                        else
                            sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }
    }
}
