"""공개 PDF Formula의 수작업 정답과 모델/MCID 소비를 독립 대조한다.

실행: python -m scripts.probe_pdf_formulas /path/to/pdfjs/test/pdfs
정답 생성에 FormulaExtractor나 mathml_to_latex를 사용하지 않는다.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from dochan.model.equation import Equation
from dochan.pdf.content import ContentTextExtractor
from dochan.pdf.objects import PDFRef
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile


def expected_formulas():
    """원본 MathML을 읽어 수작업으로 적은 표준 LaTeX 의미 정답이다.

    None은 inline/code/Alt 원문 보존, 빈 문자열은 빈 구조이다.
    display 판단이나 정답 생성에 생산 변환기를 호출하지 않는다.
    """
    return {
        "bug1937438_af_from_latex.pdf": {
            42: None, 45: None, 48: None, 53: r"\sqrt{x^{2}}=|x|",
        },
        "bug1937438_mml_from_latex.pdf": {
            32: None, 59: r"c=\sqrt{a^{2}+b^{2}}",
        },
        "bug1997343.pdf": {
            141: None, 142: r"n^{p}=n\operatorname{mod}p",
            145: (r"\begin{matrix}\text{(2.1)} & f(x) & =\sin x+\cos x"
                  r" & f^{\prime}(x) & =\cos x-\sin x \\ "
                  r"\text{(2.2)} & g(x) & =2\cos x"
                  r" & g^{\prime}(x) & =-2\sin x\end{matrix}"),
            150: (r"(\begin{matrix}1 & 2 \\ 3 & 4\end{matrix})"
                  r"(\begin{matrix}1 & 1 \\ 0 & 1\end{matrix})="
                  r"(\begin{matrix}1 & 3 \\ 3 & 7\end{matrix})"),
            293: None, 294: None, 295: None, 296: None, 297: None,
            305: "", 306: None, 307: None, 308: None, 310: "", 311: None,
            312: None, 313: None, 314: None, 315: None, 316: None, 318: "", 319: None,
        },
        "bug2004951.pdf": {35: None},
        "bug2009627.pdf": {
            56: None, 57: r"n^{p}=n\operatorname{mod}p",
            60: r"(\begin{matrix}1 & 2 \\ 3 & 4\end{matrix})",
        },
        "bug2025674.pdf": {33: r"a^{2}+b^{2}=c^{2}"},
    }


def normalize_latex(value):
    """표본의 배치 간격과 안전한 명령 종결만 제거한다.

    빈 그룹에 첨자가 붙는 오류, 연산자 종류, 행/열 순서는 정규화하지 않는다.
    이 함수는 LaTeX 의미 전체를 판정하는 도구가 아니다.
    """
    value = re.sub(r"\\hspace\{[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:em|pt)\}", " ", value)
    value = re.sub(r"(\\[A-Za-z]+)\{\}(?!\s*[_^])", r"\1 ", value)
    return tuple(re.findall(r"\\[A-Za-z]+|\\.|[^\s]", value))


def _members(pdf, obj, inherited_page=None, seen=None):
    """원시 K의 구조 자식/정수/MCR만 순회하는 독립 정답 조사이다."""
    if seen is None:
        seen = set()
    if isinstance(obj, PDFRef):
        if obj.num in seen:
            return []
        seen.add(obj.num)
        obj = pdf.resolve(obj)
    if isinstance(obj, list):
        return [pair for child in obj for pair in _members(pdf, child, inherited_page, seen)]
    if isinstance(obj, int):
        return [(inherited_page, obj)]
    if not isinstance(obj, dict):
        return []
    page = obj.get("Pg", inherited_page)
    if obj.get("Type") == "MCR":
        return [(page, obj["MCID"])]
    return _members(pdf, obj.get("K"), page, seen)


class _ObservedReader(PDFReader):
    def __init__(self):
        super().__init__()
        self.body_stages = []

    def _body_groups(self, extractor, fragments, tables, boundaries=()):
        self.body_stages.append((list(fragments), list(boundaries)))
        return super()._body_groups(extractor, fragments, tables, boundaries)


def probe(corpus, include_additional=False):
    results = []
    # Kept as a compatible CLI flag; the semantic audit always covers all six PDFs.
    for name, expected in expected_formulas().items():
        path = corpus / name
        pdf = PDFFile(path.read_bytes())
        raw_formulas = {}
        for number in sorted(set(pdf.xref) | set(pdf._compressed)):
            obj = pdf.get_object(PDFRef(number, 0))
            if isinstance(obj, dict) and obj.get("S") == "Formula":
                raw_formulas[number] = obj
        assert set(raw_formulas) == set(expected), (name, "Formula object set changed")
        pages = pdf.pages()
        page_index = {id(page): index for index, (page, _) in enumerate(pages)}
        members = {}
        sources = {}
        for number, obj in raw_formulas.items():
            members[number] = [(page_index[id(pdf.resolve(pg))], mcid)
                               for pg, mcid in _members(pdf, obj)]
            sources[number] = []
            for ref in pdf.resolve(obj.get("AF", [])):
                spec = pdf.resolve(ref)
                stream_ref = pdf.resolve(spec["EF"])["F"]
                content = pdf.decode_stream_bytes(pdf.resolve(stream_ref))
                sources[number].append({"stream": stream_ref.num,
                                        "sha256": hashlib.sha256(content).hexdigest()})
        reader = _ObservedReader()
        ordered_expected = []
        selections = []
        for index, (page, resources) in enumerate(pages):
            extractor = ContentTextExtractor.from_fonts(reader._font_infos(pdf, resources, {}))
            properties = pdf.resolve(resources.get("Properties")) if isinstance(resources, dict) else None
            if isinstance(properties, dict):
                extractor.properties = {key: pdf.resolve(value) for key, value in properties.items()}
            raw = extractor.extract_page(b"\n".join(reader._page_content_parts(pdf, page)))
            selected = set()
            preserved = set()
            events = []
            for number, pairs in members.items():
                ids = {mcid for p, mcid in pairs if p == index}
                if not ids:
                    continue
                own = [fragment for fragment in raw.fragments if ids.intersection(fragment.mcids)]
                assert own, (name, number, "raw MCID lacks glyphs")
                assert ids.issubset(raw.marked_ids), (name, number, "missing raw marked content")
                orders = {fragment.order for fragment in own}
                if expected[number]:
                    assert selected.isdisjoint(orders), (name, number, "overlapping ownership")
                    selected.update(orders)
                    events.append((min(orders), number, expected[number]))
                else:
                    preserved.update(orders)
            events.sort()
            ordered_expected.extend(events)
            selections.append((raw.fragments, selected, preserved, [event[0] for event in events]))
        doc = reader.read(str(path))
        equations = [element for section in doc.sections for element in section.elements
                     if isinstance(element, Equation)]
        actual = [element.latex for element in equations]
        assert len(actual) == len(ordered_expected), (name, "display Equation count", actual)
        checks = []
        for equation, (_, number, latex) in zip(equations, ordered_expected):
            assert normalize_latex(equation.latex) == normalize_latex(latex), (
                name, number, "semantic LaTeX/order differs", latex, equation.latex)
            assert equation.script_format == "mathml", (name, number, "source kind missing")
            checks.append({"object": number, "expected_latex": latex,
                           "actual_latex": equation.latex, "semantic_match": True})
        assert len(reader.body_stages) == len(pages), (name, "body stage count")
        selected_count = preserved_count = body_count = artifact_count = 0
        for (fragments, boundaries), (raw, selected, preserved, bounds) in zip(reader.body_stages, selections):
            remaining = {fragment.order: fragment for fragment in fragments}
            assert selected.isdisjoint(remaining), (name, "display glyph duplicated in body")
            assert preserved.issubset(remaining), (name, "inline/code/Alt glyph lost")
            # Every unowned fragment is compared as well, including Artifacts.
            for fragment in raw:
                if fragment.order not in selected:
                    assert fragment.order in remaining, (name, "unowned body glyph lost", fragment.order)
                    assert remaining[fragment.order].text == fragment.text, (name, "body text changed")
                    body_count += 1
                    artifact_count += bool(fragment.artifact)
            selected_count += len(selected)
            preserved_count += len(preserved)
            assert sorted(boundaries) == bounds, (name, "display position differs")
        empty = [number for number, latex in expected.items() if latex == ""]
        assert all(not members[number] for number in empty), (name, "empty structure has MCID")
        results.append({"file": name, "raw_formula_count": len(expected),
                        "display_semantic_checks": checks,
                        "equations_expected": len(ordered_expected), "equations_actual": len(actual),
                        "preserved_formula_objects": sum(value is None for value in expected.values()),
                        "empty_structures": empty,
                        "owned_display_fragments": selected_count,
                        "preserved_inline_code_alt_fragments": preserved_count,
                        "preserved_unowned_fragments": body_count,
                        "preserved_unowned_artifacts": artifact_count,
                        "raw_mcid_position_match": True, "associated_sources": sources,
                        "errors": doc.errors})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--include-additional", action="store_true")
    args = parser.parse_args()
    results = probe(args.corpus, args.include_additional)
    output = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
