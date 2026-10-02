"""Bounded, deliberately partial MathType MTEF 2/3/5 to LaTeX reader.

The record vocabulary follows Design Science's public MTEF v3/v5 format:
https://docs.wiris.com/en/mathtype/mathtype_desktop/mathtype-sdk/mtef3
https://docs.wiris.com/en/mathtype/mathtype_desktop/mathtype-sdk/mtef5

Supported semantic records are LINE, CHAR and a small set of v2/v3 TMPL
records (fences, roots, fractions, scripts and bars), plus v5 fractions and
fences. V5 encoding/font/preference definitions are consumed by their layouts.
Size/font metadata is ignored
only where its byte layout is known. Unknown records, glyphs, options and
templates raise MTEFError so the embedding reader can retain its preview.
This module does not infer mathematics from a rendered replacement image.
"""

import struct
from typing import List, NamedTuple


MAX_INPUT = 1024 * 1024
MAX_DEPTH = 64
MAX_RECORDS = 10000
MAX_OUTPUT = 100000


class MTEFError(ValueError):
    """Unsupported or malformed equation; the caller should keep its preview."""


_SYMBOLS = {
    "α": r"\alpha ", "β": r"\beta ", "γ": r"\gamma ", "δ": r"\delta ",
    "ε": r"\epsilon ", "ζ": r"\zeta ", "η": r"\eta ", "θ": r"\theta ",
    "ι": r"\iota ", "κ": r"\kappa ", "λ": r"\lambda ", "μ": r"\mu ",
    "ν": r"\nu ", "ξ": r"\xi ", "π": r"\pi ", "ρ": r"\rho ",
    "σ": r"\sigma ", "τ": r"\tau ", "υ": r"\upsilon ", "φ": r"\phi ",
    "χ": r"\chi ", "ψ": r"\psi ", "ω": r"\omega ", "Γ": r"\Gamma ",
    "Δ": r"\Delta ", "Θ": r"\Theta ", "Λ": r"\Lambda ", "Ξ": r"\Xi ",
    "Π": r"\Pi ", "Σ": r"\Sigma ", "Υ": r"\Upsilon ", "Φ": r"\Phi ",
    "Ψ": r"\Psi ", "Ω": r"\Omega ", "ϕ": r"\varphi ", "ϑ": r"\vartheta ",
    "±": r"\pm ", "∓": r"\mp ", "×": r"\times ", "÷": r"\div ",
    "⋅": r"\cdot ", "·": r"\cdot ", "•": r"\bullet ", "−": "-", "≤": r"\leq ",
    "≥": r"\geq ", "≠": r"\neq ", "≈": r"\approx ", "≡": r"\equiv ",
    "∞": r"\infty ", "∂": r"\partial ", "∇": r"\nabla ",
    "∈": r"\in ", "∉": r"\notin ", "⊂": r"\subset ", "⊆": r"\subseteq ",
    "∪": r"\cup ", "∩": r"\cap ", "∅": r"\emptyset ", "∑": r"\sum ",
    "∏": r"\prod ", "∫": r"\int ", "→": r"\to ", "←": r"\leftarrow ",
    "↔": r"\leftrightarrow ", "⇒": r"\Rightarrow ", "∀": r"\forall ",
    "∃": r"\exists ", "…": r"\ldots ", "⋯": r"\cdots ", "°": r"^{\circ}",
    "{": r"\{", "}": r"\}", "%": r"\%", "#": r"\#", "&": r"\&",
    "$": r"\$", "_": r"\_", "^": r"\hat{}", "\\": r"\backslash ",
    "~": r"\sim ", "⊗": r"\otimes ",
    # Observed MTCode spaces retain a visible separation. Do not invent TeX
    # widths from font positions; exact MathType spacing is presentation data.
    "\ueb01": r"{\ }", "\ueb02": r"{\ }", "\ueb04": r"{\ }",
}


class _Node(NamedTuple):
    kind: int
    text: str
    plain: bool = False


class _Reader:
    def __init__(self, data: bytes):
        if len(data) > MAX_INPUT:
            raise MTEFError("MTEF size limit exceeded")
        self.data = data
        self.pos = 0
        self.records = 0
        self.output = 0
        header = self.take(5)
        self.version = header[0]
        if self.version not in (2, 3, 5):
            raise MTEFError("Unsupported MTEF version")
        if self.version == 5:
            self.cstring()  # generating application key
            self.take(1)  # inline/display equation preference

    def take(self, size: int) -> bytes:
        if self.pos + size > len(self.data):
            raise MTEFError("Truncated MTEF record")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def byte(self) -> int:
        return self.take(1)[0]

    def cstring(self) -> bytes:
        end = self.data.find(b"\x00", self.pos, min(len(self.data), self.pos + 256))
        if end < 0:
            raise MTEFError("Unterminated MTEF string")
        return self.take(end + 1 - self.pos)[:-1]

    def uint(self) -> int:
        value = self.byte()
        return struct.unpack('<H', self.take(2))[0] if value == 255 else value

    def preferences(self):
        if self.byte():
            raise MTEFError('Unsupported MTEF equation preference options')
        # Sizes and spacings are packed nibble strings terminated by F. Strings
        # share bytes; each list, not each string, ends on a byte boundary.
        for _ in range(2):
            count = self.byte()
            completed = 0
            while completed < count:
                value = self.byte()
                for nibble in (value >> 4, value & 15):
                    if completed == count:
                        break
                    if nibble == 15:
                        completed += 1
        for _ in range(self.byte()):
            if self.uint():
                self.take(1)  # style of the referenced font; zero has no style

    def nodes(self, depth: int = 0) -> List[_Node]:
        if depth > MAX_DEPTH:
            raise MTEFError("MTEF depth limit exceeded")
        nodes = []
        while True:
            tag = self.byte()
            self.records += 1
            if self.records > MAX_RECORDS:
                raise MTEFError("MTEF record limit exceeded")
            kind = tag & 15 if self.version < 5 else tag
            if kind == 0:
                if tag:
                    raise MTEFError("Invalid MTEF END options")
                return nodes
            options = tag >> 4 if self.version < 5 else (
                self.byte() if kind in (1, 2, 3, 4, 5, 6) else 0)
            if options & 8:
                x, y = self.take(2)
                if x == 128 and y == 128:
                    self.take(4)
                options &= ~8
            if kind == 1:
                if options & ~1:
                    raise MTEFError("Unsupported MTEF LINE options")
                value = "" if options & 1 else self.join(self.nodes(depth + 1))
            elif kind == 2:
                node = self.character(options)
                value = node.text
            elif kind == 3:
                if options:
                    raise MTEFError("Unsupported MTEF TMPL options")
                selector = self.byte()
                variation = self.byte()
                if self.version == 5 and variation & 128:
                    variation = (variation & 127) | (self.byte() << 7)
                template_options = self.byte()
                if template_options:
                    raise MTEFError("Unsupported MTEF template options")
                value = self.template(selector, variation, self.nodes(depth + 1))
            elif kind in (10, 11, 12, 13, 14):
                if options:
                    raise MTEFError("Invalid MTEF size options")
                continue  # FULL/SUB/SUB2/SYM/SUBSYM are presentation metadata
            elif kind == 8 and self.version < 5 and not options:
                self.take(2)  # font number and style
                self.cstring()
                continue
            elif kind == 17 and self.version == 5:
                self.uint()  # encoding definition index
                self.cstring()
                continue
            elif kind == 18 and self.version == 5:
                self.preferences()
                continue
            elif kind == 19 and self.version == 5:
                self.cstring()
                continue
            else:
                raise MTEFError("Unsupported MTEF record {}".format(kind))
            self.output += len(value)
            if self.output > MAX_OUTPUT:
                raise MTEFError("MTEF output limit exceeded")
            nodes.append(node if kind == 2 else _Node(kind, value))

    @staticmethod
    def join(nodes: List[_Node]) -> str:
        result = []
        text = []
        for node in nodes:
            if node.plain:
                text.append(node.text)
            else:
                if text:
                    result.append(r'\text{' + ''.join(text) + '}')
                    text = []
                result.append(node.text)
        if text:
            result.append(r'\text{' + ''.join(text) + '}')
        return ''.join(result)

    def character(self, options: int) -> _Node:
        # v3 option 1 is the function/typeface hint, not an attached embellishment.
        # v5 font positions are redundant when MTCode is present; embellishments
        # and characters without MTCode still require preview fallback.
        if options & ~(1 if self.version < 5 else 0x14):
            raise MTEFError("Unsupported MTEF CHAR options")
        face = self.byte()
        code = self.byte() if self.version == 2 else struct.unpack("<H", self.take(2))[0]
        if self.version == 5:
            if options & 4:
                self.take(1)
            if options & 16:
                self.take(2)
        if self.version == 2:
            # Before MTCode, CHAR stores a byte in the selected typeface.
            if face in (0x84, 0x85, 0x86, 0x96):
                from .symbol_fonts import _SYMBOL_UNICODE
                # Identity glyphs verified against Symbol's cmap. In particular
                # byte 0x60 is a radical extender, not an ASCII backtick.
                identity = ' !#%&()+,./0123456789:;<=>?[]_{}|'
                code = _SYMBOL_UNICODE.get(code, code if chr(code) in identity else 0)
                code = {0x23A1: ord('['), 0x23A4: ord(']')}.get(code, code)
            elif face not in (0x81, 0x82, 0x83, 0x87, 0x88):
                raise MTEFError('Unsupported MTEF v2 typeface')
        value = chr(code)
        if face == 0x81:
            if not 32 <= code <= 126:
                raise MTEFError('Unsupported MTEF text character')
            escapes = {'\\': r'\textbackslash{}', '~': r'\textasciitilde{}',
                       '^': r'\textasciicircum{}'}
            value = escapes.get(value, '\\' + value if value in '{}%#&$_' else value)
            return _Node(2, value, True)
        if value in _SYMBOLS:
            return _Node(2, _SYMBOLS[value])
        if 32 <= code <= 126:
            return _Node(2, value)
        raise MTEFError("Unsupported MTEF character U+{:04X}".format(code))

    def template(self, selector: int, variation: int, children: List[_Node]) -> str:
        # v3 has one SCRIPT selector. v5 templates use a different numbering.
        selectors = ({13: "root", 14: "fraction", 15: "script", 16: "under",
                      17: "over"} if self.version < 5 else
                     {11: "fraction"})
        name = selectors.get(selector)
        if name:
            if any(child.kind != 1 for child in children):
                raise MTEFError("Invalid MTEF template slots")
            slots = [child.text for child in children]
            if name == "fraction" and variation in ((0,) if self.version < 5 else (0, 2)) and len(slots) == 2:
                return r"\frac{" + slots[0] + "}{" + slots[1] + "}"
            if name == "root" and variation == 0 and len(slots) == 2:
                return ((r"\sqrt[" + slots[1] + "]{" + slots[0] + "}")
                        if slots[1] else r"\sqrt{" + slots[0] + "}")
            if name in ("under", "over") and variation == 0 and len(slots) == 1:
                return "\\" + name + "line{" + slots[0] + "}"
            if name == "script" and variation in (0, 1, 2) and len(slots) == 2:
                if (variation == 0 and slots[0]) or (variation == 1 and slots[1]):
                    raise MTEFError("Invalid MTEF script slots")
                return (("_{" + slots[0] + "}" if slots[0] else "") +
                        ("^{" + slots[1] + "}" if slots[1] else ""))
            raise MTEFError("Unsupported MTEF {} variation/slots".format(name))
        # Basic fences carry a body LINE followed by the actual delimiter CHARs.
        if ((self.version < 5 and selector in range(8) and variation == 0) or
                (self.version == 5 and selector in range(8) and variation == 3)):
            if len(children) == 3 and [c.kind for c in children] == [1, 2, 2]:
                left, right = children[1].text, children[2].text
                if left in ("(", "[", r"\{", "|") and right in (")", "]", r"\}", "|"):
                    return r"\left" + left + children[0].text + r"\right" + right
        raise MTEFError("Unsupported MTEF template {}".format(selector))


def parse_mtef(data: bytes) -> str:
    """Return LaTeX without math delimiters, or raise MTEFError for fallback."""
    reader = _Reader(data)
    result = reader.join(reader.nodes()).strip()
    if any(data[reader.pos:]):
        raise MTEFError("Unexpected data after MTEF END")
    if not result:
        raise MTEFError("Empty MTEF equation")
    return result


def parse_equation_native(data: bytes) -> str:
    """Read Equation Native's 28-byte EQNOLEFILEHDR and bounded MTEF payload."""
    if len(data) > MAX_INPUT + 28:
        raise MTEFError("Equation Native size limit exceeded")
    if len(data) < 28:
        raise MTEFError("Truncated Equation Native header")
    header_size = struct.unpack_from("<H", data)[0]
    payload_size = struct.unpack_from("<I", data, 8)[0]
    if header_size != 28 or not payload_size or payload_size > len(data) - 28:
        raise MTEFError("Invalid Equation Native header/length")
    return parse_mtef(data[28:28 + payload_size])
