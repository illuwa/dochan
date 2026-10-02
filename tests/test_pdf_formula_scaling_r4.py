"""수식의 처리량 상한과 실패 시 보존을 시간 측정 없이 검증한다."""
import pytest

from dochan.output.markdown import to_markdown
from dochan.pdf import formulas
from dochan.pdf.content import Fragment, PageContent
from dochan.pdf.formulas import FormulaExtractor
from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from test_pdf_structure import _build_pdf, _minimal_objects


class _CountedFragment(Fragment):
    """실제 Fragment 속성 접근만 계수하며 값과 동작은 바꾸지 않는다."""

    def __init__(self, reads, **kwargs):
        self.reads = reads
        super().__init__(**kwargs)

    def __getattribute__(self, name):
        if name in ("mcids", "y"):
            reads = object.__getattribute__(self, "reads")
            reads[name] += 1
        return super().__getattribute__(name)


def _fragment(reads, order, mcids=(), y=700.0):
    return _CountedFragment(reads, x=50.0, y=y, width=5.0, size=10.0,
                            text="x", space_width=3.0, order=order, mcids=mcids)


def _objects(formula_count=1, content=b""):
    objects = _minimal_objects(content)
    objects[1] = "<< /Type /Catalog /Pages 2 0 R /StructTreeRoot 6 0 R >>"
    refs = " ".join("%d 0 R" % (20 + i) for i in range(formula_count))
    objects[6] = "<< /Type /StructTreeRoot /K [%s] >>" % refs
    for i in range(formula_count):
        objects[20 + i] = "<< /S /Formula /Pg 3 0 R /K %d /AF [8 0 R] >>" % i
    objects[8] = "<< /F (math.tex) /EF << /F 9 0 R >> >>"
    data = b"x^{2}"
    objects[9] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(data), data)
    return objects


@pytest.mark.parametrize("token_count", [24, 96])
def test_namespace_mathml_tokens_do_not_rescan_all_fragment_mcids(token_count):
    objects = _objects()
    objects[20] = "<< /S /Formula /Pg 3 0 R /K 10 0 R >>"
    refs = " ".join("%d 0 R" % (100 + i) for i in range(token_count))
    objects[10] = "<< /S /math /NS 11 0 R /K [%s] >>" % refs
    objects[11] = "<< /Type /Namespace /NS (http://www.w3.org/1998/Math/MathML) >>"
    for i in range(token_count):
        objects[100 + i] = "<< /S /mi /NS 11 0 R /K %d >>" % i
    pdf = PDFFile(_build_pdf(objects))
    page = pdf.pages()[0][0]
    reads = {"mcids": 0, "y": 0}
    fragments = [_fragment(reads, i, (i,)) for i in range(token_count)]
    fragments += [_fragment(reads, token_count + i, y=600.0) for i in range(token_count)]
    content = PageContent(fragments, [], marked_ids=set(range(token_count)))

    events, consumed = FormulaExtractor(pdf).apply(page, content)

    assert len(events) == 1
    assert events[0][2].latex == "x" * token_count
    assert consumed == set(range(token_count))
    # A small fixed number of whole-page passes is allowed; one per token is not.
    assert reads["mcids"] <= 4 * len(fragments)
    assert not pdf.warnings


@pytest.mark.parametrize("member_count", [24, 96])
def test_formula_geometry_y_reads_do_not_multiply_members_by_page(member_count):
    pdf = PDFFile(_build_pdf(_objects()))
    page = pdf.pages()[0][0]
    reads = {"mcids": 0, "y": 0}
    fragments = [_fragment(reads, i, (0,)) for i in range(member_count)]
    fragments += [_fragment(reads, member_count + i, y=600.0) for i in range(member_count)]
    content = PageContent(fragments, [], marked_ids={0})

    events, consumed = FormulaExtractor(pdf).apply(page, content)

    assert len(events) == 1
    assert consumed == set(range(member_count))
    # The isolated row forces a complete negative overlap search. Count data
    # reads rather than wall time, so CI speed and scheduling do not matter.
    assert reads["y"] <= 12 * len(fragments)
    assert not pdf.warnings


def _multi_formula_pdf(tmp_path, count=4):
    content = b" ".join(
        ("/Formula <</MCID %d>> BDC BT /F1 12 Tf 50 %d Td (FORMULA-%d) Tj ET EMC"
         % (i, 700 - i * 60, i)).encode("ascii")
        for i in range(count)
    )
    path = tmp_path / "formulas.pdf"
    path.write_bytes(_build_pdf(_objects(count, content)))
    return path


def test_geometry_budget_exhaustion_warns_once_and_preserves_every_formula(tmp_path, monkeypatch):
    monkeypatch.setattr(formulas, "MAX_FORMULA_GEOMETRY_CHECKS", 1, raising=False)
    path = _multi_formula_pdf(tmp_path)

    doc = PDFReader().read(str(path))

    assert not doc.find_all("equation")
    text = to_markdown(doc)
    assert all("FORMULA-%d" % i in text for i in range(4))
    assert sum("기하 검사 한도" in error for error in doc.errors) == 1


def test_failed_formula_discovery_does_not_convert_partial_records_in_text_tables(tmp_path, monkeypatch):
    path = _multi_formula_pdf(tmp_path)

    def fail_after_discovery(self, page):
        assert self._for_page(page)
        raise ValueError("synthetic discovery failure after collecting records")

    monkeypatch.setattr(FormulaExtractor, "has_formulas", fail_after_discovery, raising=False)

    doc = PDFReader(text_tables=True).read(str(path))

    assert not doc.find_all("equation")
    text = to_markdown(doc)
    assert all("FORMULA-%d" % i in text for i in range(4))
    assert sum("synthetic discovery failure" in error for error in doc.errors) == 1
