import sys
import zipfile
from io import BytesIO
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import extract_text_from_bytes  # noqa: E402


def make_pptx_with_text(text: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            f"""
            <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                   xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
              <p:txBody>
                <a:bodyPr/>
                <a:lstStyle/>
                <a:p>
                  <a:r>
                    <a:t>{text}</a:t>
                  </a:r>
                </a:p>
              </p:txBody>
            </p:sld>
            """,
        )
    return buffer.getvalue()


def test_extract_text_from_pptx() -> None:
    pptx_bytes = make_pptx_with_text("The return window is 30 days.")
    extracted = extract_text_from_bytes("example.pptx", pptx_bytes)
    assert "return window" in extracted.lower()


def test_extract_text_from_binary_rejects_invalid_bytes() -> None:
    extracted = extract_text_from_bytes("binary.bin", b"\x00\x01\x02\xff\x00\x20")
    assert extracted == ""
