"""최적화한 PDF 렉서와 경로 판정의 기존 출력 계약을 고정한다."""
import math
import random
import signal

from dochan.pdf.objects import DELIMITERS, WHITESPACE, PDFLexer
from dochan.pdf.paths import Segment, _axis_segment
from dochan.pdf.content import ContentTextExtractor, ContentScanner, _OPERAND_START, _num
from dochan.pdf.objects import PDFSyntaxError
from dochan.pdf.paths import PathCollector


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


def _old_content_events(data):
    lexer = PDFLexer(data)
    lexer.skip_array_operators = True
    events = []
    while True:
        lexer.skip_whitespace()
        if lexer.pos >= len(data):
            return events
        if data[lexer.pos] in _OPERAND_START:
            try:
                value = lexer.parse_object()
            except PDFSyntaxError:
                lexer.pos += 1
            else:
                events.append(("operand", value, lexer.pos))
            continue
        op = lexer.read_token()
        if not op:
            lexer.pos += 1
            continue
        events.append(("operator", op, lexer.pos))
        if op == b"BI":
            lexer.pos = ContentTextExtractor._skip_inline_image(data, lexer.pos)


def test_content_scanner_differential_random_and_boundaries():
    rng = random.Random(20261004)
    samples = [
        b"/F1 12 Tf (hello) Tj [(a) 0 Tc (b)] TJ",
        b"/Artifact << /MCID 1 >> BDC BI /W 1 /H 1 ID abc EI EMC",
        b"1 2 R 3 4 m 10 20 l S", b"% comment\r\n-2.4 +.5 .0 1e2 cm",
        b"1% comment\r\n2% another\nR 3 4 m 10 20 l S",
        b"1 2 Rfoo 1 2/R 1% comment\r2 R", b"+1 0 R -1 2 R 1.2 3 R",
        b"[(a\\(b\\)c) <AB C> 1] TJ", b"<> << /A#20B 1 >> BDC",
        bytes(range(256)), b"[ (unclosed", b"/ ( ) < > [ ] %\r\n",
    ]
    alphabet = b"abcXYZ0123456789 /[]()<>%\r\n\t\x00#\\-+.\"'"
    samples.extend(bytes(rng.choice(alphabet) for _ in range(rng.randrange(0, 129)))
                   for _ in range(3000))
    for data in samples:
        scanner = ContentScanner(data)
        actual = []
        while True:
            event = scanner.next()
            if event is None:
                break
            kind, value = event
            actual.append((kind, value, scanner.pos))
            if value == b"BI" and kind == "operator":
                scanner.pos = ContentTextExtractor._skip_inline_image(data, scanner.pos)
        assert actual == _old_content_events(data)


def test_content_path_ops_differential_random_sequences():
    rng = random.Random(20261005)
    ops = [b"m", b"l", b"re", b"h", b"c", b"v", b"y", b"S", b"s",
           b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*", b"n", b"W"]
    for _ in range(100):
        pieces = []
        for _ in range(100):
            values = [rng.randrange(-100, 101) for _ in range(rng.randrange(0, 7))]
            pieces.extend(str(value).encode() for value in values)
            pieces.append(rng.choice(ops))
        data = b" ".join(pieces)
        old = PathCollector()
        operands = []
        for kind, value, _pos in _old_content_events(data):
            if kind == "operand":
                operands.append(value)
            else:
                old.operate(value, [_num(item) for item in operands], (1, 0, 0, 1, 0, 0))
                operands = []
        actual = ContentTextExtractor().extract_page(data)
        assert actual.segments == old.segments
        assert actual.short_segments == old.short_segments
        assert actual.warnings == old.warnings


def test_content_scanner_large_whitespace_after_integer_is_bounded():
    if not hasattr(signal, "SIGALRM"):
        return

    def timed_out(_signum, _frame):
        raise TimeoutError("content scanner backtracked on whitespace")

    previous = signal.signal(signal.SIGALRM, timed_out)
    try:
        signal.alarm(2)
        scanner = ContentScanner(b"1" + b" " * 4096 + b"m")
        assert scanner.next() == ("operand", 1)
        assert scanner.next() == ("operator", b"m")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
