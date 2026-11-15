from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def scanned_document(kind="PDF"):
    image = Image.new("RGB", (1050, 175), "white")
    ImageDraw.Draw(image).text(
        (35, 40), "Orchid Voucher 2026", font=ImageFont.load_default(size=66), fill="black"
    )
    buffer = BytesIO()
    image.save(buffer, format=kind)
    return buffer.getvalue()
