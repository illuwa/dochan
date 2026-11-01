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


def test_font_snapshot_once_across_yields_and_pages(monkeypatch):
    from dochan.pdf import _show_table
    monkeypatch.setattr(content, '_CInterpreter', native.Interpreter)
    calls = []
    original = _show_table.font_table
    def counted(font):
        calls.append(font)
        return original(font)
    monkeypatch.setattr(_show_table, 'font_table', counted)
    font = font_for(2)
    fonts = {'F': font, 'P': content.FontInfo(content.default_byte_decoder, WidthMap({}, 500))}
    data = b'/F 10 Tf ' + b'/GS gs <0041> Tj /P 10 Tf (p) Tj /F 10 Tf ' * 50
    for _ in range(3):
        owner = content.ContentTextExtractor.from_fonts(fonts)
        owner.resources = {'ExtGState': {'GS': {'LW': 1}}}
        assert len(owner.extract_page(data).fragments) == 100
    assert calls.count(font) == 1
    assert len(calls) == 2


def test_tj_boolean_does_not_bail():
    font = font_for()
    data = b'/F 10 Tf [(A) true (B) false (C)] TJ'
    owner = content.ContentTextExtractor.from_fonts({'F': font})
    expected = owner._extract_page_python(data)
    frags = []
    engine = native.Interpreter(data, {'F': font}, (1, 0, 0, 1, 0, 0),
                                (None, 0., 0., 0., 1., 0., 0, 1.),
                                [], [], [], owner, frags, content.Fragment, font_table)
    assert engine.next() is None
    assert signature([vars(f) for f in frags]) == signature([vars(f) for f in expected.fragments])


def test_native_cache_owns_font_until_interpreter_release():
    import gc
    import weakref
    font = font_for()
    ref = weakref.ref(font)
    fonts = {'F': font}
    owner = content.ContentTextExtractor.from_fonts(fonts)
    owner._extract_page_python(b'')
    engine = native.Interpreter(b'/F 10 Tf (A) Tj /GS gs', fonts, (1, 0, 0, 1, 0, 0),
                                (None, 0., 0., 0., 1., 0., 0, 1.),
                                [], [], [], owner, [], content.Fragment, font_table)
    assert engine.next()[0] == b'gs'
    engine.font = None
    fonts.clear()
    del font
    gc.collect()
    assert ref() is not None
    del engine, owner
    gc.collect()
    assert ref() is None


def test_encoding_snapshot_preserves_parent_notdef_and_byte_boxes():
    from dochan.pdf.cmap import EncodingCMap
    from dochan.pdf.objects import PDFStream
    from dochan.pdf.reader import PDFReader
    class PDF:
        warnings = []
        def resolve(self, value):
            return value
        def decode_stream_bytes(self, stream):
            return stream.raw
    parent = EncodingCMap(((2, 0x1010, 0x1112),), ((2, 0x1010, 0x1112, 1),))
    encoding = EncodingCMap((), ((2, 0x1011, 0x1011, 800),),
                            ((2, 0x1010, 0x1112, 900),), parent=parent)
    stream = PDFStream({}, b'1 beginbfchar <1010> <0041> endbfchar')
    decode = PDFReader()._build_font_decoder(PDF(), 'F', {'ToUnicode': stream}, encoding)
    widths = WidthMap({1: 500, 800: 750, 900: 1000}, 600)
    font = content.FontInfo(decode, widths, 2, encoding_cmap=encoding)
    for code in range(0x1000, 0x1120):
        data = b'/F 10 Tf <' + code.to_bytes(2, 'big').hex().encode() + b'> Tj'
        owner = content.ContentTextExtractor.from_fonts({'F': font})
        expected = owner._extract_page_python(data)
        actual = owner.extract_page(data)
        assert signature([vars(f) for f in actual.fragments]) == signature([vars(f) for f in expected.fragments])



def test_uniks_gs_and_forms_build_one_snapshot(monkeypatch):
    from dochan.pdf import _show_table
    from dochan.pdf.cmap import predefined_cmap
    from dochan.pdf.objects import PDFStream
    from dochan.pdf.reader import PDFReader
    class PDF:
        warnings = []
        def resolve(self, value):
            return value
        def decode_stream_bytes(self, stream):
            return stream.raw
    encoding = predefined_cmap('UniKS-UCS2-H')
    stream = PDFStream({}, b'2 beginbfchar <AC00> <AC00> <AC01> <AC01> endbfchar')
    decode = PDFReader()._build_font_decoder(PDF(), 'F', {'ToUnicode': stream}, encoding)
    font = content.FontInfo(decode, WidthMap({}, 1000, cid_default=True), 2, encoding_cmap=encoding)
    calls = []
    original = _show_table.font_table
    def counted(value):
        calls.append(value)
        return original(value)
    monkeypatch.setattr(_show_table, 'font_table', counted)
    monkeypatch.setattr(content, '_CInterpreter', native.Interpreter)
    fonts = {'F': font}
    form = b'/F 10 Tf <AC00AC01> Tj'
    resources = {'ExtGState': {'GS': {'LW': 1}}}
    def loader(name, resources):
        return ('form', form, (1, 0, 0, 1, 0, 0), resources, fonts, {}, 2, None, False)
    data = b'BT /F 10 Tf ' + b'/GS gs <AC00AC01> Tj /X Do ' * 50 + b'ET'
    for _ in range(2):
        owner = content.ContentTextExtractor.from_fonts(fonts)
        owner.resources = resources
        owner.form_loader = loader
        assert len(owner.extract_page(data).fragments) == 100
    assert calls == [font]


def test_fixed_encoding_snapshot_does_not_expand_codespace():
    from dochan.pdf.cmap import EncodingCMap
    from dochan.pdf.objects import PDFStream
    from dochan.pdf.reader import PDFReader
    class PDF:
        warnings = []
        def resolve(self, value):
            return value
        def decode_stream_bytes(self, stream):
            return stream.raw
    encoding = EncodingCMap(((2, 0, 65535),), ((2, 0, 65535, 0),))
    stream = PDFStream({}, b'1 beginbfchar <0041> <0041> endbfchar')
    decode = PDFReader()._build_font_decoder(PDF(), 'F', {'ToUnicode': stream}, encoding)
    table = font_table(content.FontInfo(decode, WidthMap({65: 500}, 600), 2, encoding_cmap=encoding))
    assert len(table[1]) == 1
    assert len(table[3]) == 1


@pytest.mark.parametrize('preserve', [False, True])
def test_core14_snapshot_uses_mapping_without_per_byte_decoder(monkeypatch, preserve):
    original = Core14Decoder.decode
    calls = []
    def counted(self, raw):
        calls.append(raw)
        return original(self, raw)
    monkeypatch.setattr(Core14Decoder, 'decode', counted)
    decoder = Core14Decoder({65: 'A'}, content.default_byte_decoder, preserve_undefined=preserve)
    font = content.FontInfo(decoder.decode, WidthMap({65: 500}, 600))
    table = font_table(font)
    assert ''.join(table[1]) == original(decoder, bytes(range(256)))
    assert calls == []


@pytest.mark.parametrize('mapping,kind,step', [
    ({True: 500}, 0, 0), ({1: True}, 0, 0), ({1: '500'}, 0, 0),
    ({'1': 500}, 0, 0), ([], 0, 0), ({1: 1}, 1, 1),
    ({(2, True): 'A'}, 2, 2), ({(True, 1): 'A'}, 2, 1),
    ({(1, 2): 'A'}, 2, 2), ({(2, 1, 0): 'A'}, 2, 2),
    ({(2, 1): 5}, 3, 0), ({(10 ** 100, 1): 'A'}, 2, 2),
])
def test_native_snapshot_rejects_non_exact_mapping(mapping, kind, step):
    assert native._snapshot_map(mapping, kind, step) is False


def test_native_snapshot_preserves_width_types_and_normalizes_unicode():
    widths = {1: 500, 2: -0.0, 3: 1 << 100}
    assert signature(native._snapshot_map(widths, 0, 0)) == signature(widths)
    mapping = {(2, 1): 'ffi', (2, 2): '', (2, 3): '\ufffd'}
    assert native._snapshot_map(mapping, 2, 2) == {1: 'ffi', 2: '', 3: '\ufffd'}
    assert native._snapshot_map(mapping, 3, 0) is mapping
