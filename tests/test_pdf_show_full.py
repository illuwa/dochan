"""Native text operators must consume glyphs without the Python show callback."""
import struct

import pytest

from dochan.pdf import content
from dochan.pdf.cmap import ToUnicodeCMap
from dochan.pdf._show_table import font_table
from dochan.pdf.core14 import Core14Decoder
from dochan.pdf.widths import WidthMap

native = pytest.importorskip('dochan.pdf._cinterp')


def font_for(step=1):
    cmap = ToUnicodeCMap()
    cmap.code_lengths = {step}
    cmap.mapping = {(step, code): chr(code) for code in range(256)}
    cmap.mapping[step, 65] = 'fi'
    return content.FontInfo(cmap.decode, WidthMap({i: 500.0 for i in range(256)}, 600.0), step)


def signature(value):
    if isinstance(value, float):
        return type(value), struct.pack('!d', value)
    if isinstance(value, dict):
        return type(value), {k: signature(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return type(value), tuple(signature(v) for v in value)
    return type(value), value


@pytest.mark.parametrize('step', [1, 2])
@pytest.mark.parametrize('track', [False, True])
def test_native_show_consumes_all_four_operators(monkeypatch, step, track):
    monkeypatch.setattr(content, '_CInterpreter', native.Interpreter)
    monkeypatch.setattr(content, '_CInterpreterBailout', native.Bailout)
    raw = '004100200042' if step == 2 else '412042'
    data = (f'BT /F 12 Tf 14 TL 2 Tr 0.5 w <{raw}> Tj '
            f'[<{raw}> 12 <{raw}>] TJ <{raw}> \' 2 1 <{raw}> " ET').encode()
    fonts = {'F': font_for(step)}
    expected = content.ContentTextExtractor.from_fonts(fonts, track_char_positions=track)
    before = expected._extract_page_python(data)
    actual = content.ContentTextExtractor.from_fonts(fonts, track_char_positions=track)
    actual._form_context = {'char_positions': 200000}
    actual._marked_stack = []
    actual._marked_overflow = 0
    actual._link_position_reliable = True
    frags = []
    engine = native.Interpreter(data, fonts, (1, 0, 0, 1, 0, 0),
                                (None, 0.0, 0.0, 0.0, 1.0, 0.0, 0, 1.0),
                                [], [], [], actual, frags, content.Fragment, font_table)
    assert engine.next() is None, 'supported glyph operator returned to Python'
    assert signature([vars(f) for f in frags]) == signature([vars(f) for f in before.fragments])
    assert frags


def test_unknown_decoder_remains_python(monkeypatch):
    monkeypatch.setattr(content, '_CInterpreter', native.Interpreter)
    calls = []
    def decode(raw):
        calls.append(raw)
        return 'custom'
    font = content.FontInfo(decode, WidthMap({}, 500))
    page = content.ContentTextExtractor.from_fonts({'F': font}).extract_page(b'/F 12 Tf (abc) Tj')
    assert page.fragments[0].text == 'custom'
    assert calls == [b'abc']


def test_core14_contract():
    decoder = Core14Decoder({65: 'A'}, content.default_byte_decoder)
    assert decoder.decode(b'\x80\x81A') == ''.join(decoder.decode(bytes([c])) for c in b'\x80\x81A')
    # The default decoder itself is NOT compositional: one undefined cp1252
    # byte changes the interpretation of all bytes in the same string.
    assert content.default_byte_decoder(b'\x80\x81') != ''.join(
        content.default_byte_decoder(bytes([c])) for c in b'\x80\x81')


def test_fixed_encoding_cmap_consumed_in_native_loop():
    from dochan.pdf.cmap import EncodingCMap
    from dochan.pdf.objects import PDFStream
    from dochan.pdf.reader import PDFReader
    class PDF:
        warnings = []
        def resolve(self, value):
            return value
        def decode_stream_bytes(self, stream):
            return stream.raw
    cmap = EncodingCMap(((1, 0, 255),), ((1, 0, 255, 100),))
    stream = PDFStream({}, b'1 beginbfchar <41> <0041> endbfchar')
    decode = PDFReader()._build_font_decoder(PDF(), 'F', {'ToUnicode': stream}, cmap)
    font = content.FontInfo(decode, WidthMap({165: 750.0}, 500.0),
                            encoding_cmap=cmap, link_metrics_reliable=False)
    owner = content.ContentTextExtractor.from_fonts({'F': font}, track_char_positions=True)
    expected = owner._extract_page_python(b'/F 12 Tf (A) Tj')
    frags = []
    engine = native.Interpreter(b'/F 12 Tf (A) Tj', {'F': font}, (1, 0, 0, 1, 0, 0),
                                (None, 0.0, 0.0, 0.0, 1.0, 0.0, 0, 1.0),
                                [], [], [], owner, frags, content.Fragment, font_table)
    assert engine.next() is None
    assert signature([vars(f) for f in frags]) == signature([vars(f) for f in expected.fragments])


@pytest.mark.parametrize('kind', ['vertical', 'unreliable', 'custom-width', 'mixed-code', 'default'])
def test_unsupported_fonts_preserve_python_results(monkeypatch, kind):
    monkeypatch.setattr(content, '_CInterpreter', native.Interpreter)
    monkeypatch.setattr(content, '_CInterpreterBailout', native.Bailout)
    font = font_for()
    if kind == 'vertical':
        font.wmode = 1
    elif kind == 'unreliable':
        font.link_metrics_reliable = False
    elif kind == 'custom-width':
        class Widths(WidthMap):
            def advance(self, code):
                return 123.0 + code
        font.widths = Widths({}, 500)
    elif kind == 'mixed-code':
        font.decode.__self__.code_lengths.add(2)
        font.decode.__self__.mapping[2, 0x4142] = 'Z'
    else:
        font.decode = content.default_byte_decoder
    data = b'/F 12 Tf [<80814142> 5 (A)] TJ (B) Tj'
    owner = content.ContentTextExtractor.from_fonts({'F': font}, track_char_positions=True)
    expected = owner._extract_page_python(data)
    actual = owner.extract_page(data)
    assert signature([vars(f) for f in actual.fragments]) == signature([vars(f) for f in expected.fragments])


@pytest.mark.parametrize('raw', [b'\x00', b'\x00A\x00', b'\x00A', b''])
def test_truncated_cid_operation_matches_python(monkeypatch, raw):
    monkeypatch.setattr(content, '_CInterpreter', native.Interpreter)
    font = font_for(2)
    data = b'/F 12 Tf [(\x00B) 23 <' + raw.hex().encode() + b'>] TJ'
    owner = content.ContentTextExtractor.from_fonts({'F': font}, track_char_positions=True)
    expected = owner._extract_page_python(data)
    actual = owner.extract_page(data)
    assert signature([vars(f) for f in actual.fragments]) == signature([vars(f) for f in expected.fragments])
