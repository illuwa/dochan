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


def glyph_names(base_font, encoding):
    """Return a bounded code → glyph map, or None for an unknown encoding."""
    canonical = canonical_font(base_font)
    if canonical is None:
        return None
    builtin = canonical + "Encoding" if canonical in ("Symbol", "ZapfDingbats") else "StandardEncoding"
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


class Core14Decoder:
    def __init__(self, names):
        self.mapping = {code: GLYPH_UNICODE[glyph] for code, glyph in names.items()
                        if glyph in GLYPH_UNICODE}
        self.reliable = all(glyph in GLYPH_UNICODE for glyph in names.values())

    def decode(self, raw):
        return "".join(self.mapping.get(code, "\ufffd") for code in raw)
