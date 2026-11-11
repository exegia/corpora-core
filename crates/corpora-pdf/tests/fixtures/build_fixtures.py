"""Build small PDFs with independently specified text for engine tests."""

from pathlib import Path
import re
import subprocess
import tempfile
import zlib


ROOT = Path(__file__).parent


def pdf(objects: list[bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def line(font: str, size: int, y: int, text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /{font} {size} Tf 72 {y} Td ({escaped}) Tj ET\n".encode()


content = b"".join(
    [
        line("F2", 18, 750, "Sample Document"),
        line("F1", 12, 720, "This is a clear paragraph."),
        line("F1", 12, 690, "1. First item"),
        line("F1", 12, 672, "2. Second item"),
        line("F1", 12, 642, "See Reference [1]."),
        line("F2", 16, 612, "References"),
        line("F1", 12, 590, "[1] Example Source."),
        line("F2", 12, 550, "Name"),
        b"BT /F2 12 Tf 260 550 Td (Value) Tj ET\n",
        line("F1", 12, 532, "Alpha"),
        b"BT /F1 12 Tf 260 532 Td (42) Tj ET\n",
    ]
)
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R /Annots [7 0 R] >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"endstream",
    b"<< /Type /Annot /Subtype /Link /Rect [95 638 170 655] /Border [0 0 0] /A << /S /URI /URI (https://example.org/reference) >> >>",
]
(ROOT / "semantic.pdf").write_bytes(pdf(objects))

# Keep the independently specified wording above, but remove its PDF text
# objects so the engine has to read the pixels in this second fixture.
with tempfile.TemporaryDirectory() as folder:
    prefix = Path(folder) / "render"
    subprocess.run(
        ["pdftoppm", "-f", "1", "-l", "1", "-r", "150", "-singlefile", str(ROOT / "semantic.pdf"), str(prefix)],
        check=True,
    )
    ppm = prefix.with_suffix(".ppm").read_bytes()
header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", ppm)
assert header is not None
width, height = (int(value) for value in header.groups())
pixels = ppm[header.end() :]
assert len(pixels) == width * height * 3
compressed = zlib.compress(pixels, level=9)
image_content = b"q 612 0 0 792 0 0 cm /Im1 Do Q\n"
scan_objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>",
    f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(compressed)} >>\nstream\n".encode() + compressed + b"\nendstream",
    f"<< /Length {len(image_content)} >>\nstream\n".encode() + image_content + b"endstream",
]
(ROOT / "scanned.pdf").write_bytes(pdf(scan_objects))

mixed_objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R 8 0 R] /Count 2 >>",
    objects[2],
    objects[3],
    objects[4],
    objects[5],
    objects[6],
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 9 0 R >> >> /Contents 10 0 R >>",
    scan_objects[3],
    scan_objects[4],
]
(ROOT / "mixed.pdf").write_bytes(pdf(mixed_objects))
