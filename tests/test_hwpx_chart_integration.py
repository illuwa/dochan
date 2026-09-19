"""Package/API chart integration; real-document gold uses only stdlib XML."""
import hashlib
from pathlib import Path
import struct
import zlib
# Independent gold reader: every external archive is SHA-256 verified before XML parsing.
import xml.etree.ElementTree as ET  # nosemgrep: use-defused-xml
# quoteattr only escapes generated test attributes; it does not parse XML.
from xml.sax.saxutils import quoteattr  # nosemgrep: use-defused-xml
import zipfile

import pytest

from dochan import Dochan
from dochan.hwpx import charts, parser
from dochan.model.document import Paragraph
from dochan.model.table import Table


ROOT = Path(__file__).resolve().parents[1]
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
EXT = "http://www.hancom.co.kr/hwpml/2016/ooxmlchart"
NS = {"c": C}
DECL = f'xmlns:hp="{HP}" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'


def chart_xml(kind="pieChart", title=""):
    heading = f'<c:title><c:tx><c:v>{title}</c:v></c:tx></c:title>' if title else ""
    return (
        f'<c:chartSpace xmlns:c="{C}"><c:chart>{heading}<c:plotArea><c:{kind}>'
        '<c:ser><c:order val="0"/><c:tx><c:v>판매</c:v></c:tx>'
        '<c:cat><c:strLit><c:ptCount val="2"/><c:pt idx="0"><c:v>A</c:v></c:pt>'
        '<c:pt idx="1"><c:v>B</c:v></c:pt></c:strLit></c:cat>'
        '<c:val><c:numLit><c:ptCount val="2"/><c:pt idx="0"><c:v>0</c:v></c:pt>'
        '<c:pt idx="1"><c:v>2.00</c:v></c:pt></c:numLit></c:val>'
        f'</c:ser></c:{kind}></c:plotArea></c:chart></c:chartSpace>'
    ).encode()


def reference(ref="Chart/chart1.xml"):
    return '<hp:chart chartIDRef=%s/>' % quoteattr(ref)


def paragraph(body):
    return f'<hp:p><hp:run>{body}</hp:run></hp:p>'


def switch(body, fallback='<hp:t>FALLBACK</hp:t>'):
    return (f'<hp:switch><hp:case hp:required-namespace="{EXT}">{body}'
            f'</hp:case><hp:default>{fallback}</hp:default></hp:switch>')


def package(tmp_path, bodies=None, parts=None, header=None):
    path = tmp_path / "charts.hwpx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/hwp+zip")
        for i, body in enumerate(bodies or [paragraph(reference())]):
            z.writestr(f"Contents/section{i}.xml", f'<hs:sec {DECL}>{body}</hs:sec>')
        for name, data in (parts if parts is not None else {"Chart/chart1.xml": chart_xml()}).items():
            z.writestr(name, data)
        if header:
            z.writestr("Contents/header.xml", header)
    return path


def rows(table):
    return [[cell.text for cell in row] for row in table.rows]


def warned(doc, code):
    return any(f"[chart:{code}]" in error for error in doc.errors)


@pytest.mark.parametrize("wrapped", [False, True])
def test_body_order_title_and_switch_select_one_branch(tmp_path, wrapped):
    node = switch(reference()) if wrapped else reference()
    body = paragraph('<hp:t>before</hp:t>' + node + '<hp:t>after</hp:t>')
    doc = Dochan(package(tmp_path, [body], {"Chart/chart1.xml": chart_xml(title="제목")})).doc
    assert doc.errors == []
    elems = doc.sections[0].elements
    assert [type(x) for x in elems] == [Paragraph, Paragraph, Table, Paragraph]
    assert [x.text for x in elems if isinstance(x, Paragraph)] == ["before", "제목", "after"]
    assert rows(elems[2]) == [["범주", "값"], ["A", "0"], ["B", "2.00"]]


@pytest.mark.parametrize("ref", [
    "../Chart/chart1.xml", "Chart/../chart1.xml", "Chart/sub/../../chart1.xml",
    "/Chart/chart1.xml", "https://example.test/chart.xml", "file:///Chart/chart1.xml",
    "//host/Chart/chart1.xml", "C:/Chart/chart1.xml", "Chart\\chart1.xml",
    "Chart/%2e%2e/chart1.xml", "Chart/chart1.xml?x=1", "Chart/chart1.xml#x",
    "chart1.xml", "Contents/Chart/chart1.xml", "Chart//chart1.xml", "Chart/./chart1.xml", "",
])
def test_unsafe_references_are_explicit_and_never_read(tmp_path, monkeypatch, ref):
    path = package(tmp_path, [paragraph(reference(ref))])
    original = zipfile.ZipFile.open

    def guarded(archive, name, *args, **kwargs):
        filename = name.filename if isinstance(name, zipfile.ZipInfo) else name
        assert not filename.startswith("Chart/")
        return original(archive, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", guarded)
    doc = Dochan(path).doc
    assert not doc.find_all("table")
    assert warned(doc, "invalid_reference")


@pytest.mark.parametrize("parts,code", [
    ({}, "missing_part"),
    ({"Chart/chart1.xml": b"<broken>"}, "invalid_xml"),
    ({"Chart/chart1.xml": chart_xml("bubbleChart")}, "unsupported_type"),
    ({"Chart/chart1.xml": b'<!DOCTYPE a [<!ENTITY x "secret">]><a/>'}, "doctype"),
])
def test_missing_broken_unsupported_and_unsafe_xml_reach_errors(tmp_path, parts, code):
    doc = Dochan(package(tmp_path, [paragraph(switch(reference()))], parts)).doc
    assert warned(doc, code)
    assert not doc.find_all("table")
    assert "FALLBACK" not in [p.text for p in doc.find_all("paragraph")]


def test_crc_corruption_does_not_drop_surrounding_text(tmp_path):
    path = package(tmp_path, [paragraph('<hp:t>A</hp:t>' + reference() + '<hp:t>B</hp:t>')])
    data = bytearray(path.read_bytes())
    offset = 0
    while True:
        offset = data.index(b"PK\x01\x02", offset)
        length = struct.unpack_from("<H", data, offset + 28)[0]
        if data[offset + 46:offset + 46 + length] == b"Chart/chart1.xml":
            data[offset + 16] ^= 1  # Central-directory CRC, leaving XML bytes unchanged.
            break
        offset += 4
    path.write_bytes(data)
    doc = Dochan(path).doc
    assert warned(doc, "part_read")
    assert ''.join(p.text for p in doc.find_all("paragraph")) == "AB"


def test_deflate_corruption_does_not_abort_the_section(tmp_path, monkeypatch):
    path = package(tmp_path, [paragraph('<hp:t>A</hp:t>' + reference() + '<hp:t>B</hp:t>')])
    original = zipfile.ZipExtFile.read

    def damaged(stream, n=-1):
        if stream.name.startswith("Chart/"):
            raise zlib.error("invalid block type")
        return original(stream, n)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", damaged)
    doc = Dochan(path).doc
    assert warned(doc, "part_read")
    assert ''.join(p.text for p in doc.find_all("paragraph")) == "AB"


def test_actual_read_size_is_checked_even_if_zip_metadata_is_small(tmp_path, monkeypatch):
    path = package(tmp_path)
    monkeypatch.setattr(charts, "MAX_XML_BYTES", 600)
    original = zipfile.ZipExtFile.read

    def overrun(stream, n=-1):
        if stream.name.startswith("Chart/"):
            assert n == 601
            return b"x" * 601
        return original(stream, n)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", overrun)
    doc = Dochan(path).doc
    assert not doc.find_all("table") and warned(doc, "limit")


def test_normalized_zip_alias_is_not_used_for_exact_reference(tmp_path):
    doc = Dochan(package(tmp_path, parts={"Chart/sub/../chart1.xml": chart_xml()})).doc
    assert not doc.find_all("table") and warned(doc, "invalid_reference")


@pytest.mark.parametrize("constant,value", [
    ("MAX_SERIES", 0), ("MAX_POINTS", 1), ("MAX_TOTAL_POINTS", 3), ("MAX_GRID_CELLS", 5),
])
def test_chart_module_limits_are_preserved_through_api(tmp_path, monkeypatch, constant, value):
    monkeypatch.setattr(charts, constant, value)
    doc = Dochan(package(tmp_path)).doc
    assert not doc.find_all("table") and warned(doc, "limit")


def test_title_cache_and_duplicate_points_consume_document_point_budget(tmp_path, monkeypatch):
    xml = chart_xml().replace(b'<c:chart>', (
        '<c:chart><c:title><c:tx><c:strRef><c:strCache><c:ptCount val="1"/>'
        '<c:pt idx="0"><c:v>title</c:v></c:pt><c:pt idx="0"><c:v>duplicate</c:v></c:pt>'
        '</c:strCache></c:strRef></c:tx></c:title>').encode())
    monkeypatch.setattr(parser, "MAX_DOCUMENT_CHART_POINTS", 10)
    doc = Dochan(package(tmp_path, [paragraph(reference() * 2)], {"Chart/chart1.xml": xml})).doc
    assert len(doc.find_all("table")) == 1 and warned(doc, "document_limit")


def test_unknown_switch_uses_only_default_without_chart_read(tmp_path):
    body = switch(reference(), '<hp:t>fallback</hp:t>').replace(EXT, "urn:unknown")
    doc = Dochan(package(tmp_path, [paragraph(body)], {})).doc
    assert doc.errors == []
    assert [p.text for p in doc.find_all("paragraph")] == ["fallback"]


@pytest.mark.parametrize("guard", ["size", "ratio"])
def test_zip_limits_checked_before_opening_chart(tmp_path, monkeypatch, guard):
    path = package(tmp_path)
    original_info = zipfile.ZipFile.getinfo
    original_open = zipfile.ZipFile.open

    def info(archive, name):
        item = original_info(archive, name)
        if name == "Chart/chart1.xml":
            if guard == "size":
                item.file_size = charts.MAX_XML_BYTES + 1
            else:
                item.file_size, item.compress_size = parser.MAX_COMPRESSION_RATIO + 1, 1
        return item

    def opened(archive, name, *args, **kwargs):
        assert (name.filename if isinstance(name, zipfile.ZipInfo) else name) != "Chart/chart1.xml"
        return original_open(archive, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "getinfo", info)
    monkeypatch.setattr(zipfile.ZipFile, "open", opened)
    doc = Dochan(path).doc
    assert warned(doc, "limit")


def test_bounded_read_zip_lifetime_cache_isolation_and_reset(tmp_path, monkeypatch):
    path = package(tmp_path, [paragraph(reference()), paragraph(reference())])
    original = zipfile.ZipExtFile.read
    reads = []

    def bounded(stream, n=-1):
        if stream.name == "Chart/chart1.xml":
            assert 0 <= n <= charts.MAX_XML_BYTES + 1
            reads.append(n)
        return original(stream, n)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", bounded)
    instance = parser.HWPXParser()
    doc = instance.parse(path)
    assert doc.errors == []
    tables = doc.find_all("table")
    assert len(tables) == 2 and len(reads) == 1
    tables[0].rows[1][1].paragraphs[0].runs[0].text = "changed"
    tables[0].caption[0].runs[0].text = "changed"
    assert tables[1].caption_text == "판매" and rows(tables[1])[1][1] == "0"
    assert instance._chart_archive is None and instance._chart_cache == {}
    next_doc = instance.parse(path)
    assert next_doc.errors == [] and len(next_doc.find_all("table")) == 2
    assert rows(next_doc.find_all("table")[0])[1][1] == "0"


@pytest.mark.parametrize("constant,limit", [
    ("MAX_DOCUMENT_CHARTS", 1), ("MAX_DOCUMENT_CHART_SERIES", 1),
    ("MAX_DOCUMENT_CHART_POINTS", 4), ("MAX_DOCUMENT_CHART_CELLS", 6),
    ("MAX_DOCUMENT_CELLS", 6), ("MAX_DOCUMENT_CHART_BYTES", len(chart_xml())),
])
@pytest.mark.parametrize("same_part", [True, False])
def test_document_budgets_include_repeated_placements_across_sections(tmp_path, monkeypatch, constant, limit, same_part):
    monkeypatch.setattr(parser, constant, limit, raising=False)
    second = "Chart/chart1.xml" if same_part else "Chart/chart2.xml"
    doc = Dochan(package(tmp_path, [paragraph(reference()), paragraph(reference(second))],
                         {"Chart/chart1.xml": chart_xml(), "Chart/chart2.xml": chart_xml()})).doc
    assert len(doc.find_all("table")) == 1
    assert warned(doc, "document_limit")


@pytest.mark.parametrize("chart_first", [False, True])
@pytest.mark.parametrize("coordinates", [False, True])
def test_normal_table_and_chart_share_document_cell_budget(tmp_path, monkeypatch, chart_first, coordinates):
    monkeypatch.setattr(parser, "MAX_DOCUMENT_CELLS", 6)
    table = ('<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
             '<hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
             + paragraph('<hp:t>ordinary</hp:t>') + '</hp:subList></hp:tc></hp:tr></hp:tbl>')
    if not coordinates:
        table = table.replace('<hp:cellAddr rowAddr="0" colAddr="0"/>', '')
    body = reference() + table if chart_first else table + reference()
    doc = Dochan(package(tmp_path, [paragraph(body)])).doc
    assert sum(len(r) for t in doc.find_all("table") for r in t.rows) <= 6
    assert doc.errors


@pytest.mark.parametrize("wrapper", [
    '<hp:ctrl>{}</hp:ctrl>',
    '<hp:container>{}</hp:container>',
    '<hp:ctrl><hp:header><hp:subList>' + paragraph('{}') + '</hp:subList></hp:header></hp:ctrl>',
    '<hp:tbl><hp:tr><hp:tc><hp:subList>' + paragraph('{}') + '</hp:subList></hp:tc></hp:tr></hp:tbl>',
])
def test_nested_chart_placement_is_preserved(tmp_path, wrapper):
    doc = Dochan(package(tmp_path, [paragraph(wrapper.format(switch(reference())))])).doc
    assert doc.errors == []
    assert len([t for t in doc.find_all("table") if t.caption_text == "판매"]) == 1


def test_unhandled_chart_placement_is_not_silent(tmp_path):
    doc = Dochan(package(tmp_path, [paragraph('<hp:unknown>' + reference() + '</hp:unknown>')])).doc
    assert warned(doc, "unsupported_placement")


def test_foreign_chart_qname_is_not_treated_as_hp_chart(tmp_path):
    body = paragraph('<other:chart xmlns:other="urn:other" chartIDRef="Chart/chart1.xml"/>')
    doc = Dochan(package(tmp_path, [body])).doc
    assert not doc.find_all("table") and warned(doc, "unsupported_namespace")


@pytest.mark.parametrize("mode", ["preserve", "final", "original"])
def test_revision_projection_and_assets_option_are_kept(tmp_path, mode):
    body = paragraph('<hp:t>before<hp:deleteBegin Id="d" TcId="2"/></hp:t>'
                     + switch(reference()) + '<hp:t><hp:deleteEnd Id="d" TcId="2" paraend="0"/>after</hp:t>')
    header = ('<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">'
              '<hh:trackChange id="2" type="Delete"/></hh:head>')
    doc = Dochan(package(tmp_path, [body], header=header), include_assets=False, revision_mode=mode).doc
    assert len(doc.find_all("table")) == 1
    assert any('revision partial [object]' in e for e in doc.errors)


def test_text_revision_next_to_chart_still_projects(tmp_path):
    body = paragraph('<hp:t>A<hp:deleteBegin Id="d" TcId="2"/>deleted'
                     '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>B</hp:t>' + reference())
    header = ('<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head">'
              '<hh:trackChange id="2" type="Delete"/></hh:head>')
    doc = Dochan(package(tmp_path, [body], header=header), include_assets=False, revision_mode="final").doc
    assert doc.errors == [] and len(doc.find_all("table")) == 1
    assert doc.sections[0].elements[0].text == "AB"


PUBLIC = [
    ("2차원원형.hwpx", "ce4304b8aa4fba79d493647d6fb1204b527bc2aac50c55a94bea9ec67f8994a8",
     "pieChart", ["판매"], [["10", "3.5", "1.5", "1.2"]]),
    ("꺽은선형.hwpx", "a8a4449c3641c107aadb6e597dbb780b5b7ae3dc50d4a144a2e87075af2fc398",
     "lineChart", ["계열 1", "계열 2", "계열 3"],
     [["4.3", "2.5", "3.5", "4.5"], ["2.4", "4.4", "1.8", "2.8"], ["2", "2", "3", "5"]]),
]


def public_path(name):
    path = ROOT / "corpus/hwp-public/hwpx" / name
    if not path.is_file():
        pytest.skip("public corpus absent; this is not a real-document validation pass")
    return path


def xml_gold(raw, kind):
    """Independent oracle for complete stored string/numeric caches only."""
    root = ET.fromstring(raw)
    group = root.find("c:chart/c:plotArea/c:" + kind, NS)
    assert group is not None
    result = []
    for series in sorted(group.findall("c:ser", NS), key=lambda s: int(s.find("c:order", NS).get("val"))):
        tx = series.find("c:tx", NS)
        name = tx.findtext("c:v", namespaces=NS)
        if name is None:
            name = tx.findtext("c:strRef/c:strCache/c:pt/c:v", namespaces=NS)
        columns = []
        for axis in ("cat", "val") if kind != "scatterChart" else ("xVal", "yVal"):
            axis_node = series.find("c:" + axis, NS)
            cache = next(x for x in axis_node.iter() if x.tag in {
                '{%s}%s' % (C, t) for t in ("strCache", "numCache", "strLit", "numLit")})
            values = {int(p.get("idx")): p.findtext("c:v", default="", namespaces=NS)
                      for p in cache.findall("c:pt", NS)}
            count = int(cache.find("c:ptCount", NS).get("val"))
            assert set(values) == set(range(count))
            columns.append([values[i] for i in range(count)])
        assert len(columns[0]) == len(columns[1])
        result.append((name, list(map(list, zip(*columns)))))
    return result


@pytest.mark.parametrize("name,digest,kind,names,values", PUBLIC, ids=["public-pie", "public-line"])
def test_dochan_api_public_documents_match_independent_gold(name, digest, kind, names, values):
    path = public_path(name)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(path) as z:
        gold = xml_gold(z.read("Chart/chart1.xml"), kind)
    assert [n for n, _ in gold] == names
    assert [[r[1] for r in data] for _, data in gold] == values
    doc = Dochan(path, include_assets=False).doc
    assert doc.errors == []
    assert [(t.caption_text, rows(t)[1:]) for t in doc.find_all("table")] == gold


@pytest.mark.parametrize("name,digest,count,unsupported", [
    ("14_chart.hwpx", "bf630bc7c87ed48b267c496059846392125eea59ebe3dccaccda815b53cd4aca", 24,
     {"ofPieChart", "bubbleChart", "stockChart"}),
    ("charts.hwpx", "9e5b3ff8f879ea207681b70f2ccbaf330c942e6cc1e77bf16d83363524792a56", 12,
     {"ofPieChart", "surface3DChart"}),
])
def test_many_chart_real_documents_account_for_every_reference(name, digest, count, unsupported):
    path = public_path(name)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    gold, skipped = [], []
    with zipfile.ZipFile(path) as z:
        section = ET.fromstring(z.read("Contents/section0.xml"))
        references = [n.get("chartIDRef") for n in section.iter('{%s}chart' % HP)]
        assert len(references) == count
        for ref in references:
            raw = z.read(ref)
            plot = ET.fromstring(raw).find("c:chart/c:plotArea", NS)
            kind = next(n.tag.split('}')[-1] for n in plot if n.tag.endswith('Chart'))
            if kind in unsupported:
                skipped.append(ref)
            else:
                gold.extend(xml_gold(raw, kind))
    doc = Dochan(path, include_assets=False).doc
    tables = [t for t in doc.find_all("table") if t.caption_side == "TOP"]
    assert [(t.caption_text, rows(t)[1:]) for t in tables] == gold
    chart_errors = [e for e in doc.errors if '[chart:' in e]
    assert len(chart_errors) == len(skipped)
    for ref in skipped:
        assert any('[chart:unsupported_type]' in e and ref in e for e in chart_errors)
