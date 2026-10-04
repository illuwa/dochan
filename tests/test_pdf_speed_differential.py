"""최적화한 PDF 렉서와 경로 판정의 기존 출력 계약을 고정한다."""
import math
import random

from dochan.pdf.objects import DELIMITERS, WHITESPACE, PDFLexer
from dochan.pdf.paths import Segment, _axis_segment


def _old_skip(data, pos):
    while pos < len(data):
        ch = data[pos]
        if ch in WHITESPACE:
            pos += 1
        elif ch == 0x25:
            while pos < len(data) and data[pos] not in b"\r\n":
                pos += 1
        else:
            return pos
    return pos


def _old_token(data, pos):
    start = pos
    while pos < len(data):
        ch = data[pos]
        if ch in WHITESPACE or ch in DELIMITERS:
            break
        pos += 1
    return data[start:pos], pos


def test_lexer_differential_random_bytes_and_boundaries():
    rng = random.Random(20261004)
    samples = [
        b"", b"%", b"% ignored\r\n/Name#20[<AB C>](a\\(b\\)c) BI ID xyz EI",
        bytes(range(256)), b"a\x00b\tc\nd\x0ce\rf g%comment\nend",
        b"/a#28(b\\\r\nc)[]<0> << /x 1 >>",
    ]
    samples.extend(rng.randbytes(rng.randrange(0, 129)) for _ in range(5000))
    for data in samples:
        starts = (0, len(data) // 2, len(data), len(data) + 1)
        if data:
            starts += (-1,)
        for start in starts:
            lexer = PDFLexer(data, start)
            assert lexer.skip_whitespace() is None
            expected_pos = _old_skip(data, start)
            assert lexer.pos == expected_pos
            expected_token, expected_end = _old_token(data, expected_pos)
            assert lexer.read_token() == expected_token
            assert lexer.pos == expected_end


def test_lexer_differential_complete_streams():
    rng = random.Random(117)
    alphabet = b"abcXYZ0123456789 /[]()<>%\r\n\t\x00#\\"
    for _ in range(3000):
        data = bytes(rng.choice(alphabet) for _ in range(rng.randrange(0, 256)))
        lexer = PDFLexer(data)
        old_pos = 0
        while old_pos < len(data):
            lexer.skip_whitespace()
            old_pos = _old_skip(data, old_pos)
            assert lexer.pos == old_pos
            if old_pos == len(data):
                break
            actual = lexer.read_token()
            expected, old_end = _old_token(data, old_pos)
            assert actual == expected
            assert lexer.pos == old_end
            if old_end == old_pos:
                lexer.pos += 1
                old_pos += 1
            else:
                old_pos = old_end


def _old_axis(p0, p1):
    x0, y0 = p0
    x1, y1 = p1
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)):
        return None
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    length = math.hypot(dx, dy)
    if length > 0 and (min(dx, dy) == 0 or (length >= 1 and min(dx, dy) <= 0.6)):
        return Segment(x0, y0, x1, y1)
    return None


def test_axis_segment_differential_random_and_thresholds():
    rng = random.Random(20261004)
    values = [0, 0.6, -0.6, 1, -1, 1e-9, 1e100, float("inf"), float("nan")]
    points = [((x, 0), (1, y)) for x in values for y in values]
    points.extend(((rng.uniform(-1e3, 1e3), rng.uniform(-1e3, 1e3)),
                   (rng.uniform(-1e3, 1e3), rng.uniform(-1e3, 1e3)))
                  for _ in range(5000))
    for p0, p1 in points:
        assert _axis_segment(p0, p1) == _old_axis(p0, p1)
