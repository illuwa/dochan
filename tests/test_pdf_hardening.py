"""감수(2026-08-08)에서 발견된 악성/손상 PDF 방어 회귀 테스트."""
import zlib

import pytest

from dochan.pdf.cmap import parse_tounicode
from dochan.pdf.filters import MAX_DECODED_SIZE, decode_stream
from dochan.pdf.objects import PDFLexer, PDFSyntaxError
from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf, _minimal_objects


def _write(tmp_path, name, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


# ── C1: bfrange 코드 길이 0 → decode() 무한 루프 ──

def test_bfrange_zero_length_code_terminates():
    data = b"""
    1 begincodespacerange
    <00> <FF>
    endcodespacerange
    1 beginbfrange
    <0> <0> <0041>
    endbfrange
    """
    cmap = parse_tounicode(data)
    assert 0 not in cmap.code_lengths
    # 반환 자체가 종료의 증거 — 수정 전에는 i 가 전진하지 못해 무한 루프였다
    assert isinstance(cmap.decode(b"\x00\x01"), str)


# ── C2: bfrange 목적지가 ']' → ValueError 가 리더 밖으로 탈출 ──

def test_bfrange_bracket_destination_does_not_raise():
    data = b"1 beginbfrange\n<00> <01> ]\nendbfrange\n"
    cmap = parse_tounicode(data)
    assert isinstance(cmap.decode(b"\x00"), str)


def test_reader_survives_malformed_tounicode(tmp_path):
    bad_cmap = b"1 beginbfrange\n<00> <01> ]\nendbfrange\n"
    content = b"BT /F1 12 Tf (ok) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
           "/Contents 5 0 R >>",
        4: "<< /Type /Font /Subtype /Type0 /ToUnicode 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(bad_cmap), bad_cmap),
    }
    path = _write(tmp_path, "badcmap.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)  # 예외가 새어 나오면 안 된다

    assert doc.source_format == "pdf"


# ── M1: 중첩 깊이 무제한 → RecursionError 크래시 ──

def test_deeply_nested_array_raises_syntax_error_not_recursion_error():
    payload = b"[" * 20000
    with pytest.raises(PDFSyntaxError):
        PDFLexer(payload).parse_object()


def test_reader_reports_error_on_deeply_nested_object(tmp_path):
    objects = _minimal_objects()
    objects[5] = b"[" * 20000
    path = _write(tmp_path, "deep.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)  # RecursionError 로 죽으면 안 된다

    assert doc.source_format == "pdf"


# ── M3: 스캔 폴백 시 암호화 감지 무력화 ──

def test_encrypted_pdf_detected_even_with_broken_startxref(tmp_path):
    data = _build_pdf(_minimal_objects(), trailer_extra="/Encrypt 4 0 R")
    data = data.replace(b"startxref", b"startxrfX")
    path = _write(tmp_path, "enc-broken.pdf", data)

    doc = PDFReader().read(path)

    assert doc.sections == []
    assert any("암호화" in e for e in doc.errors)


# ── M4: ToUnicode 없는 Type0/Identity-H → 제어문자 유출 ──

def test_cid_font_without_tounicode_warns_and_drops_garbage(tmp_path):
    content = b"BT /F1 12 Tf <00120013> Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
           "/Contents 5 0 R >>",
        4: "<< /Type /Font /Subtype /Type0 /Encoding /Identity-H >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
    }
    path = _write(tmp_path, "cid.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)
    markdown = __import__("dochan.output.markdown", fromlist=["to_markdown"]).to_markdown(doc)

    assert "\x00" not in markdown  # NUL 이 본문으로 새면 안 된다
    assert any("ToUnicode" in e for e in doc.errors)


# ── 보안 한도: 압축 폭탄 해제 상한 ──

def test_flate_bomb_truncated_at_limit_with_warning():
    bomb = zlib.compress(b"\x00" * (MAX_DECODED_SIZE + 10 * 1024 * 1024))
    warnings = []

    out = decode_stream({"Filter": "FlateDecode"}, bomb, warnings)

    assert len(out) == MAX_DECODED_SIZE
    assert any("한도" in w for w in warnings)
