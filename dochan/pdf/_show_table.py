"""Conservative, compositional font snapshots for the native text loop.

Only exact repository decoder implementations are accepted. Core14 iterates
bytes independently; a fixed-length ToUnicode map consumes exactly one code at
a time. Mixed lengths use an operand preflight to prove compositional decoding.
Encoding CMaps requiring warning side effects and custom callables/metrics
retain the Python operation. Unreliable geometry keeps its original flag.

The snapshot is attached to the FontInfo for its lifetime and is derived from
the font alone. Mutating a FontInfo (bold, space_code, wmode, the width map)
after its first text operator leaves the native loop on the stale snapshot;
build a new FontInfo instead.
"""
from types import CodeType, FunctionType, MethodType
from functools import lru_cache

from .cmap import EncodingCMap, ToUnicodeCMap
from .core14 import Core14Decoder
from .widths import WidthMap


def _snapshot_map(mapping, kind, step):
    """Pure fallback for installations without the optional native module."""
    if type(mapping) is not dict:
        return False
    for key, value in mapping.items():
        if kind >= 2:
            if type(key) is not tuple or len(key) != 2 or type(key[0]) is not int:
                return False
            if kind == 2 and key[0] != step:
                return False
            key = key[1]
        if type(key) is not int or (type(value) not in (int, float) if kind == 0 else type(value) is not str):
            return False
    return {code: value for (_size, code), value in mapping.items()} if kind == 2 else mapping


try:
    from ._cinterp import _snapshot_map
except ImportError:
    pass


@lru_cache(maxsize=1)
def _byte_defaults():
    from .content import default_byte_decoder
    return {code: default_byte_decoder(bytes([code])) for code in range(256)}


def cached_font_table(font):
    """Keep the immutable reader-built snapshot for the FontInfo lifetime."""
    from .content import FontInfo
    if type(font) is not FontInfo:
        return font_table(font)
    try:
        return font._native_show_table
    except AttributeError:
        font._native_show_table = font_table(font)
        return font._native_show_table


def font_table(font):
    from .content import FontInfo, default_byte_decoder

    if (type(font) is not FontInfo or font.wmode != 0
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
    if font.encoding_cmap is not None:
        return _encoding_table(font)
    decode = font.decode
    step = font.code_bytes
    mixed = None
    byte_default = decode is default_byte_decoder and step == 1
    if not byte_default and type(decode) is not MethodType:
        return _safe_fallback(font)
    owner = None if byte_default else decode.__self__
    if byte_default:
        mapping = _byte_defaults()
        missing = "\ufffd"
    elif (type(owner) is ToUnicodeCMap and decode.__func__ is ToUnicodeCMap.decode
            and owner.code_lengths == {step} and type(owner.mapping) is dict):
        mapping = _snapshot_map(owner.mapping, 2, step)
        if mapping is False:
            return _safe_fallback(font)
        missing = '\ufffd'
    elif (type(owner) is ToUnicodeCMap and decode.__func__ is ToUnicodeCMap.decode
          and type(owner.code_lengths) is set and owner.code_lengths == {1, 2}
          and all(type(size) is int for size in owner.code_lengths)
          and _snapshot_map(owner.mapping, 3, 0) is not False):
        # Preflight every operand: the longest-match decoder must consume the
        # same chunks as the width loop. Otherwise yield the complete operator.
        mapping = {code: value for (size, code), value in owner.mapping.items() if size == step}
        missing = '\ufffd'
        mixed = ((2, 1), owner.mapping)
    elif (step == 1 and type(owner) is Core14Decoder
          and decode.__func__ is Core14Decoder.decode
          and type(owner._preserve_undefined) is bool
          and (owner._fallback is default_byte_decoder or owner._preserve_undefined)
          and type(owner.mapping) is dict
          and _snapshot_map(owner.mapping, 1, step) is not False):
        mapping = {} if owner._preserve_undefined else _byte_defaults().copy()
        mapping.update(owner.mapping)
        missing = '\ufffd'
    else:
        return _safe_fallback(font)
    if (_snapshot_map(widths._widths, 0, step) is False
            or type(widths._default) not in (int, float)):
        return _safe_fallback(font)
    if step == 1:
        mapping = tuple(mapping.get(code, missing) for code in range(256))
    return (step, mapping, missing, widths._widths, widths._default,
            widths.reliable, widths._cid_default, font.space_code, font.bold, font.italic,
            font.link_metrics_reliable, True if byte_default else mixed)


def _safe_fallback(font):
    """False identifies a pure fallback; None denotes unsupported metadata."""
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
            or _snapshot_map(widths._widths, 0, 0) is False):
        return None
    decode = font.decode
    if decode is default_byte_decoder:
        return False
    if (type(decode) is MethodType and type(decode.__self__) is ToUnicodeCMap
            and decode.__func__ is ToUnicodeCMap.decode
            and type(decode.__self__.code_lengths) is set
            and all(type(v) is int for v in decode.__self__.code_lengths)
            and type(decode.__self__.mapping) is dict
            and _snapshot_map(decode.__self__.mapping, 3, 0) is not False):
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
            or _snapshot_map(cmap.mapping, 3, 0) is False
            or type(cmap.code_lengths) is not set
            or any(type(v) is not int for v in cmap.code_lengths)):
        return None
    lengths = {size for size, _lo, _hi in encoding._boxes}
    if len(lengths) != 1 or next(iter(lengths)) not in (1, 2):
        return None  # Variable-length/malformed spaces retain warning semantics.
    step = next(iter(lengths))
    if (_snapshot_map(font.widths._widths, 0, step) is False
            or type(font.widths._default) not in (int, float)):
        return None
    if cmap.code_lengths == {step}:
        # Keep sparse Unicode and CID width maps. The native loop searches the
        # normalized CID intervals only for codes actually present in text.
        normal, notdef = [], []
        current = encoding
        while current is not None:
            normal.append(current._ranges[step][1])
            notdef.append(current._notdef[step][1])
            current = current.parent
        spaces = tuple((int.from_bytes(lo, 'big'), int.from_bytes(hi, 'big'))
                       for _size, lo, hi in encoding._boxes)
        return (step, cmap.mapping, '\ufffd', font.widths._widths,
                font.widths._default, font.widths.reliable, font.widths._cid_default,
                font.space_code, font.bold, font.italic, font.link_metrics_reliable,
                (spaces, tuple(normal), tuple(notdef)))
    # Expand normalized ranges once, avoiding per-code space/bisect/decode
    # calls. Normal mappings throughout the parent chain precede notdef.
    chain = []
    current = encoding
    while current is not None:
        chain.append(current)
        current = current.parent
    cids = {}
    for notdef in (True, False):
        for current in reversed(chain):
            rows = (current._notdef if notdef else current._ranges)[step][1]
            for lo, hi, cid in rows:
                cids.update({code: cid if notdef else cid + code - lo
                             for code in range(max(0, lo), min(256 ** step - 1, hi) + 1)})
    valid = set()
    for size, lo, hi in encoding._boxes:
        if size == 1:
            valid.update(range(lo[0], hi[0] + 1))
        else:
            valid.update((first << 8) | second
                         for first in range(lo[0], hi[0] + 1)
                         for second in range(lo[1], hi[1] + 1))
    cids = {code: cid for code, cid in cids.items() if code in valid}
    if cmap.code_lengths == {step}:
        mapping = {code: cmap.mapping.get((step, code), '\ufffd') for code in cids}
    else:
        mapping = {code: cmap.decode(code.to_bytes(step, 'big')) for code in cids}
    widths = {code: font.widths.advance(cid) for code, cid in cids.items()}
    explicit = {code for code, cid in cids.items() if font.widths.explicit(cid)}
    if step == 1:
        mapping = tuple(mapping.get(code) for code in range(256))
    widths[-1] = font.widths.advance(font.space_code)
    return (step, mapping, '', widths, font.widths._default, font.widths.reliable,
            False, -1, font.bold, font.italic, font.link_metrics_reliable, frozenset(explicit))
