import os
import subprocess
from io import BytesIO
from threading import Lock

import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

MAX_PAGES = 20
MAX_IMAGE_PIXELS = 30_000_000
MAX_OCR_SIDE = 3200
IMAGE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "TIFF": "image/tiff",
               "BMP": "image/bmp", "WEBP": "image/webp", "GIF": "image/gif"}
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
pdf_lock = Lock()  # PDFium calls must be serialized within one process.


class InvalidDocument(Exception):
    pass


class OcrError(Exception):
    pass


def read_image(image):
    image = image.convert("RGBA")
    white = Image.new("RGBA", image.size, "white")
    white.alpha_composite(image)
    image = white.convert("L")
    image.thumbnail((MAX_OCR_SIDE, MAX_OCR_SIDE))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    try:
        result = subprocess.run(
            [os.environ.get("TESSERACT_CMD", "tesseract"), "stdin", "stdout", "-l", "eng", "--dpi", "200"],
            input=buffer.getvalue(), capture_output=True, timeout=20, check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OcrError("OCR could not process this file. Check Tesseract or try a smaller file.") from error
    return result.stdout.decode("utf-8", errors="replace").strip()


def read_pdf(data):
    try:
        with pdf_lock, pdfium.PdfDocument(data) as pdf:
            if not 1 <= len(pdf) <= MAX_PAGES:
                raise InvalidDocument(f"A PDF must contain 1 to {MAX_PAGES} pages.")
            parts = []
            for page in pdf:
                try:
                    with_text = page.get_textpage()
                    native_text = with_text.get_text_bounded().strip()
                    with_text.close()
                    parts.append(native_text)
                    image_on_page = next(page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE]), None)
                    if not native_text or image_on_page is not None:
                        scale = min(200 / 72, MAX_OCR_SIDE / max(page.get_size()))
                        bitmap = page.render(scale=scale, fill_color=(255, 255, 255, 255))
                        try:
                            ocr_text = read_image(bitmap.to_pil())
                        finally:
                            bitmap.close()
                        if ocr_text != native_text:
                            parts.append(ocr_text)
                finally:
                    page.close()
    except (pdfium.PdfiumError, ValueError, ZeroDivisionError) as error:
        raise InvalidDocument("This PDF is damaged, empty, or password protected.") from error
    return "\n".join(part for part in parts if part)


def extract_text(data):
    if b"%PDF-" in data[:1024]:
        return "application/pdf", read_pdf(data)[:250_000]
    try:
        with Image.open(BytesIO(data)) as image:
            content_type = IMAGE_TYPES.get(image.format)
            if not content_type:
                raise InvalidDocument("Upload a PDF, PNG, JPEG, TIFF, BMP, WebP, or GIF file.")
            if getattr(image, "n_frames", 1) > MAX_PAGES:
                raise InvalidDocument(f"An image can contain up to {MAX_PAGES} frames.")
            parts = []
            for frame in ImageSequence.Iterator(image):
                if frame.width * frame.height > MAX_IMAGE_PIXELS:
                    raise InvalidDocument("The image exceeds 30 million pixels.")
                parts.append(read_image(ImageOps.exif_transpose(frame)))
            return content_type, "\n".join(parts)[:250_000]
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as error:
        raise InvalidDocument("Upload a readable PDF or supported image.") from error
