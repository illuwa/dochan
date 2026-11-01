"""Coverage and finite filtering contracts for the native text loop."""
import math
import struct

import pytest

from dochan.pdf import content
from dochan.pdf._show_table import font_table
from dochan.pdf.widths import WidthMap

native = pytest.importorskip('dochan.pdf._cinterp')


def signature(value):
    if isinstance(value, float):
        return type(value), struct.pack('!d', value)
    if isinstance(value, dict):
        return type(value), {key: signature(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value), tuple(signature(item) for item in value)
    return type(value), value


@pytest.mark.parametrize('raw', [b'ABC', b'\x80ABC', bytes(range(128))])
def test_default_decoder_native_supported(raw):
    font = content.FontInfo(content.default_byte_decoder, WidthMap({}, 500.0))
    owner = content.ContentTextExtractor.from_fonts({'F': font}, track_char_positions=True)
    data = b'/F 12 Tf <' + raw.hex().encode() + b'> Tj'
    expected = owner._extract_page_python(data)
    frags = []
    engine = native.Interpreter(data, {'F': font}, (1, 0, 0, 1, 0, 0),
                                (None, 0.0, 0.0, 0.0, 1.0, 0.0, 0, 1.0),
                                [], [], [], owner, frags, content.Fragment, font_table)
    assert engine.next() is None
    assert signature([vars(f) for f in frags]) == signature([vars(f) for f in expected.fragments])


@pytest.mark.parametrize('field', ['x', 'y', 'width', 'size', 'dir_x', 'dir_y', 'up_x', 'up_y'])
@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf])
def test_finite_filter_all_fields(field, value):
    good = content.Fragment(1, 2, 3, 4, 'ok', 5)
    bad = content.Fragment(1, 2, 3, 4, 'bad', 5)
    setattr(bad, field, value)
    assert native._finite_fragments([good, bad, good]) == [good, good]


def test_finite_filter_excludes_space_width_and_preserves_identity():
    fragment = content.Fragment(-0.0, 2, 3, 4, 'ok', math.inf)
    result = native._finite_fragments([fragment])
    assert result[0] is fragment


@pytest.mark.parametrize('undefined', [0x81, 0x8d, 0x8f, 0x90, 0x9d])
def test_default_undefined_byte_yields_entire_tj(undefined):
    font = content.FontInfo(content.default_byte_decoder, WidthMap({}, 500.0))
    owner = content.ContentTextExtractor.from_fonts({'F': font}, track_char_positions=True)
    owner._extract_page_python(b'')
    frags = []
    data = b'/F 12 Tf [(A) 10 <80' + f'{undefined:02x}'.encode() + b'>] TJ'
    engine = native.Interpreter(data, {'F': font}, (1, 0, 0, 1, 0, 0),
                                (None, 0.0, 0.0, 0.0, 1.0, 0.0, 0, 1.0),
                                [], [], [], owner, frags, content.Fragment, font_table)
    assert engine.next()[0] == b'TJ'
    assert frags == []
    assert engine.tm == (1, 0, 0, 1, 0, 0)


@pytest.mark.parametrize('field', ['x', 'y', 'width', 'size', 'dir_x', 'dir_y', 'up_x', 'up_y'])
def test_python_callback_fragments_keep_warning_and_order(monkeypatch, field):
    original = content.ContentTextExtractor._show

    def show(self, raw, *args):
        tm = original(self, raw, *args)
        if raw == b'bad':
            setattr(args[-2][-1], field, math.inf)
        return tm

    monkeypatch.setattr(content.ContentTextExtractor, '_show', show)
    monkeypatch.setattr(content, '_CInterpreter', native.Interpreter)
    monkeypatch.setattr(content, '_c_finite_fragments', native._finite_fragments)
    owner = content.ContentTextExtractor.from_fonts({})
    data = b'/F 12 Tf (bad) Tj (good) Tj (bad) Tj'
    expected = owner._extract_page_python(data)
    actual = owner.extract_page(data)
    assert signature([vars(f) for f in actual.fragments]) == signature([vars(f) for f in expected.fragments])
    assert actual.warnings == expected.warnings == ['WARN: PDF 비유한 텍스트 좌표 — 해당 조각 건너뜀']
    assert actual.fragments[0].order == 1
