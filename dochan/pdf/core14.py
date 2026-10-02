"""ISO 32000-1 §9.6.2.2 / Annex D의 표준 글꼴과 단순 인코딩.

AFM은 kerning 없이 PDF 텍스트 연산자가 사용하는 글리프 advance를 제공한다.
명시적 Widths 또는 내장 폰트 프로그램보다 대체 글꼴 폭을 우선하지 않는다.
"""
from .core14_metrics import ENCODINGS, GLYPH_UNICODE, GLYPH_WIDTHS


# Explicit metric-compatible PostScript/Windows aliases only. A substring match
# would incorrectly give unrelated or subset fonts authoritative link geometry.
_ALIASES = {}
for family, target, styles in (
    ("Arial", "Helvetica", ("", "Bold", "Italic", "BoldItalic")),
    ("TimesNewRoman", "Times", ("", "Bold", "Italic", "BoldItalic")),
    ("CourierNew", "Courier", ("", "Bold", "Italic", "BoldItalic")),
):
    for style in styles:
        suffix = style.replace("Italic", "Oblique") if target != "Times" else style
        canonical = target + ("-" + suffix if suffix else "-Roman" if target == "Times" else "")
        for separator in ("", "-", ","):
            alias = family + (separator + style if style else "")
            for ending in ("", "MT"):
                _ALIASES[alias + ending] = canonical
        ps = family + "PS" + ("-" + style if style else "") + "MT"
        _ALIASES[ps] = canonical
_ALIASES["TimesNewRomanPS"] = "Times-Roman"


def canonical_font(name):
    if name in GLYPH_WIDTHS:
        return name
    return _ALIASES.get(name)


def glyph_names(base_font, encoding, truetype=False):
    """Return a bounded code → glyph map, or None for an unknown encoding."""
    canonical = canonical_font(base_font)
    if canonical is None:
        return None
    builtin = canonical + "Encoding" if canonical in ("Symbol", "ZapfDingbats") else "StandardEncoding"
    if truetype and canonical not in ("Symbol", "ZapfDingbats"):
        # ISO 32000-1 9.6.6.4: nonsymbolic TrueType uses Windows character
        # codes; StandardEncoding is a Type 1 built-in encoding.
        builtin = "WinAnsiEncoding"
    differences = None
    if isinstance(encoding, dict):
        differences = encoding.get("Differences")
        encoding = encoding.get("BaseEncoding")
    name = str(encoding) if encoding is not None else builtin
    if name not in ENCODINGS:
        return None
    names = dict(ENCODINGS[name])
    if isinstance(differences, list):
        code = -1
        for value in differences[:4096]:
            if isinstance(value, int) and not isinstance(value, bool):
                code = value
            elif isinstance(value, str):
                if 0 <= code < 256:
                    names[code] = value
                code += 1
    return names


def glyph_unicode(name):
    """Adobe Glyph List glyph-name rules, bounded to PDF's 127-byte names.

    Strip suffixes, split components, then resolve AGL or uppercase uni/u
    scalar names. Surrogate code points are not Unicode scalar values.
    """
    if len(name) > 127:
        return None
    name = name.split(".", 1)[0]
    result = []
    for part in name.split("_"):
        if part in GLYPH_UNICODE:
            result.append(GLYPH_UNICODE[part])
            continue
        if part.startswith("uni") and len(part) > 3 and (len(part) - 3) % 4 == 0:
            digits = part[3:]
            units = [digits[index:index + 4] for index in range(0, len(digits), 4)]
        elif part.startswith("u") and 5 <= len(part) <= 7:
            digits = part[1:]
            units = [digits]
        else:
            return None
        if any(char not in "0123456789ABCDEF" for char in digits):
            return None
        values = [int(unit, 16) for unit in units]
        if any(value > 0x10FFFF or 0xD800 <= value <= 0xDFFF for value in values):
            return None
        result.extend(chr(value) for value in values)
    return "".join(result) or None


class Core14Decoder:
    def __init__(self, names, fallback, preserve_undefined=False):
        self.mapping = {}
        self.reliable = True
        for code, glyph in names.items():
            value = glyph_unicode(glyph)
            if value is None:
                # Unknown names and .notdef are not a reason to lose the byte.
                value = fallback(bytes([code]))
                self.reliable = False
            self.mapping[code] = value
        self._fallback = fallback
        self._preserve_undefined = preserve_undefined

    def decode(self, raw):
        return "".join(self.mapping[code] if code in self.mapping else
                       "\ufffd" if self._preserve_undefined else self._fallback(bytes([code]))
                       for code in raw)
