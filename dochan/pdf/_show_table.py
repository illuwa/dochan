"""Conservative, compositional font snapshots for the native text loop.

Only exact repository decoder implementations are accepted. Core14 iterates
bytes independently; a fixed-length ToUnicode map consumes exactly one code at
a time. Mixed lengths, encoding CMaps requiring warning side effects, custom
callables/metrics and unreliable/Type3 fonts retain the Python operation.
"""
from types import CodeType, FunctionType, MethodType

from .cmap import EncodingCMap, ToUnicodeCMap
from .core14 import Core14Decoder
from .widths import WidthMap


def font_table(font):
    from .content import FontInfo, default_byte_decoder

    if (type(font) is not FontInfo or font.wmode != 0
            or (font.encoding_cmap is None and not font.link_metrics_reliable)
            or type(font.link_metrics_reliable) is not bool
            or type(font.widths) is not WidthMap or font.code_bytes not in (1, 2)):
        return _safe_fallback(font)
    widths = font.widths
    if (set(vars(widths)) - {'_widths', '_default', '_cid_default', 'reliable', 'warnings'}
            or type(widths._widths) is not dict
            or type(widths.reliable) is not bool or type(widths._cid_default) is not bool
            or type(font.bold) is not bool or type(font.italic) is not bool
            or type(font.space_code) is not int):
        return _safe_fallback(font)
    if any(type(k) is not int or type(v) not in (int, float)
           for k, v in widths._widths.items()) or type(widths._default) not in (int, float):
        return _safe_fallback(font)
    if font.encoding_cmap is not None:
        return _encoding_table(font)
    decode = font.decode
    if type(decode) is not MethodType:
        return _safe_fallback(font)
    owner = decode.__self__
    step = font.code_bytes
    if (type(owner) is ToUnicodeCMap and decode.__func__ is ToUnicodeCMap.decode
            and owner.code_lengths == {step} and type(owner.mapping) is dict):
        if any(type(k) is not tuple or len(k) != 2 or k[0] != step
               or type(k[1]) is not int or type(v) is not str
               for k, v in owner.mapping.items()):
            return _safe_fallback(font)
        mapping = {code: value for (_size, code), value in owner.mapping.items()}
        missing = '\ufffd'
    elif (step == 1 and type(owner) is Core14Decoder
          and decode.__func__ is Core14Decoder.decode
          and type(owner._preserve_undefined) is bool
          and (owner._fallback is default_byte_decoder or owner._preserve_undefined)
          and type(owner.mapping) is dict
          and all(type(k) is int and type(v) is str for k, v in owner.mapping.items())):
        mapping = {code: decode(bytes([code])) for code in range(256)}
        missing = '\ufffd'
    else:
        return _safe_fallback(font)
    if step == 1:
        mapping = tuple(mapping.get(code, missing) for code in range(256))
    return (step, mapping, missing, widths._widths.copy(), widths._default,
            widths.reliable, widths._cid_default, font.space_code, font.bold, font.italic,
            font.link_metrics_reliable, None)


def _safe_fallback(font):
    """False is a pure fallback; None requires invalidating prior snapshots."""
    from .content import FontInfo, default_byte_decoder
    if (type(font) is not FontInfo or type(font.widths) is not WidthMap
            or type(font.wmode) is not int or font.wmode != 0
            or type(font.code_bytes) is not int or type(font.space_code) is not int
            or any(type(value) is not bool for value in (font.bold, font.italic, font.link_metrics_reliable))
            or font.encoding_cmap is not None
            or set(vars(font.widths)) - {'_widths', '_default', '_cid_default', 'reliable', 'warnings'}):
        return None
    widths = font.widths
    if (type(widths._widths) is not dict or type(widths._default) not in (int, float)
            or type(widths.reliable) is not bool or type(widths._cid_default) is not bool
            or any(type(k) is not int or type(v) not in (int, float)
                   for k, v in widths._widths.items())):
        return None
    decode = font.decode
    if decode is default_byte_decoder:
        return False
    if (type(decode) is MethodType and type(decode.__self__) is ToUnicodeCMap
            and decode.__func__ is ToUnicodeCMap.decode
            and type(decode.__self__.code_lengths) is set
            and all(type(v) is int for v in decode.__self__.code_lengths)
            and type(decode.__self__.mapping) is dict
            and all(type(k) is tuple and len(k) == 2
                    and all(type(v) is int for v in k) and type(value) is str
                    for k, value in decode.__self__.mapping.items())):
        return False
    return None


def _encoding_table(font):
    # The reader's exact closure composes cmap.decode over encoding chunks.
    # Inspect its code identity, never a user-supplied name or mapping attribute.
    from .reader import PDFReader
    expected = next(value for value in PDFReader._build_font_decoder.__code__.co_consts
                    if type(value) is CodeType and value.co_name == 'decode_encoded')
    decode = font.decode
    encoding = font.encoding_cmap
    if (type(decode) is not FunctionType or decode.__code__ is not expected
            or type(encoding) is not EncodingCMap):
        return None
    closure = dict(zip(decode.__code__.co_freevars,
                       (cell.cell_contents for cell in decode.__closure__)))
    cmap = closure['cmap']
    if (closure['encoding_cmap'] is not encoding or type(cmap) is not ToUnicodeCMap
            or type(cmap.mapping) is not dict
            or any(type(k) is not tuple or len(k) != 2
                   or any(type(v) is not int for v in k) or type(value) is not str
                   for k, value in cmap.mapping.items())
            or type(cmap.code_lengths) is not set
            or any(type(v) is not int for v in cmap.code_lengths)):
        return None
    lengths = {size for size, _lo, _hi in encoding._boxes}
    if len(lengths) != 1 or next(iter(lengths)) not in (1, 2):
        return None  # Variable-length/malformed spaces retain warning semantics.
    step = next(iter(lengths))
    mapping, widths, explicit = {}, {}, set()
    for code in range(256 ** step):
        if not encoding._space(step, code):
            continue
        cid = encoding._lookup(step, code)
        if cid is None:
            cid = encoding._lookup(step, code, True)
        if cid is None:
            continue  # Missing CID must yield, so Python emits its warning.
        mapping[code] = cmap.decode(code.to_bytes(step, 'big'))
        widths[code] = font.widths.advance(cid)
        if font.widths.explicit(cid):
            explicit.add(code)
    if step == 1:
        mapping = tuple(mapping.get(code) for code in range(256))
    widths[-1] = font.widths.advance(font.space_code)
    return (step, mapping, '', widths, font.widths._default, font.widths.reliable,
            False, -1, font.bold, font.italic, font.link_metrics_reliable, frozenset(explicit))
