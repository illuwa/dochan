"""DOCX·PPTX 공용 OMML → LaTeX 변환기."""

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"m": M_NS}

# ── OMML(Office Math Markup Language) → LaTeX ──

def _m_tag(name: str) -> str:
    return f"{{{M_NS}}}{name}"


_OMML_CONTAINER_TAGS = frozenset(
    _m_tag(name)
    for name in ("oMath", "oMathPara", "e", "num", "den", "sub", "sup", "deg", "fName", "lim")
)

_NARY_OPERATORS = {
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∬": r"\iint", "∭": r"\iiint",
    "∮": r"\oint", "⋃": r"\bigcup", "⋂": r"\bigcap", "⋁": r"\bigvee", "⋀": r"\bigwedge",
}

_OMML_MAX_DEPTH = 32


def _omml_child(elem, name: str):
    return elem.find(f"m:{name}", namespaces=NS)


def _omml_join(elem, depth: int) -> str:
    return "".join(_omml_to_latex(child, depth + 1) for child in elem)


def _omml_to_latex(elem, depth: int = 0) -> str:
    """OMML 트리를 LaTeX 문자열로 재귀 변환. 미지원 요소는 자식 텍스트를 보존."""
    if depth > _OMML_MAX_DEPTH:
        return ""
    tag = elem.tag
    if tag == _m_tag("t"):
        return elem.text or ""
    if tag == _m_tag("r"):
        return "".join(t.text or "" for t in elem.findall("m:t", namespaces=NS))
    if tag in _OMML_CONTAINER_TAGS:
        return _omml_join(elem, depth)
    if tag == _m_tag("f"):
        num = _omml_child(elem, "num")
        den = _omml_child(elem, "den")
        return "\\frac{%s}{%s}" % (
            _omml_to_latex(num, depth + 1) if num is not None else "",
            _omml_to_latex(den, depth + 1) if den is not None else "",
        )
    if tag == _m_tag("sSup"):
        base = _omml_child(elem, "e")
        sup = _omml_child(elem, "sup")
        return "{%s}^{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(sup, depth + 1) if sup is not None else "",
        )
    if tag == _m_tag("sSub"):
        base = _omml_child(elem, "e")
        sub = _omml_child(elem, "sub")
        return "{%s}_{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(sub, depth + 1) if sub is not None else "",
        )
    if tag == _m_tag("sSubSup"):
        base = _omml_child(elem, "e")
        sub = _omml_child(elem, "sub")
        sup = _omml_child(elem, "sup")
        return "{%s}_{%s}^{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(sub, depth + 1) if sub is not None else "",
            _omml_to_latex(sup, depth + 1) if sup is not None else "",
        )
    if tag == _m_tag("rad"):
        deg = _omml_child(elem, "deg")
        base = _omml_child(elem, "e")
        deg_tex = _omml_to_latex(deg, depth + 1) if deg is not None else ""
        base_tex = _omml_to_latex(base, depth + 1) if base is not None else ""
        if deg_tex:
            return "\\sqrt[%s]{%s}" % (deg_tex, base_tex)
        return "\\sqrt{%s}" % base_tex
    if tag == _m_tag("nary"):
        nary_pr = _omml_child(elem, "naryPr")
        chr_elem = nary_pr.find("m:chr", namespaces=NS) if nary_pr is not None else None
        chr_val = chr_elem.get(f"{{{M_NS}}}val", "") if chr_elem is not None else ""
        operator = _NARY_OPERATORS.get(chr_val, r"\int")
        sub = _omml_child(elem, "sub")
        sup = _omml_child(elem, "sup")
        base = _omml_child(elem, "e")
        parts = operator
        sub_tex = _omml_to_latex(sub, depth + 1) if sub is not None else ""
        sup_tex = _omml_to_latex(sup, depth + 1) if sup is not None else ""
        if sub_tex:
            parts += "_{%s}" % sub_tex
        if sup_tex:
            parts += "^{%s}" % sup_tex
        base_tex = _omml_to_latex(base, depth + 1) if base is not None else ""
        return f"{parts} {base_tex}".rstrip()
    if tag == _m_tag("d"):  # 구분자 (기본 괄호)
        inner = ",".join(
            _omml_to_latex(e, depth + 1) for e in elem.findall("m:e", namespaces=NS)
        )
        d_pr = _omml_child(elem, "dPr")
        beg = end = None
        if d_pr is not None:
            beg_elem = d_pr.find("m:begChr", namespaces=NS)
            end_elem = d_pr.find("m:endChr", namespaces=NS)
            beg = beg_elem.get(f"{{{M_NS}}}val") if beg_elem is not None else None
            end = end_elem.get(f"{{{M_NS}}}val") if end_elem is not None else None
        return f"{beg if beg is not None else '('}{inner}{end if end is not None else ')'}"
    if tag == _m_tag("func"):
        fname = _omml_child(elem, "fName")
        base = _omml_child(elem, "e")
        return "%s(%s)" % (
            _omml_to_latex(fname, depth + 1) if fname is not None else "",
            _omml_to_latex(base, depth + 1) if base is not None else "",
        )
    if tag == _m_tag("limLow"):
        base = _omml_child(elem, "e")
        lim = _omml_child(elem, "lim")
        return "{%s}_{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(lim, depth + 1) if lim is not None else "",
        )
    if tag == _m_tag("limUpp"):
        base = _omml_child(elem, "e")
        lim = _omml_child(elem, "lim")
        return "{%s}^{%s}" % (
            _omml_to_latex(base, depth + 1) if base is not None else "",
            _omml_to_latex(lim, depth + 1) if lim is not None else "",
        )
    # 미지원 구조 — 자식을 이어붙여 텍스트 보존
    return _omml_join(elem, depth)


omml_to_latex = _omml_to_latex
