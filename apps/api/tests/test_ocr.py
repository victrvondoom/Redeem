import io

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app import ocr

B = "/api/v1"


def png(lines: list[str]) -> bytes:
    im = Image.new("RGB", (900, 70 + 60 * len(lines)), "white")
    d = ImageDraw.Draw(im)
    f = ImageFont.load_default(size=36)
    for i, ln in enumerate(lines):
        d.text((24, 24 + 60 * i), ln, fill="black", font=f)
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_real_ocr_reads_an_image_and_the_pipeline_extracts_facts_from_it(api):
    assert ocr.available()
    data = png(["Flight FA2041 cancelled", "Refund Rs 8450 not received"])
    r = api.post(f"{B}/documents?domain=travel", files={"file": ("ticket.png", data, "image/png")})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["ocr_status"].startswith("OCR:") and float(d["ocr_status"].split(":")[1]) > 0.5
    full = api.get(f"{B}/documents/{d['id']}").json()
    assert "FA2041" in full["text"] and "8450" in full["text"] and "FA2041" in full["extracted"]["booking_refs"]


def test_blank_image_is_reported_as_no_text_not_invented(api):
    b = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(b, "PNG")
    d = api.post(f"{B}/documents", files={"file": ("blank.png", b.getvalue(), "image/png")}).json()
    assert d["ocr_status"] == "OCR_NO_TEXT_FOUND" and api.get(f"{B}/documents/{d['id']}").json()["text"] == ""


def test_scanned_pdf_with_only_an_image_is_ocrd(api):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawImage(ImageReader(io.BytesIO(png(["Invoice INV-77231", "Total Rs 1200"]))), 40, 400, width=500, height=140)
    c.showPage()
    c.save()
    d = api.post(f"{B}/documents", files={"file": ("scan.pdf", buf.getvalue(), "application/pdf")}).json()
    assert d["ocr_status"].startswith("OCR:"), d
    assert "INV-77231" in api.get(f"{B}/documents/{d['id']}").json()["text"]


def test_ocr_review_correction_recomputes_facts_and_keeps_the_original(api, api2):
    d = api.post(f"{B}/documents?domain=travel", files={"file": ("t.png", png(["Flight FA2O41 cancelled"]), "image/png")}).json()
    r = api.put(f"{B}/documents/{d['id']}/text", {"text": "Flight FA2041 cancelled, refund Rs 8450"})
    assert r.status_code == 200 and r.json()["ocr_status"] == "OCR_REVIEWED" and "FA2041" in r.json()["extracted"]["booking_refs"]
    assert api.get(f"{B}/documents/{d['id']}/download").content[:4] == b"\x89PNG"            # original bytes untouched
    assert api2.put(f"{B}/documents/{d['id']}/text", {"text": "x"}).status_code == 404       # IDOR
    assert api.put(f"{B}/documents/{d['id']}/text", {"text": ""}).status_code == 422
