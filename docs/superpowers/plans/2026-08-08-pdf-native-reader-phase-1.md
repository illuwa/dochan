# PDF Native Reader Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native, stdlib-only PDF reader that extracts page-level text from simple digital PDFs with page-number provenance, routed through the existing `Document` model.

**Architecture:** A layered parser under `dochan/pdf/`: object-syntax lexer (`objects.py`), stream filter decoding (`filters.py`), file structure with classic xref tables plus object-scan fallback (`structure.py`), ToUnicode CMap decoding for Korean/CID text (`cmap.py`), content-stream text operator interpretation (`content.py`), and a `PDFReader` (`reader.py`) that maps each page to a `Section` with `Provenance(page=N)`. Encrypted files, xref streams (PDF 1.5+), object streams, and scanned-only pages produce clear warnings instead of silent failure, per the design spec Phase 6 milestone.

**Tech Stack:** Python 3.9+, standard library only (`re`, `zlib`, `binascii`, `base64`). No new dependencies.

## Global Constraints

- Core remains MIT/permissive-only; no external conversion engines.
- Preserve existing HWP/HWPX/DOC/PPT/XLS/DOCX/PPTX/XLSX behavior and all 463 existing tests.
- Validation command in this workspace: `PYTHONPATH=. pytest tests/ -q` (a PyPI-installed dochan shadows the repo without `PYTHONPATH`).
- TDD: write a failing test, verify it fails for the expected reason, then implement.
- Commit per task on the current feature branch (`illuwa/pacu`).

## File Structure

- Create `dochan/pdf/__init__.py`: package marker.
- Create `dochan/pdf/objects.py`: PDF object-syntax lexer/parser (names, strings, numbers, arrays, dicts, refs, streams).
- Create `dochan/pdf/filters.py`: FlateDecode / ASCIIHexDecode / ASCII85Decode; warnings for unsupported filters.
- Create `dochan/pdf/structure.py`: startxref discovery, classic xref table + trailer chain, object cache, page-tree traversal with inherited resources, object-scan fallback.
- Create `dochan/pdf/cmap.py`: ToUnicode CMap parsing (codespacerange/bfchar/bfrange) and byte-code decoding.
- Create `dochan/pdf/content.py`: content-stream tokenizer and text operator interpreter producing text lines.
- Create `dochan/pdf/reader.py`: `PDFReader.read(file_path) -> Document` with page sections, provenance, warnings.
- Modify `dochan/reader.py`: route `.pdf` extension and `%PDF-` magic.
- Modify `dochan/batch.py`: add `.pdf` to default extensions.
- Modify `dochan/cli.py`: docstring example only (commands are format-agnostic).
- Create `tests/test_pdf_objects.py`, `tests/test_pdf_filters.py`, `tests/test_pdf_structure.py`, `tests/test_pdf_cmap.py`, `tests/test_pdf_content.py`, `tests/test_pdf_reader.py`.
- Modify `README.md`, `docs/superpowers/specs/2026-06-20-native-universal-document-conversion-design.md`, `CHANGELOG.md`.

## Task 1: PDF Object Syntax Parser

**Files:**
- Create: `dochan/pdf/__init__.py`
- Create: `dochan/pdf/objects.py`
- Test: `tests/test_pdf_objects.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_pdf_objects.py`:

```python
import pytest

from dochan.pdf.objects import (
    PDFLexer,
    PDFName,
    PDFRef,
    PDFStream,
    PDFSyntaxError,
    parse_indirect_object,
)


def _parse(data: bytes):
    return PDFLexer(data).parse_object()


def test_parses_scalars():
    assert _parse(b"true") is True
    assert _parse(b"false") is False
    assert _parse(b"null") is None
    assert _parse(b"42") == 42
    assert _parse(b"-17") == -17
    assert _parse(b"3.14") == pytest.approx(3.14)


def test_parses_name_with_hash_escape():
    name = _parse(b"/A#20B")
    assert isinstance(name, PDFName)
    assert name == "A B"


def test_parses_literal_string_with_escapes_and_nesting():
    assert _parse(rb"(a\(b\)c)") == b"a(b)c"
    assert _parse(b"(nested (paren) ok)") == b"nested (paren) ok"
    assert _parse(rb"(tab\there)") == b"tab\there"
    assert _parse(rb"(\101\102)") == b"AB"


def test_parses_hex_string_with_odd_digits():
    assert _parse(b"<48454C4C4F>") == b"HELLO"
    assert _parse(b"<48 45 4C>") == b"HEL"
    assert _parse(b"<484>") == b"H@"


def test_parses_array_and_dict_with_refs():
    obj = _parse(b"<< /Kids [3 0 R 4 0 R] /Count 2 /Name /Pages >>")
    assert obj["Kids"] == [PDFRef(3, 0), PDFRef(4, 0)]
    assert obj["Count"] == 2
    assert obj["Name"] == "Pages"


def test_skips_comments_between_tokens():
    assert _parse(b"% comment\n7") == 7


def test_parse_indirect_object_plain():
    data = b"12 0 obj\n<< /Type /Catalog >>\nendobj\n"
    num, gen, obj = parse_indirect_object(data, 0)
    assert (num, gen) == (12, 0)
    assert obj["Type"] == "Catalog"


def test_parse_indirect_object_stream_with_length():
    body = b"BT (hi) Tj ET"
    data = b"5 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\nendobj\n" % (len(body), body)
    num, gen, obj = parse_indirect_object(data, 0)
    assert isinstance(obj, PDFStream)
    assert obj.raw == body


def test_parse_indirect_object_stream_with_wrong_length_falls_back():
    body = b"0123456789"
    data = b"5 0 obj\n<< /Length 99999 >>\nstream\n%s\nendstream\nendobj\n" % body
    _, _, obj = parse_indirect_object(data, 0)
    assert isinstance(obj, PDFStream)
    assert obj.raw == body


def test_parse_indirect_object_stream_with_indirect_length():
    body = b"abcdef"
    data = b"5 0 obj\n<< /Length 6 0 R >>\nstream\n%s\nendstream\nendobj\n" % body
    _, _, obj = parse_indirect_object(data, 0, resolve=lambda ref: 6)
    assert obj.raw == body


def test_raises_on_broken_header():
    with pytest.raises(PDFSyntaxError):
        parse_indirect_object(b"nonsense here", 0)
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_pdf_objects.py -q`
Expected: `ModuleNotFoundError: No module named 'dochan.pdf'`

- [x] **Step 3: Write minimal implementation**

Create `dochan/pdf/__init__.py`:

```python
"""네이티브 PDF 리더."""
```

Create `dochan/pdf/objects.py`:

```python
"""PDF 객체 문법 파서 — 렉서와 기본 객체 파싱.

PDF 32000-1:2008 §7.3 의 객체 문법(불리언, 숫자, 문자열, 이름, 배열,
사전, 스트림, null, 간접 참조)을 표준 라이브러리만으로 파싱한다.
"""
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

WHITESPACE = b"\x00\t\n\x0c\r "
DELIMITERS = b"()<>[]{}/%"

MAX_COLLECTION_ITEMS = 100_000


class PDFSyntaxError(ValueError):
    """PDF 객체 문법 위반."""


@dataclass(frozen=True)
class PDFRef:
    """간접 객체 참조 (`12 0 R`)."""
    num: int
    gen: int


class PDFName(str):
    """PDF 이름 객체 (`/Name`). str 부분클래스라 사전 키로 그대로 쓴다."""


@dataclass
class PDFStream:
    """스트림 객체 — 사전과 원본(필터 미해제) 바이트."""
    dictionary: dict
    raw: bytes


class PDFLexer:
    """바이트 버퍼 위의 순차 파서."""

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def _peek(self) -> int:
        if self.pos >= len(self.data):
            return -1
        return self.data[self.pos]

    def skip_whitespace(self) -> None:
        data, n = self.data, len(self.data)
        while self.pos < n:
            ch = data[self.pos]
            if ch in WHITESPACE:
                self.pos += 1
            elif ch == 0x25:  # '%' 주석은 줄 끝까지
                while self.pos < n and data[self.pos] not in b"\r\n":
                    self.pos += 1
            else:
                return

    def read_token(self) -> bytes:
        start = self.pos
        data, n = self.data, len(self.data)
        while self.pos < n:
            ch = data[self.pos]
            if ch in WHITESPACE or ch in DELIMITERS:
                break
            self.pos += 1
        return data[start:self.pos]

    def parse_object(self) -> Any:
        self.skip_whitespace()
        ch = self._peek()
        if ch < 0:
            raise PDFSyntaxError("예상치 못한 EOF")
        if ch == 0x3C:  # '<'
            if self.data[self.pos:self.pos + 2] == b"<<":
                return self._parse_dict()
            return self._parse_hex_string()
        if ch == 0x28:  # '('
            return self._parse_literal_string()
        if ch == 0x2F:  # '/'
            return self._parse_name()
        if ch == 0x5B:  # '['
            return self._parse_array()
        token = self.read_token()
        if not token:
            raise PDFSyntaxError(
                f"파싱할 수 없는 문자: {self.data[self.pos:self.pos + 8]!r}"
            )
        if token == b"true":
            return True
        if token == b"false":
            return False
        if token == b"null":
            return None
        return self._parse_number_or_ref(token)

    def _parse_number_or_ref(self, token: bytes) -> Any:
        try:
            if b"." in token:
                return float(token)
            value = int(token)
        except ValueError:
            raise PDFSyntaxError(f"잘못된 숫자 토큰: {token!r}")
        if value >= 0:
            saved = self.pos
            self.skip_whitespace()
            token2 = self.read_token()
            if token2.isdigit():
                self.skip_whitespace()
                if self.read_token() == b"R":
                    return PDFRef(value, int(token2))
            self.pos = saved
        return value

    def _parse_name(self) -> PDFName:
        self.pos += 1  # '/'
        raw = self.read_token()
        out = bytearray()
        i = 0
        while i < len(raw):
            if raw[i:i + 1] == b"#" and i + 2 < len(raw):
                try:
                    out.append(int(raw[i + 1:i + 3], 16))
                    i += 3
                    continue
                except ValueError:
                    pass
            out.append(raw[i])
            i += 1
        return PDFName(out.decode("utf-8", errors="replace"))

    def _parse_literal_string(self) -> bytes:
        self.pos += 1  # '('
        out = bytearray()
        depth = 1
        data, n = self.data, len(self.data)
        while self.pos < n:
            ch = data[self.pos]
            if ch == 0x5C:  # '\'
                self.pos += 1
                if self.pos >= n:
                    break
                esc = data[self.pos]
                if esc == 0x6E:
                    out.append(0x0A)
                elif esc == 0x72:
                    out.append(0x0D)
                elif esc == 0x74:
                    out.append(0x09)
                elif esc == 0x62:
                    out.append(0x08)
                elif esc == 0x66:
                    out.append(0x0C)
                elif esc in (0x28, 0x29, 0x5C):
                    out.append(esc)
                elif 0x30 <= esc <= 0x37:  # 8진 이스케이프 최대 3자리
                    octal = chr(esc)
                    for _ in range(2):
                        nxt = data[self.pos + 1] if self.pos + 1 < n else -1
                        if 0x30 <= nxt <= 0x37:
                            self.pos += 1
                            octal += chr(nxt)
                        else:
                            break
                    out.append(int(octal, 8) & 0xFF)
                elif esc in (0x0D, 0x0A):  # 줄 연속은 무시
                    if esc == 0x0D and self.pos + 1 < n and data[self.pos + 1] == 0x0A:
                        self.pos += 1
                else:
                    out.append(esc)
                self.pos += 1
            elif ch == 0x28:
                depth += 1
                out.append(ch)
                self.pos += 1
            elif ch == 0x29:
                depth -= 1
                self.pos += 1
                if depth == 0:
                    return bytes(out)
                out.append(ch)
            else:
                out.append(ch)
                self.pos += 1
        raise PDFSyntaxError("닫히지 않은 리터럴 문자열")

    def _parse_hex_string(self) -> bytes:
        self.pos += 1  # '<'
        end = self.data.find(b">", self.pos)
        if end < 0:
            raise PDFSyntaxError("닫히지 않은 16진 문자열")
        hex_chars = bytes(c for c in self.data[self.pos:end] if c not in WHITESPACE)
        self.pos = end + 1
        if len(hex_chars) % 2:
            hex_chars += b"0"
        try:
            return bytes.fromhex(hex_chars.decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            raise PDFSyntaxError("잘못된 16진 문자열")

    def _parse_array(self) -> list:
        self.pos += 1  # '['
        items = []
        while True:
            self.skip_whitespace()
            if self._peek() == 0x5D:
                self.pos += 1
                return items
            if self._peek() < 0:
                raise PDFSyntaxError("닫히지 않은 배열")
            if len(items) >= MAX_COLLECTION_ITEMS:
                raise PDFSyntaxError("배열 항목 수가 한도를 초과")
            items.append(self.parse_object())

    def _parse_dict(self) -> dict:
        self.pos += 2  # '<<'
        result = {}
        while True:
            self.skip_whitespace()
            if self.data[self.pos:self.pos + 2] == b">>":
                self.pos += 2
                return result
            if self._peek() != 0x2F:
                raise PDFSyntaxError("사전 키는 이름이어야 함")
            if len(result) >= MAX_COLLECTION_ITEMS:
                raise PDFSyntaxError("사전 항목 수가 한도를 초과")
            key = self._parse_name()
            result[str(key)] = self.parse_object()


def parse_indirect_object(
    data: bytes,
    offset: int,
    resolve: Optional[Callable[[PDFRef], Any]] = None,
) -> Tuple[int, int, Any]:
    """`num gen obj ... endobj` 를 파싱한다.

    resolve: 스트림 /Length 가 간접 참조일 때 정수로 해석하는 콜백.
    /Length 가 틀리거나 없으면 `endstream` 탐색으로 보정한다.
    """
    lexer = PDFLexer(data, offset)
    lexer.skip_whitespace()
    num_tok = lexer.read_token()
    lexer.skip_whitespace()
    gen_tok = lexer.read_token()
    lexer.skip_whitespace()
    obj_tok = lexer.read_token()
    if not num_tok.isdigit() or not gen_tok.isdigit() or obj_tok != b"obj":
        raise PDFSyntaxError(f"오프셋 {offset}: 간접 객체 헤더가 아님")
    obj = lexer.parse_object()
    lexer.skip_whitespace()
    keyword_pos = lexer.pos
    keyword = lexer.read_token()
    if keyword == b"stream" and isinstance(obj, dict):
        if lexer.data[lexer.pos:lexer.pos + 2] == b"\r\n":
            lexer.pos += 2
        elif lexer.data[lexer.pos:lexer.pos + 1] in (b"\n", b"\r"):
            lexer.pos += 1
        start = lexer.pos
        length = obj.get("Length")
        if resolve is not None and isinstance(length, PDFRef):
            length = resolve(length)
        raw = None
        if isinstance(length, int) and 0 <= length <= len(data) - start:
            candidate_end = start + length
            tail = data[candidate_end:candidate_end + 20]
            if tail.lstrip(WHITESPACE).startswith(b"endstream"):
                raw = data[start:candidate_end]
        if raw is None:
            end = data.find(b"endstream", start)
            if end < 0:
                raise PDFSyntaxError("endstream 누락")
            raw = data[start:end].rstrip(b"\r\n")
        return int(num_tok), int(gen_tok), PDFStream(obj, raw)
    lexer.pos = keyword_pos
    return int(num_tok), int(gen_tok), obj
```

- [x] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_pdf_objects.py -q`
Expected: `11 passed`

- [x] **Step 5: Run all tests**

Run: `PYTHONPATH=. pytest tests/ -q`
Expected: `474 passed` (463 existing + 11)

- [x] **Step 6: Commit**

```bash
git add dochan/pdf/__init__.py dochan/pdf/objects.py tests/test_pdf_objects.py
git commit -m "feat(pdf): PDF 객체 문법 파서 추가"
```

## Task 2: Stream Filter Decoding

**Files:**
- Create: `dochan/pdf/filters.py`
- Test: `tests/test_pdf_filters.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_pdf_filters.py`:

```python
import zlib

from dochan.pdf.filters import decode_stream


def test_flate_decode_roundtrip():
    warnings = []
    raw = zlib.compress(b"hello pdf")
    assert decode_stream({"Filter": "FlateDecode"}, raw, warnings) == b"hello pdf"
    assert warnings == []


def test_no_filter_returns_raw():
    assert decode_stream({}, b"plain", []) == b"plain"


def test_filter_chain_applies_in_order():
    warnings = []
    payload = zlib.compress(b"chained")
    hex_encoded = payload.hex().encode("ascii") + b">"
    result = decode_stream({"Filter": ["ASCIIHexDecode", "FlateDecode"]}, hex_encoded, warnings)
    assert result == b"chained"


def test_ascii_hex_decode_ignores_whitespace():
    assert decode_stream({"Filter": "ASCIIHexDecode"}, b"68 65 6C 6C 6F>", []) == b"hello"


def test_image_filter_returns_empty_without_warning_spam():
    warnings = []
    assert decode_stream({"Filter": "DCTDecode"}, b"\xff\xd8jpeg", warnings) == b""


def test_unknown_filter_warns():
    warnings = []
    assert decode_stream({"Filter": "LZWDecode"}, b"data", warnings) == b""
    assert any("LZWDecode" in w for w in warnings)


def test_corrupt_flate_warns_and_returns_empty():
    warnings = []
    assert decode_stream({"Filter": "FlateDecode"}, b"not-zlib", warnings) == b""
    assert any("FlateDecode" in w for w in warnings)


def test_predictor_warns():
    warnings = []
    raw = zlib.compress(b"x")
    decode_stream({"Filter": "FlateDecode", "DecodeParms": {"Predictor": 12}}, raw, warnings)
    assert any("Predictor" in w for w in warnings)
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_pdf_filters.py -q`
Expected: `ModuleNotFoundError: No module named 'dochan.pdf.filters'`

- [x] **Step 3: Write minimal implementation**

Create `dochan/pdf/filters.py`:

```python
"""PDF 스트림 필터 해제 — 표준 라이브러리만 사용."""
import base64
import binascii
import zlib
from typing import List

MAX_DECODED_SIZE = 50 * 1024 * 1024

# 이미지 압축 계열 — 텍스트 추출 대상이 아니므로 조용히 빈 값 처리
_IMAGE_FILTERS = {"DCTDecode", "DCT", "JPXDecode", "CCITTFaxDecode", "CCF", "JBIG2Decode"}

_WHITESPACE = b"\x00\t\n\x0c\r "


def decode_stream(stream_dict: dict, raw: bytes, warnings: List[str]) -> bytes:
    """스트림 사전의 /Filter 체인을 적용해 원본 바이트를 해제한다."""
    filters = stream_dict.get("Filter")
    if filters is None:
        return raw
    if not isinstance(filters, list):
        filters = [filters]

    parms = stream_dict.get("DecodeParms") or stream_dict.get("DP")
    if isinstance(parms, dict) and isinstance(parms.get("Predictor"), int) \
            and parms["Predictor"] > 1:
        warnings.append("WARN: PDF Predictor 인코딩은 아직 지원하지 않음 — 텍스트가 손상될 수 있음")

    data = raw
    for filt in filters:
        name = str(filt)
        if name in ("FlateDecode", "Fl"):
            data = _flate(data, warnings)
        elif name in ("ASCIIHexDecode", "AHx"):
            data = _ascii_hex(data, warnings)
        elif name in ("ASCII85Decode", "A85"):
            data = _ascii85(data, warnings)
        elif name in _IMAGE_FILTERS:
            return b""
        else:
            warnings.append(f"WARN: 지원하지 않는 PDF 필터: {name}")
            return b""
    return data


def _flate(data: bytes, warnings: List[str]) -> bytes:
    try:
        decomp = zlib.decompressobj()
        out = decomp.decompress(data, MAX_DECODED_SIZE)
        if decomp.unconsumed_tail:
            warnings.append("WARN: PDF 스트림이 해제 한도를 초과하여 잘림")
        return out
    except zlib.error as e:
        warnings.append(f"WARN: FlateDecode 실패: {e}")
        return b""


def _ascii_hex(data: bytes, warnings: List[str]) -> bytes:
    text = data.split(b">")[0]
    text = bytes(c for c in text if c not in _WHITESPACE)
    if len(text) % 2:
        text += b"0"
    try:
        return binascii.unhexlify(text)
    except (binascii.Error, ValueError):
        warnings.append("WARN: ASCIIHexDecode 실패")
        return b""


def _ascii85(data: bytes, warnings: List[str]) -> bytes:
    text = bytes(c for c in data if c not in _WHITESPACE)
    if text.startswith(b"<~"):
        text = text[2:]
    if text.endswith(b"~>"):
        text = text[:-2]
    try:
        return base64.a85decode(text)
    except ValueError:
        warnings.append("WARN: ASCII85Decode 실패")
        return b""
```

- [x] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_pdf_filters.py -q`
Expected: `8 passed`

- [x] **Step 5: Commit**

```bash
git add dochan/pdf/filters.py tests/test_pdf_filters.py
git commit -m "feat(pdf): 스트림 필터 해제(Flate/ASCIIHex/ASCII85) 추가"
```

## Task 3: File Structure — xref, Trailer, Page Tree

**Files:**
- Create: `dochan/pdf/structure.py`
- Test: `tests/test_pdf_structure.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_pdf_structure.py`. The `_build_pdf` helper assembles a classic-xref PDF with correct offsets; reuse it in later tasks by importing from this module.

```python
from dochan.pdf.objects import PDFRef, PDFStream
from dochan.pdf.structure import PDFFile


def _build_pdf(objects, trailer_extra=""):
    """{번호: 본문 str|bytes} 로 고전 xref PDF 를 조립한다. Root 는 1번 가정."""
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        body = objects[num]
        if isinstance(body, str):
            body = body.encode("latin-1")
        out += b"%d 0 obj\n" % num
        out += body
        out += b"\nendobj\n"
    xref_pos = len(out)
    max_num = max(objects)
    out += b"xref\n0 %d\n" % (max_num + 1)
    out += b"0000000000 65535 f \n"
    for num in range(1, max_num + 1):
        if num in offsets:
            out += ("%010d 00000 n \n" % offsets[num]).encode("ascii")
        else:
            out += b"0000000000 65535 f \n"
    trailer = "<< /Size %d /Root 1 0 R %s >>" % (max_num + 1, trailer_extra)
    out += b"trailer\n" + trailer.encode("latin-1") + b"\n"
    out += b"startxref\n%d\n%%%%EOF\n" % xref_pos
    return bytes(out)


def _minimal_objects(content=b"BT (x) Tj ET"):
    return {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
           "/Contents 5 0 R >>",
        4: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
    }


def test_parses_xref_and_returns_objects():
    pdf = PDFFile(_build_pdf(_minimal_objects()))
    catalog = pdf.resolve(pdf.trailer["Root"])
    assert catalog["Type"] == "Catalog"
    stream = pdf.resolve(PDFRef(5, 0))
    assert isinstance(stream, PDFStream)
    assert stream.raw == b"BT (x) Tj ET"


def test_pages_traversal_with_inherited_resources():
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 "
           "/Resources << /Font << /F1 6 0 R >> >> >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R "
           "/Resources << /Font << /F2 6 0 R >> >> >>",
        5: b"<< /Length 4 >>\nstream\nBT E\nendstream",
        6: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    pdf = PDFFile(_build_pdf(objects))
    pages = pdf.pages()
    assert len(pages) == 2
    assert "F1" in pages[0][1]["Font"]
    assert "F2" in pages[1][1]["Font"]


def test_broken_startxref_falls_back_to_scan():
    data = _build_pdf(_minimal_objects())
    data = data.replace(b"startxref", b"startxrfX")
    pdf = PDFFile(data)
    assert any("스캔" in w for w in pdf.warnings)
    assert len(pdf.pages()) == 1


def test_xref_stream_detected_and_scan_fallback():
    data = _build_pdf(_minimal_objects())
    # startxref 가 xref 테이블이 아닌 객체(1번)를 가리키게 조작
    xref_pos = data.rindex(b"startxref")
    obj1_pos = data.index(b"1 0 obj")
    tail = b"startxref\n%d\n%%%%EOF\n" % obj1_pos
    pdf = PDFFile(data[:xref_pos] + tail)
    assert any("xref 스트림" in w for w in pdf.warnings)
    assert len(pdf.pages()) == 1


def test_encrypted_trailer_sets_flag_and_warning():
    pdf = PDFFile(_build_pdf(_minimal_objects(), trailer_extra="/Encrypt 4 0 R"))
    assert pdf.encrypted
    assert any("암호화" in w for w in pdf.warnings)


def test_missing_root_reports_warning():
    objects = {1: "<< /Type /NotACatalog >>"}
    data = _build_pdf(objects)
    data = data.replace(b"/Root 1 0 R", b"")
    pdf = PDFFile(data)
    assert pdf.pages() == []
    assert any("Root" in w or "카탈로그" in w for w in pdf.warnings)


def test_circular_page_tree_terminates():
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [2 0 R] /Count 1 >>",
    }
    pdf = PDFFile(_build_pdf(objects))
    assert pdf.pages() == []
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_pdf_structure.py -q`
Expected: `ModuleNotFoundError: No module named 'dochan.pdf.structure'`

- [x] **Step 3: Write minimal implementation**

Create `dochan/pdf/structure.py`:

```python
"""PDF 파일 구조 — startxref, 고전 xref 테이블, trailer, 페이지 트리.

xref 스트림(PDF 1.5+)과 객체 스트림은 이번 마일스톤에서 지원하지 않는다.
발견하면 경고를 남기고 `N G obj` 패턴 스캔으로 대체 복구를 시도한다.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from .objects import PDFLexer, PDFRef, PDFSyntaxError, parse_indirect_object

MAX_XREF_SECTIONS = 32
MAX_OBJECTS = 500_000
MAX_PAGES = 10_000
MAX_RESOLVE_DEPTH = 32
MAX_TREE_DEPTH = 64
_SCAN_ROOT_LIMIT = 10_000

_OBJ_RE = re.compile(rb"(?<!\d)(\d{1,10})\s+(\d{1,5})\s+obj\b")


class PDFFile:
    """파싱된 PDF 파일 — 객체 접근과 페이지 트리 순회."""

    def __init__(self, data: bytes):
        self.data = data
        self.warnings: List[str] = []
        self.trailer: Dict[str, Any] = {}
        self.xref: Dict[int, int] = {}  # 객체 번호 → 파일 오프셋
        self.encrypted = False
        self._cache: Dict[int, Any] = {}
        self._rescanned = False
        self._parse_structure()

    # ── 구조 파싱 ──

    def _parse_structure(self) -> None:
        start = self._find_startxref()
        ok = start is not None and self._parse_xref_chain(start)
        if not ok or "Root" not in self.trailer:
            self._scan_objects()
        if self.trailer.get("Encrypt") is not None:
            self.encrypted = True
            self.warnings.append("WARN: 암호화된 PDF — 텍스트 추출을 지원하지 않음")

    def _find_startxref(self) -> Optional[int]:
        tail = self.data[-2048:]
        idx = tail.rfind(b"startxref")
        if idx < 0:
            self.warnings.append("WARN: startxref 를 찾지 못함 — 객체 스캔으로 대체")
            return None
        lexer = PDFLexer(tail, idx + len(b"startxref"))
        lexer.skip_whitespace()
        token = lexer.read_token()
        if not token.isdigit():
            self.warnings.append("WARN: startxref 오프셋 손상 — 객체 스캔으로 대체")
            return None
        offset = int(token)
        if offset >= len(self.data):
            self.warnings.append("WARN: startxref 오프셋이 파일 범위 밖 — 객체 스캔으로 대체")
            return None
        return offset

    def _parse_xref_chain(self, offset: int) -> bool:
        seen = set()
        current: Optional[int] = offset
        while current is not None and current not in seen and len(seen) < MAX_XREF_SECTIONS:
            seen.add(current)
            lexer = PDFLexer(self.data, current)
            lexer.skip_whitespace()
            if lexer.read_token() != b"xref":
                self.warnings.append(
                    "WARN: xref 스트림(PDF 1.5+)은 아직 지원하지 않음 — 객체 스캔으로 대체"
                )
                return False
            trailer = self._parse_xref_table(lexer)
            if trailer is None:
                return False
            for key, value in trailer.items():
                self.trailer.setdefault(key, value)  # 최신 trailer 우선
            prev = trailer.get("Prev")
            current = prev if isinstance(prev, int) else None
        return True

    def _parse_xref_table(self, lexer: PDFLexer) -> Optional[dict]:
        while True:
            lexer.skip_whitespace()
            token = lexer.read_token()
            if token == b"trailer":
                lexer.skip_whitespace()
                try:
                    obj = lexer.parse_object()
                except PDFSyntaxError:
                    self.warnings.append("WARN: trailer 손상 — 객체 스캔으로 대체")
                    return None
                return obj if isinstance(obj, dict) else None
            if not token.isdigit():
                self.warnings.append("WARN: xref 테이블 손상 — 객체 스캔으로 대체")
                return None
            start_num = int(token)
            lexer.skip_whitespace()
            count_tok = lexer.read_token()
            if not count_tok.isdigit() or int(count_tok) > MAX_OBJECTS:
                self.warnings.append("WARN: xref 테이블 손상 — 객체 스캔으로 대체")
                return None
            for i in range(int(count_tok)):
                lexer.skip_whitespace()
                off_tok = lexer.read_token()
                lexer.skip_whitespace()
                gen_tok = lexer.read_token()
                lexer.skip_whitespace()
                kind = lexer.read_token()
                if not off_tok.isdigit() or not gen_tok.isdigit() or kind not in (b"n", b"f"):
                    self.warnings.append("WARN: xref 항목 손상 — 객체 스캔으로 대체")
                    return None
                obj_num = start_num + i
                if kind == b"n" and obj_num not in self.xref:
                    self.xref[obj_num] = int(off_tok)

    def _scan_objects(self) -> None:
        self.xref = {}
        self._cache = {}
        count = 0
        for match in _OBJ_RE.finditer(self.data):
            # 파일 뒤쪽 정의가 최신(증분 갱신)이므로 덮어쓴다
            self.xref[int(match.group(1))] = match.start()
            count += 1
            if count > MAX_OBJECTS:
                self.warnings.append("WARN: 객체 수가 한도를 초과 — 일부만 파싱")
                break
        if "Root" not in self.trailer:
            self._find_root_by_scan()

    def _find_root_by_scan(self) -> None:
        for num in sorted(self.xref)[:_SCAN_ROOT_LIMIT]:
            try:
                obj = self.get_object(PDFRef(num, 0))
            except Exception:
                continue
            if isinstance(obj, dict) and str(obj.get("Type", "")) == "Catalog":
                self.trailer["Root"] = PDFRef(num, 0)
                return

    # ── 객체 접근 ──

    def get_object(self, ref: PDFRef) -> Any:
        if ref.num in self._cache:
            return self._cache[ref.num]
        offset = self.xref.get(ref.num)
        if offset is None or offset >= len(self.data):
            return None
        self._cache[ref.num] = None  # 순환 참조 가드
        try:
            num, _gen, obj = parse_indirect_object(self.data, offset, resolve=self.resolve)
        except PDFSyntaxError as e:
            self.warnings.append(f"WARN: 객체 {ref.num} 파싱 실패: {e}")
            return None
        if num != ref.num:
            if not self._rescanned:
                self._rescanned = True
                self.warnings.append("WARN: xref 오프셋 불일치 — 객체 스캔으로 재구성")
                self._scan_objects()
                return self.get_object(ref)
            self.warnings.append(f"WARN: 객체 {ref.num} 오프셋이 {num} 을 가리킴")
            return None
        self._cache[ref.num] = obj
        return obj

    def resolve(self, obj: Any, depth: int = 0) -> Any:
        while isinstance(obj, PDFRef):
            if depth > MAX_RESOLVE_DEPTH:
                return None
            obj = self.get_object(obj)
            depth += 1
        return obj

    # ── 페이지 트리 ──

    def pages(self) -> List[Tuple[dict, dict]]:
        """(페이지 사전, 유효 Resources) 목록을 문서 순서대로 반환."""
        root = self.resolve(self.trailer.get("Root"))
        if not isinstance(root, dict):
            self.warnings.append("WARN: PDF 카탈로그(Root)를 찾지 못함")
            return []
        pages_root = self.resolve(root.get("Pages"))
        if not isinstance(pages_root, dict):
            self.warnings.append("WARN: 페이지 트리를 찾지 못함")
            return []
        result: List[Tuple[dict, dict]] = []
        self._walk_pages(pages_root, {}, result, set(), 0)
        if not result:
            self.warnings.append("WARN: 페이지를 찾지 못함")
        return result

    def _walk_pages(self, node: dict, inherited: dict, result, visited, depth) -> None:
        if depth > MAX_TREE_DEPTH or len(result) >= MAX_PAGES:
            return
        node_id = id(node)
        if node_id in visited:
            return
        visited.add(node_id)
        resources = self.resolve(node.get("Resources"))
        effective = resources if isinstance(resources, dict) else inherited
        node_type = str(node.get("Type", ""))
        kids = node.get("Kids")
        if kids is not None and node_type != "Page":
            kids = self.resolve(kids)
            if not isinstance(kids, list):
                return
            for kid_ref in kids:
                kid = self.resolve(kid_ref)
                if isinstance(kid, dict):
                    self._walk_pages(kid, effective, result, visited, depth + 1)
            return
        result.append((node, effective))
```

- [x] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_pdf_structure.py -q`
Expected: `7 passed`

- [x] **Step 5: Commit**

```bash
git add dochan/pdf/structure.py tests/test_pdf_structure.py
git commit -m "feat(pdf): xref/trailer/페이지 트리 파싱과 객체 스캔 폴백 추가"
```

## Task 4: ToUnicode CMap Decoding

**Files:**
- Create: `dochan/pdf/cmap.py`
- Test: `tests/test_pdf_cmap.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_pdf_cmap.py`:

```python
from dochan.pdf.cmap import parse_tounicode


CMAP_KOREAN = b"""
/CIDInit /ProcSet findresource begin
begincmap
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
2 beginbfchar
<0001> <AC00>
<0002> <D55C>
endbfchar
1 beginbfrange
<0010> <0012> <0041>
endbfrange
endcmap
"""


def test_bfchar_maps_korean_codes():
    cmap = parse_tounicode(CMAP_KOREAN)
    assert cmap.decode(b"\x00\x01\x00\x02") == "가한"  # 가한


def test_bfrange_contiguous():
    cmap = parse_tounicode(CMAP_KOREAN)
    assert cmap.decode(b"\x00\x10\x00\x11\x00\x12") == "ABC"


def test_bfrange_array_form():
    data = b"""
    1 begincodespacerange
    <00> <FF>
    endcodespacerange
    1 beginbfrange
    <20> <22> [<0058> <0059> <005A>]
    endbfrange
    """
    cmap = parse_tounicode(data)
    assert cmap.decode(b"\x20\x21\x22") == "XYZ"


def test_multibyte_destination():
    data = b"""
    1 begincodespacerange
    <00> <FF>
    endcodespacerange
    1 beginbfchar
    <01> <00480069>
    endbfchar
    """
    cmap = parse_tounicode(data)
    assert cmap.decode(b"\x01") == "Hi"


def test_unmapped_code_becomes_replacement_char():
    cmap = parse_tounicode(CMAP_KOREAN)
    assert cmap.decode(b"\x99\x99") == "�"


def test_empty_cmap_defaults_to_single_byte():
    cmap = parse_tounicode(b"nothing here")
    assert cmap.code_lengths == {1}
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_pdf_cmap.py -q`
Expected: `ModuleNotFoundError: No module named 'dochan.pdf.cmap'`

- [x] **Step 3: Write minimal implementation**

Create `dochan/pdf/cmap.py`:

```python
"""ToUnicode CMap 파싱 — 문자 코드를 유니코드 문자열로 매핑.

한국어 PDF 는 대부분 Identity-H CID 폰트 + ToUnicode CMap 조합이므로
bfchar/bfrange 해석이 한글 텍스트 추출의 핵심이다.
"""
import re
from typing import Dict, Set, Tuple

_CODESPACE_RE = re.compile(rb"begincodespacerange(.*?)endcodespacerange", re.S)
_BF_CHAR_RE = re.compile(rb"beginbfchar(.*?)endbfchar", re.S)
_BF_RANGE_RE = re.compile(rb"beginbfrange(.*?)endbfrange", re.S)
_HEX_RE = re.compile(rb"<([0-9A-Fa-f]+)>")
_TOKEN_RE = re.compile(rb"<([0-9A-Fa-f]+)>|(\[)|(\])")

_MAX_RANGE = 65536


class ToUnicodeCMap:
    def __init__(self):
        # (코드 바이트 길이, 코드값) → 유니코드 문자열
        self.mapping: Dict[Tuple[int, int], str] = {}
        self.code_lengths: Set[int] = set()

    def decode(self, data: bytes) -> str:
        sizes = sorted(self.code_lengths)
        default = max(sizes)
        out = []
        i = 0
        n = len(data)
        while i < n:
            matched = False
            for size in sizes:
                if i + size > n:
                    continue
                code = int.from_bytes(data[i:i + size], "big")
                if (size, code) in self.mapping:
                    out.append(self.mapping[(size, code)])
                    i += size
                    matched = True
                    break
            if not matched:
                step = min(default, n - i)
                out.append("�")
                i += max(step, 1)
        return "".join(out)

    def _parse_bfrange_block(self, block: bytes) -> None:
        tokens = []
        for m in _TOKEN_RE.finditer(block):
            if m.group(1) is not None:
                tokens.append(m.group(1))
            elif m.group(2):
                tokens.append(b"[")
            else:
                tokens.append(b"]")
        i = 0
        n = len(tokens)
        while i < n - 2:
            lo_tok, hi_tok = tokens[i], tokens[i + 1]
            if lo_tok in (b"[", b"]") or hi_tok in (b"[", b"]"):
                i += 1
                continue
            length = len(lo_tok) // 2
            lo, hi = int(lo_tok, 16), int(hi_tok, 16)
            if hi < lo or hi - lo >= _MAX_RANGE:
                i += 3
                continue
            self.code_lengths.add(length)
            if tokens[i + 2] == b"[":
                j = i + 3
                code = lo
                while j < n and tokens[j] != b"]":
                    if code <= hi:
                        self.mapping[(length, code)] = _hex_to_text(tokens[j])
                    code += 1
                    j += 1
                i = j + 1
            else:
                base = int(tokens[i + 2], 16)
                digits = len(tokens[i + 2])
                for k in range(hi - lo + 1):
                    self.mapping[(length, lo + k)] = _int_to_text(base + k, digits)
                i += 3


def parse_tounicode(data: bytes) -> ToUnicodeCMap:
    cmap = ToUnicodeCMap()
    for block in _CODESPACE_RE.findall(data):
        for hex_tok in _HEX_RE.findall(block):
            cmap.code_lengths.add(max(len(hex_tok) // 2, 1))
    for block in _BF_CHAR_RE.findall(data):
        toks = _HEX_RE.findall(block)
        for i in range(0, len(toks) - 1, 2):
            src, dst = toks[i], toks[i + 1]
            length = max(len(src) // 2, 1)
            cmap.code_lengths.add(length)
            cmap.mapping[(length, int(src, 16))] = _hex_to_text(dst)
    for block in _BF_RANGE_RE.findall(data):
        cmap._parse_bfrange_block(block)
    if not cmap.code_lengths:
        cmap.code_lengths.add(1)
    return cmap


def _hex_to_text(hex_tok: bytes) -> str:
    """<0041> 형태의 UTF-16BE 16진 문자열을 파이썬 str 로 변환."""
    if len(hex_tok) % 2:
        hex_tok += b"0"
    raw = bytes.fromhex(hex_tok.decode("ascii"))
    return raw.decode("utf-16-be", errors="replace")


def _int_to_text(value: int, hex_digits: int) -> str:
    width = max(hex_digits, 4)
    if width % 4:
        width += 4 - (width % 4)
    try:
        raw = value.to_bytes(width // 2, "big")
    except OverflowError:
        return ""
    return raw.decode("utf-16-be", errors="replace")
```

- [x] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_pdf_cmap.py -q`
Expected: `6 passed`

- [x] **Step 5: Commit**

```bash
git add dochan/pdf/cmap.py tests/test_pdf_cmap.py
git commit -m "feat(pdf): ToUnicode CMap 파싱으로 한글 CID 텍스트 디코딩 지원"
```

## Task 5: Content Stream Text Extraction

**Files:**
- Create: `dochan/pdf/content.py`
- Test: `tests/test_pdf_content.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_pdf_content.py`:

```python
from dochan.pdf.content import ContentTextExtractor, default_byte_decoder


def _extract(content: bytes, decoders=None):
    return ContentTextExtractor(decoders or {}).extract(content)


def test_tj_and_td_produce_lines():
    content = b"BT /F1 12 Tf 72 720 Td (Line one) Tj 0 -14 Td (Line two) Tj ET"
    assert _extract(content) == ["Line one", "Line two"]


def test_horizontal_td_stays_on_same_line():
    content = b"BT (Left) Tj 100 0 Td (Right) Tj ET"
    assert _extract(content) == ["LeftRight"]


def test_tj_array_inserts_space_on_large_adjustment():
    content = b"BT [(Hello) -500 (world)] TJ ET"
    assert _extract(content) == ["Hello world"]


def test_tj_array_small_adjustment_no_space():
    content = b"BT [(Ke) -40 (rning)] TJ ET"
    assert _extract(content) == ["Kerning"]


def test_tstar_and_quote_start_new_lines():
    content = b"BT (a) Tj T* (b) Tj (c) ' ET"
    assert _extract(content) == ["a", "b", "c"]


def test_tm_same_y_keeps_line_different_y_breaks():
    content = (
        b"BT 1 0 0 1 72 700 Tm (Left) Tj 1 0 0 1 200 700 Tm (Right) Tj "
        b"1 0 0 1 72 680 Tm (Below) Tj ET"
    )
    assert _extract(content) == ["LeftRight", "Below"]


def test_font_decoder_selected_by_tf():
    decoders = {"F7": lambda raw: raw.decode("ascii").upper()}
    content = b"BT /F7 10 Tf (abc) Tj ET"
    assert _extract(content, decoders) == ["ABC"]


def test_hex_string_show():
    content = b"BT <414243> Tj ET"
    assert _extract(content) == ["ABC"]


def test_inline_image_is_skipped():
    content = b"BT (before) Tj ET BI /W 1 /H 1 ID \x00\xff\x28 EI BT (after) Tj ET"
    assert _extract(content) == ["before", "after"]


def test_default_decoder_cp1252():
    assert default_byte_decoder(b"caf\xe9") == "caf\xe9"
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_pdf_content.py -q`
Expected: `ModuleNotFoundError: No module named 'dochan.pdf.content'`

- [x] **Step 3: Write minimal implementation**

Create `dochan/pdf/content.py`:

```python
"""페이지 콘텐츠 스트림 해석 — 텍스트 연산자만 다룬다.

그래픽 연산자는 무시하고 BT/ET 블록의 텍스트 배치 연산자
(Tf, Td, TD, Tm, T*, Tj, TJ, ', ")로 줄 단위 텍스트를 재구성한다.
"""
from typing import Callable, Dict, List, Optional

from .objects import PDFLexer, PDFName, PDFSyntaxError

# TJ 배열에서 이보다 작은(더 음수인) 조정값은 단어 간격으로 본다 (1/1000 em 단위)
_SPACE_ADJUST_THRESHOLD = -180.0

_OPERAND_START = b"(</[0123456789+-."


def default_byte_decoder(raw: bytes) -> str:
    """ToUnicode 가 없는 단순 폰트의 기본 바이트 해석."""
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


class ContentTextExtractor:
    """콘텐츠 스트림에서 줄 단위 텍스트를 추출한다."""

    def __init__(self, font_decoders: Dict[str, Callable[[bytes], str]]):
        self._decoders = font_decoders
        self._decoder: Optional[Callable[[bytes], str]] = None
        self._last_y: Optional[float] = None

    def extract(self, content: bytes) -> List[str]:
        lexer = PDFLexer(content)
        lines: List[str] = []
        current: List[str] = []
        operands: List[object] = []
        n = len(content)
        while True:
            lexer.skip_whitespace()
            if lexer.pos >= n:
                break
            ch = content[lexer.pos]
            if ch in _OPERAND_START:
                try:
                    operands.append(lexer.parse_object())
                except PDFSyntaxError:
                    lexer.pos += 1
                continue
            token = lexer.read_token()
            if not token:
                lexer.pos += 1
                continue
            self._apply_operator(token, operands, lines, current, lexer)
            operands = []
        self._flush(lines, current)
        return lines

    def _apply_operator(self, op, operands, lines, current, lexer) -> None:
        if op == b"Tf":
            if len(operands) >= 2 and isinstance(operands[0], PDFName):
                self._decoder = self._decoders.get(str(operands[0]))
        elif op in (b"BT", b"ET", b"T*"):
            self._flush(lines, current)
            if op == b"BT":
                self._last_y = None
        elif op in (b"Td", b"TD"):
            ty = operands[1] if len(operands) >= 2 and isinstance(operands[1], (int, float)) else 0
            if ty != 0:
                self._flush(lines, current)
        elif op == b"Tm" and len(operands) >= 6:
            y = operands[5] if isinstance(operands[5], (int, float)) else None
            if self._last_y is None or y is None or abs(y - self._last_y) > 0.5:
                self._flush(lines, current)
            self._last_y = y
        elif op == b"Tj":
            if operands:
                self._show(operands[-1], current)
        elif op in (b"'", b'"'):
            self._flush(lines, current)
            if operands:
                self._show(operands[-1], current)
        elif op == b"TJ":
            if operands and isinstance(operands[-1], list):
                for item in operands[-1]:
                    if isinstance(item, bytes):
                        self._show(item, current)
                    elif isinstance(item, (int, float)) and item < _SPACE_ADJUST_THRESHOLD:
                        if current and not current[-1].endswith(" "):
                            current.append(" ")
        elif op == b"BI":
            # 인라인 이미지 — 이진 데이터를 렉서가 오해하지 않도록 EI 까지 건너뜀
            end = lexer.data.find(b"EI", lexer.pos)
            lexer.pos = len(lexer.data) if end < 0 else end + 2

    def _show(self, raw, current) -> None:
        if not isinstance(raw, bytes):
            return
        decoder = self._decoder or default_byte_decoder
        current.append(decoder(raw))

    @staticmethod
    def _flush(lines, current) -> None:
        if current:
            text = "".join(current).strip()
            if text:
                lines.append(text)
            current.clear()
```

- [x] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_pdf_content.py -q`
Expected: `10 passed`

- [x] **Step 5: Commit**

```bash
git add dochan/pdf/content.py tests/test_pdf_content.py
git commit -m "feat(pdf): 콘텐츠 스트림 텍스트 연산자 해석기 추가"
```

## Task 6: PDFReader — Document Assembly

**Files:**
- Create: `dochan/pdf/reader.py`
- Test: `tests/test_pdf_reader.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_pdf_reader.py`:

```python
import zlib

from dochan.pdf.reader import PDFReader
from tests.test_pdf_structure import _build_pdf, _minimal_objects


def _write(tmp_path, name, data: bytes):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_reads_single_page_text(tmp_path):
    content = b"BT /F1 12 Tf 72 720 Td (Hello PDF) Tj ET"
    path = _write(tmp_path, "one.pdf", _build_pdf(_minimal_objects(content)))

    doc = PDFReader().read(path)

    assert doc.source_format == "pdf"
    assert len(doc.sections) == 1
    para = doc.sections[0].elements[0]
    assert para.text == "Hello PDF"
    assert para.provenance.source_format == "pdf"
    assert para.provenance.page == 1
    assert doc.sections[0].provenance.page == 1


def test_reads_multiple_pages_in_order(tmp_path):
    c1 = b"BT (Page one) Tj ET"
    c2 = b"BT (Page two) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents 5 0 R >>",
        4: "<< /Type /Page /Parent 2 0 R /Contents 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c1), c1),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c2), c2),
    }
    path = _write(tmp_path, "two.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert len(doc.sections) == 2
    assert doc.sections[0].elements[0].text == "Page one"
    assert doc.sections[1].elements[0].text == "Page two"
    assert doc.sections[1].elements[0].provenance.page == 2


def test_flate_compressed_content(tmp_path):
    body = zlib.compress(b"BT (Compressed) Tj ET")
    objects = _minimal_objects()
    objects[5] = b"<< /Length %d /Filter /FlateDecode >>\nstream\n%s\nendstream" % (len(body), body)
    path = _write(tmp_path, "flate.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert doc.sections[0].elements[0].text == "Compressed"


def test_contents_array_concatenated(tmp_path):
    c1 = b"BT (First) Tj ET"
    c2 = b"BT (Second) Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Contents [5 0 R 6 0 R] >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c1), c1),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(c2), c2),
    }
    path = _write(tmp_path, "arr.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    texts = [p.text for p in doc.sections[0].elements]
    assert texts == ["First", "Second"]


def test_tounicode_font_decodes_korean(tmp_path):
    cmap = (
        b"1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        b"2 beginbfchar\n<0001> <AC00>\n<0002> <B098>\nendbfchar\n"
    )
    content = b"BT /F1 12 Tf <00010002> Tj ET"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
           "/Contents 5 0 R >>",
        4: "<< /Type /Font /Subtype /Type0 /ToUnicode 6 0 R >>",
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cmap), cmap),
    }
    path = _write(tmp_path, "kr.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert doc.sections[0].elements[0].text == "가나"  # 가나


def test_encrypted_pdf_stops_with_warning(tmp_path):
    data = _build_pdf(_minimal_objects(), trailer_extra="/Encrypt 4 0 R")
    path = _write(tmp_path, "enc.pdf", data)

    doc = PDFReader().read(path)

    assert doc.sections == []
    assert any("암호화" in e for e in doc.errors)


def test_scanned_only_page_warns(tmp_path):
    image = b"\xff\xd8fakejpeg"
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /Resources << /XObject << /Im1 5 0 R >> >> "
           "/Contents 6 0 R >>",
        5: b"<< /Length %d /Subtype /Image /Filter /DCTDecode >>\nstream\n%s\nendstream"
           % (len(image), image),
        6: b"<< /Length 10 >>\nstream\nq /Im1 Do Q\nendstream",
    }
    path = _write(tmp_path, "scan.pdf", _build_pdf(objects))

    doc = PDFReader().read(path)

    assert any("스캔" in e for e in doc.errors)


def test_non_pdf_file_reports_error(tmp_path):
    path = _write(tmp_path, "junk.pdf", b"this is not a pdf at all")

    doc = PDFReader().read(path)

    assert any("%PDF-" in e for e in doc.errors)
    assert doc.sections == []
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_pdf_reader.py -q`
Expected: `ModuleNotFoundError: No module named 'dochan.pdf.reader'`

- [x] **Step 3: Write minimal implementation**

Create `dochan/pdf/reader.py`:

```python
"""네이티브 PDF 리더 — 단순 디지털 PDF 의 페이지 텍스트 추출.

Phase 1 범위: 고전 xref 테이블, Flate/ASCIIHex/ASCII85 필터,
텍스트 연산자, ToUnicode CMap. 암호화·xref 스트림·객체 스트림·
스캔 전용 페이지는 명확한 경고로 보고한다.
"""
import os
from typing import Callable, Dict

from ..conversion import Provenance
from ..model.document import Document, Paragraph, Section, TextRun
from .content import ContentTextExtractor, default_byte_decoder
from .cmap import parse_tounicode
from .filters import decode_stream
from .objects import PDFStream
from .structure import PDFFile

MAX_FILE_SIZE = 500 * 1024 * 1024


class PDFReader:
    format_name = "pdf"
    extensions = (".pdf",)

    def read(self, file_path: str) -> Document:
        doc = Document(source_format="pdf")
        try:
            if os.path.getsize(file_path) > MAX_FILE_SIZE:
                doc.errors.append("ERR: PDF 파일이 크기 한도를 초과함")
                return doc
            with open(file_path, "rb") as f:
                data = f.read()
        except OSError as e:
            doc.errors.append(f"ERR: PDF 파일 열기 실패: {e}")
            return doc

        if b"%PDF-" not in data[:1024]:
            doc.errors.append("ERR: PDF 헤더(%PDF-)를 찾지 못함")
            return doc

        pdf = PDFFile(data)
        if pdf.encrypted:
            doc.errors.extend(pdf.warnings)
            return doc

        for page_number, (page, resources) in enumerate(pdf.pages(), start=1):
            section = Section(
                provenance=Provenance(source_format="pdf", page=page_number)
            )
            content = self._page_content(pdf, page)
            lines = []
            if content:
                decoders = self._font_decoders(pdf, resources)
                lines = ContentTextExtractor(decoders).extract(content)
            if not lines and self._page_has_images(pdf, resources):
                pdf.warnings.append(
                    f"WARN: {page_number}페이지: 텍스트 없음 — 스캔 이미지로 추정 (OCR 미지원)"
                )
            for line in lines:
                section.elements.append(
                    Paragraph(
                        runs=[TextRun(line)],
                        provenance=Provenance(source_format="pdf", page=page_number),
                    )
                )
            doc.sections.append(section)

        doc.errors.extend(pdf.warnings)
        return doc

    def _page_content(self, pdf: PDFFile, page: dict) -> bytes:
        contents = pdf.resolve(page.get("Contents"))
        streams = contents if isinstance(contents, list) else [contents]
        parts = []
        for item in streams:
            stream = pdf.resolve(item)
            if isinstance(stream, PDFStream):
                decoded = decode_stream(stream.dictionary, stream.raw, pdf.warnings)
                if decoded:
                    parts.append(decoded)
        return b"\n".join(parts)

    def _font_decoders(self, pdf: PDFFile, resources) -> Dict[str, Callable[[bytes], str]]:
        decoders: Dict[str, Callable[[bytes], str]] = {}
        if not isinstance(resources, dict):
            return decoders
        fonts = pdf.resolve(resources.get("Font"))
        if not isinstance(fonts, dict):
            return decoders
        for name, font_ref in fonts.items():
            font = pdf.resolve(font_ref)
            if not isinstance(font, dict):
                continue
            to_unicode = pdf.resolve(font.get("ToUnicode"))
            if isinstance(to_unicode, PDFStream):
                cmap_data = decode_stream(to_unicode.dictionary, to_unicode.raw, pdf.warnings)
                if cmap_data:
                    cmap = parse_tounicode(cmap_data)
                    if cmap.mapping:
                        decoders[str(name)] = cmap.decode
                        continue
            decoders[str(name)] = default_byte_decoder
        return decoders

    def _page_has_images(self, pdf: PDFFile, resources) -> bool:
        if not isinstance(resources, dict):
            return False
        xobjects = pdf.resolve(resources.get("XObject"))
        if not isinstance(xobjects, dict):
            return False
        for ref in xobjects.values():
            xobj = pdf.resolve(ref)
            if isinstance(xobj, PDFStream) \
                    and str(xobj.dictionary.get("Subtype", "")) == "Image":
                return True
        return False
```

- [x] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_pdf_reader.py -q`
Expected: `9 passed`

- [x] **Step 5: Run all tests**

Run: `PYTHONPATH=. pytest tests/ -q`
Expected: all pass (463 existing + new PDF tests)

- [x] **Step 6: Commit**

```bash
git add dochan/pdf/reader.py tests/test_pdf_reader.py
git commit -m "feat(pdf): PDFReader — 페이지 텍스트를 Document 모델로 조립"
```

## Task 7: Route PDF Through Dochan, Batch, CLI

**Files:**
- Modify: `dochan/reader.py`
- Modify: `dochan/batch.py`
- Modify: `dochan/cli.py`
- Test: `tests/test_pdf_reader.py` (append)

- [x] **Step 1: Write the failing integration tests**

Append to `tests/test_pdf_reader.py`:

```python
from dochan import Dochan
from dochan.batch import batch_convert


def test_dochan_routes_pdf_extension(tmp_path):
    content = b"BT (Routed) Tj ET"
    path = _write(tmp_path, "route.pdf", _build_pdf(_minimal_objects(content)))

    doc = Dochan(path)

    assert doc.metadata["source_format"] == "pdf"
    assert doc.to_markdown() == "Routed"


def test_dochan_routes_pdf_magic_without_extension(tmp_path):
    content = b"BT (MagicRouted) Tj ET"
    path = _write(tmp_path, "mystery.bin", _build_pdf(_minimal_objects(content)))

    doc = Dochan(path)

    assert doc.metadata["source_format"] == "pdf"
    assert doc.to_markdown() == "MagicRouted"


def test_batch_convert_includes_pdf_by_default(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    content = b"BT (Batch PDF) Tj ET"
    (input_dir / "doc.pdf").write_bytes(_build_pdf(_minimal_objects(content)))

    summary = batch_convert(str(input_dir), str(output_dir),
                            output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "doc.md").read_text(encoding="utf-8") == "Batch PDF"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. pytest tests/test_pdf_reader.py -q`
Expected: the three new tests fail (`.pdf` not routed → `알 수 없는 파일 형식` error, empty markdown, batch total 0).

- [x] **Step 3: Write minimal implementation**

Modify `dochan/reader.py` — add import:

```python
from .pdf.reader import PDFReader
```

In `_parse`, add extension branch before `else`:

```python
        elif ext == '.pdf':
            self._parse_pdf()
```

In the magic-byte `else` branch, add before the final `else`:

```python
            elif magic[:5] == b'%PDF-':
                self._parse_pdf()
```

Add method next to `_parse_xlsx`:

```python
    def _parse_pdf(self):
        """PDF (네이티브 파서) 파싱"""
        self.doc = PDFReader().read(self.file_path)
```

Modify `dochan/batch.py` default extensions:

```python
    extensions: tuple = ('.hwp', '.hwpx', '.doc', '.ppt', '.xls', '.docx', '.pptx', '.xlsx', '.pdf'),
```

Modify `dochan/cli.py` docstring usage block — add after the `--format text` line:

```python
  dochan convert 문서.pdf --format text      # → PDF 텍스트 추출
```

- [x] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. pytest tests/test_pdf_reader.py -q`
Expected: `12 passed`

- [x] **Step 5: Run all tests**

Run: `PYTHONPATH=. pytest tests/ -q`
Expected: all pass.

- [x] **Step 6: Commit**

```bash
git add dochan/reader.py dochan/batch.py dochan/cli.py tests/test_pdf_reader.py
git commit -m "feat(pdf): Dochan/배치/CLI 에 PDF 라우팅 연결"
```

## Task 8: Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-20-native-universal-document-conversion-design.md`
- Modify: `CHANGELOG.md`

- [x] **Step 1: Update README**

Update the feature/format tables to include PDF (text extraction, page provenance) with honest scope: 단순 디지털 PDF 텍스트 추출; 암호화·스캔·레이아웃 재구성은 미지원(경고 처리). Add CLI example `dochan convert 문서.pdf`.

- [x] **Step 2: Update design spec Phase 6 status**

Add a "Phase 1 implementation status" block to Phase 6 mirroring the other phases: completed (classic xref, Flate/ASCIIHex/ASCII85, text operators, ToUnicode/한글, page provenance, Dochan/배치/CLI routing, encrypted/scanned/xref-stream warnings) and not yet completed (xref streams, object streams, encryption, layout/tables, images, OCR, Predictor).

Also update the stale "Phase 1 implementation status" blocks for Phases 2–5 to reflect current reality (DOCX footnotes/numbering/images/merged cells are done; PPTX notes/images/groups done; XLSX formulas/dates/merged cells done — verify each against code before writing).

- [x] **Step 3: Update CHANGELOG**

Add an Unreleased section entry describing native PDF Phase 1 support.

- [x] **Step 4: Run all tests**

Run: `PYTHONPATH=. pytest tests/ -q`
Expected: all pass.

- [x] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-06-20-native-universal-document-conversion-design.md CHANGELOG.md
git commit -m "docs: 네이티브 PDF Phase 1 지원 문서화 및 스펙 상태 갱신"
```

## Self-Review Checklist

- Spec coverage: Phase 6 milestone 1 targets are all covered — header/xref parsing (Task 3), indirect objects and page tree (Task 3), stream filters (Task 2), text operators (Task 5), page-level provenance (Task 6), warnings for encryption/xref streams/scanned pages (Tasks 3, 6). Layout/tables/images/OCR deferred per spec.
- Native-only constraint: stdlib only; no new dependencies.
- Korean-first: ToUnicode CMap decoding (Task 4) covers the dominant Korean PDF pattern (Identity-H CID + ToUnicode).
- API compatibility: `Dochan` public methods unchanged; PDF is additive routing.
- Security: bounded collection sizes, decompression cap, resolve-depth cap, page-tree cycle guard, object-count cap, file-size cap.
- Type consistency: `PDFRef`/`PDFName`/`PDFStream` defined in Task 1 and used consistently; `decode_stream(dict, bytes, warnings)` signature consistent across Tasks 2, 6; `PDFFile.resolve`/`get_object`/`pages` consistent across Tasks 3, 6.
