"""Strict 문법을 직접 조립해 기존 OOXML 출력 계약과 비교한다."""
import zipfile

from dochan.utils import safe_xml as etree
import pytest

from dochan.ooxml.docx import DOCXReader
from dochan.ooxml.pptx import PPTXReader
from dochan.ooxml.xlsx import XLSXReader
from dochan.ooxml.package import OOXMLPackage
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown


STRICT = "http://purl.oclc.org/ooxml/"
TRANS = "http://schemas.openxmlformats.org/"
REL = TRANS + "package/2006/relationships"
MC = TRANS + "markup-compatibility/2006"
NAMESPACES = {
    "w": ("wordprocessingml/main", "wordprocessingml/2006/main"),
    "s": ("spreadsheetml/main", "spreadsheetml/2006/main"),
    "p": ("presentationml/main", "presentationml/2006/main"),
    "a": ("drawingml/main", "drawingml/2006/main"),
    "c": ("drawingml/chart", "drawingml/2006/chart"),
    "cdr": ("drawingml/chartDrawing", "drawingml/2006/chartDrawing"),
    "dgm": ("drawingml/diagram", "drawingml/2006/diagram"),
    "lc": ("drawingml/lockedCanvas", "drawingml/2006/lockedCanvas"),
    "pic": ("drawingml/picture", "drawingml/2006/picture"),
    "xdr": ("drawingml/spreadsheetDrawing", "drawingml/2006/spreadsheetDrawing"),
    "wp": ("drawingml/wordprocessingDrawing", "drawingml/2006/wordprocessingDrawing"),
    "m": ("officeDocument/math", "officeDocument/2006/math"),
    "r": ("officeDocument/relationships", "officeDocument/2006/relationships"),
    "ep": ("officeDocument/extendedProperties", "officeDocument/2006/extended-properties"),
    "cp": ("officeDocument/customProperties", "officeDocument/2006/custom-properties"),
    "vt": ("officeDocument/docPropsVTypes", "officeDocument/2006/docPropsVTypes"),
    "ds": ("officeDocument/customXml", "officeDocument/2006/customXml"),
    "b": ("officeDocument/bibliography", "officeDocument/2006/bibliography"),
}


def _xml(body, strict=True):
    declarations = " ".join('xmlns:%s="%s"' % (prefix, (STRICT + pair[0])
        if strict else (TRANS + pair[1])) for prefix, pair in NAMESPACES.items())
    return body.replace(" NS", " " + declarations + ' xmlns:mc="' + MC + '"')


def _zip(path, parts):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return str(path)


def _rels(*items, strict=True):
    prefix = STRICT + "officeDocument/relationships/" if strict else TRANS + "officeDocument/2006/relationships/"
    return '<Relationships xmlns="%s">%s</Relationships>' % (REL, "".join(
        '<Relationship Id="%s" Type="%s%s" Target="%s"%s/>' %
        (rid, prefix, kind, target, ' TargetMode="External"' if target.startswith("https:") else "")
        for rid, kind, target in items))


@pytest.mark.parametrize("prefix", list(NAMESPACES))
def test_strict_namespace_qnames_and_bindings(tmp_path, prefix):
    strict, transitional = NAMESPACES[prefix]
    source = '<x:root xmlns:x="%s" x:attr="value"><!-- comment --><x:child/>tail</x:root>' % (STRICT + strict)
    path = _zip(tmp_path / "sample.zip", {"part.xml": source})
    with OOXMLPackage(path) as package:
        root = package.read_xml_part("part.xml")
        assert package.read_part("part.xml") == source.encode()
    assert root.tag == "{%s}root" % (TRANS + transitional)
    assert root.get("{%s}attr" % (TRANS + transitional)) == "value"
    assert etree.namespace_map(root)["x"] == TRANS + transitional
    assert root[0].text == " comment "
    assert root[1].tail == "tail"


def test_strict_uris_only_change_structural_fields(tmp_path):
    target = STRICT + "officeDocument/relationships/image"
    text = STRICT + "drawingml/chart"
    parts = {"part.xml": _xml('<w:document NS><w:body><w:p><w:r><w:t>' + text +
        '</w:t></w:r></w:p><a:graphicData uri="' + text + '"/>' +
        '<custom xmlns="urn:custom" uri="' + text + '" Type="' + target + '"/>' +
        '</w:body></w:document>'),
        "_rels/.rels": _rels(("r1", "hyperlink", "https://example.com/" + target))}
    path = _zip(tmp_path / "sample.zip", parts)
    with OOXMLPackage(path) as package:
        root = package.read_xml_part("part.xml")
        rel = package.read_xml_part("_rels/.rels")[0]
    assert rel.get("Type") == TRANS + "officeDocument/2006/relationships/hyperlink"
    assert rel.get("Target") == "https://example.com/" + target
    assert root.find(".//{%s}t" % (TRANS + NAMESPACES["w"][1])).text == text
    assert root.find(".//{%s}graphicData" % (TRANS + NAMESPACES["a"][1])).get("uri") == TRANS + NAMESPACES["c"][1]
    custom = root.find(".//{urn:custom}custom")
    assert custom.get("uri") == text and custom.get("Type") == target


def test_strict_docx_output_matches_transitional(tmp_path):
    docs = []
    for strict in (False, True):
        parts = {
            "word/document.xml": _xml('''<w:document NS><w:body>
              <w:p><w:r><w:rPr><w:b/><w:i/></w:rPr><w:t>본문</w:t></w:r>
                <w:hyperlink r:id="link"><w:r><w:t>링크</w:t></w:r></w:hyperlink>
                <w:r><w:footnoteReference w:id="1"/></w:r></w:p>
              <w:tbl><w:tr><w:tc><w:p><w:r><w:t>표</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
              <w:p><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></w:p>
              <w:sectPr><w:headerReference w:type="default" r:id="header"/></w:sectPr>
            </w:body></w:document>''', strict),
            "word/footnotes.xml": _xml('<w:footnotes NS><w:footnote w:id="1"><w:p><w:r><w:t>각주</w:t></w:r></w:p></w:footnote></w:footnotes>', strict),
            "word/header1.xml": _xml('<w:hdr NS><w:p><w:r><w:t>머리말</w:t></w:r></w:p></w:hdr>', strict),
            "word/_rels/document.xml.rels": _rels(("link", "hyperlink", "https://example.com"),
                ("header", "header", "header1.xml"), ("note", "footnotes", "footnotes.xml"), strict=strict),
        }
        docs.append(DOCXReader().read(_zip(tmp_path / (str(strict) + ".docx"), parts)))
    assert not docs[0].errors and not docs[1].errors
    assert "본문" in to_markdown(docs[0]) and "머리말" in to_markdown(docs[0])
    assert to_dict(docs[1]) == to_dict(docs[0])
    assert to_markdown(docs[1]) == to_markdown(docs[0])


def test_strict_pptx_alternate_content_and_notes_match(tmp_path):
    docs = []
    for strict in (False, True):
        parts = {
            "ppt/presentation.xml": _xml('<p:presentation NS><p:sldIdLst><p:sldId id="256" r:id="s1"/></p:sldIdLst></p:presentation>', strict),
            "ppt/_rels/presentation.xml.rels": _rels(("s1", "slide", "slides/slide1.xml"), strict=strict),
            "ppt/slides/slide1.xml": _xml('''<p:sld NS><p:cSld><p:spTree>
              <mc:AlternateContent><mc:Choice Requires="a"><p:sp><p:txBody><a:p>
                <a:r><a:rPr b="1" i="1"><a:hlinkClick r:id="link"/></a:rPr><a:t>슬라이드</a:t></a:r>
              </a:p></p:txBody></p:sp></mc:Choice><mc:Fallback><p:sp><p:txBody><a:p><a:r><a:t>잘못된 대체</a:t></a:r></a:p></p:txBody></p:sp></mc:Fallback></mc:AlternateContent>
            </p:spTree></p:cSld></p:sld>''', strict),
            "ppt/slides/_rels/slide1.xml.rels": _rels(("link", "hyperlink", "https://example.com"), ("notes", "notesSlide", "../notesSlides/notesSlide1.xml"), strict=strict),
            "ppt/notesSlides/notesSlide1.xml": _xml('<p:notes NS><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>발표자 노트</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:notes>', strict),
        }
        docs.append(PPTXReader().read(_zip(tmp_path / (str(strict) + ".pptx"), parts)))
    assert not docs[0].errors and not docs[1].errors
    assert "슬라이드" in to_markdown(docs[0]) and "발표자 노트" in to_markdown(docs[0])
    assert "잘못된 대체" not in to_markdown(docs[1])
    assert to_dict(docs[1]) == to_dict(docs[0])


def _xlsx(path, cells, strict=True, date1904=False):
    return _zip(path, {
        "xl/workbook.xml": _xml('<s:workbook NS><s:workbookPr date1904="%s"/><s:sheets><s:sheet name="시트" sheetId="1" r:id="s1"/></s:sheets></s:workbook>' % int(date1904), strict),
        "xl/_rels/workbook.xml.rels": _rels(("s1", "worksheet", "worksheets/sheet1.xml"), strict=strict),
        "xl/worksheets/sheet1.xml": _xml('<s:worksheet NS><s:sheetData><s:row r="1">' + cells + '</s:row></s:sheetData></s:worksheet>', strict),
        "xl/styles.xml": _xml('<s:styleSheet NS><s:cellXfs><s:xf numFmtId="0"/><s:xf numFmtId="14"/><s:xf numFmtId="21"/></s:cellXfs></s:styleSheet>', strict),
    })


@pytest.mark.parametrize("streamed", [False, True])
@pytest.mark.parametrize("date1904", [False, True])
def test_strict_xlsx_iso_dates_match_existing_date_time_contract(tmp_path, monkeypatch, streamed, date1904):
    if streamed:
        monkeypatch.setattr("dochan.ooxml.xlsx.MAX_XML_PART_SIZE", 1)
    path = _xlsx(tmp_path / "dates.xlsx", '''
      <s:c r="A1" t="d" s="1"><s:v>1990-01-01T12:30:45Z</s:v></s:c>
      <s:c r="B1" t="d" s="2"><s:v>1990-01-01T12:30:45+09:00</s:v></s:c>
      <s:c r="C1" t="d"><s:v>1990-01-01T12:30:45Z</s:v></s:c>
      <s:c r="D1" t="d" s="1"><s:f>DATE(1990,1,1)</s:f><s:v>1990-01-01</s:v></s:c>
    ''', date1904=date1904)
    doc = XLSXReader().read(path)
    cells = doc.find_all("table")[0].rows[0]
    assert [cell.text for cell in cells] == ["1990-01-01", "12:30:45", "1990-01-01T12:30:45Z", "1990-01-01 (=DATE(1990,1,1))"]


def test_strict_invalid_iso_date_warns_without_losing_other_cells(tmp_path):
    path = _xlsx(tmp_path / "dates.xlsx", '<s:c r="A1" t="d" s="1"><s:v>1990-02-31</s:v></s:c><s:c r="B1"><s:v>42</s:v></s:c>')
    doc = XLSXReader().read(path)
    assert [cell.text for cell in doc.find_all("table")[0].rows[0]] == ["1990-02-31", "42"]
    assert any("WARN:" in error and "ISO date" in error for error in doc.errors)


def test_strict_parser_recovery_and_utf16(tmp_path):
    xml = _xml('<w:document NS><w:body><w:p><w:r><w:t>UTF16</w:t></w:r></w:p></w:body></w:document>')
    path = _zip(tmp_path / "encoded.docx", {"word/document.xml": xml.encode("utf-16"), "broken.xml": xml[:-13]})
    with OOXMLPackage(path) as package:
        assert package.read_xml_part("word/document.xml").tag == "{%s}document" % (TRANS + NAMESPACES["w"][1])
        assert package.read_xml_part("broken.xml", recover=True).tag == "{%s}document" % (TRANS + NAMESPACES["w"][1])


@pytest.mark.parametrize("fraction", ["9", "90", "900", "900000", "9000000"])
@pytest.mark.parametrize("time,expected", [("12:30:45", "12:30:46"), ("23:59:59", "00:00:00")])
def test_strict_iso_fractional_seconds_use_numeric_time_rounding(tmp_path, fraction, time, expected):
    value = "1990-01-01T" + time + "." + fraction + "Z"
    path = _xlsx(tmp_path / "fractions.xlsx", '<s:c r="A1" t="d" s="2"><s:v>' + value + '</s:v></s:c>')
    doc = XLSXReader().read(path)
    assert not doc.errors
    assert doc.find_all("table")[0].rows[0][0].text == expected


@pytest.mark.parametrize("suffix,target", [
    ("metadata/thumbnail", "package/2006/relationships/metadata/thumbnail"),
    ("extendedProperties", "officeDocument/2006/relationships/extended-properties"),
    ("customProperties", "officeDocument/2006/relationships/custom-properties"),
    ("image", "officeDocument/2006/relationships/image"),
])
def test_strict_relationship_type_exceptions(tmp_path, suffix, target):
    path = _zip(tmp_path / "relations.zip", {"_rels/.rels": _rels(("id", suffix, "part.xml"))})
    with OOXMLPackage(path) as package:
        assert package.read_xml_part("_rels/.rels")[0].get("Type") == TRANS + target


def test_strict_nested_namespace_rebinding_and_unknown_extension(tmp_path):
    source = '''<root xmlns:q="urn:unknown"><child xmlns:q="%s">
      <mc:Choice xmlns:mc="%s" Requires="q"><q:t>chosen</q:t></mc:Choice>
      <q:graphicData uri="%s"/>
      <extension xmlns="%s/extension" flag="25%%">unknown</extension>
    </child><q:t>outside</q:t></root>''' % (
        STRICT + NAMESPACES["a"][0], MC, STRICT + NAMESPACES["c"][0], STRICT + NAMESPACES["a"][0])
    path = _zip(tmp_path / "nested.zip", {"part.xml": source})
    with OOXMLPackage(path) as package:
        root = package.read_xml_part("part.xml")
    assert etree.namespace_map(root)["q"] == "urn:unknown"
    assert etree.namespace_map(root[0][0])["q"] == TRANS + NAMESPACES["a"][1]
    assert root[0][0].get("Requires") == "q"
    assert root[0][2].tag == "{%s/extension}extension" % (STRICT + NAMESPACES["a"][0])
    assert root[0][2].get("flag") == "25%"
    assert root[1].tag == "{urn:unknown}t"


def test_strict_deep_tree_and_existing_limits(tmp_path, monkeypatch):
    xml = '<w:document xmlns:w="%s">%svalue%s</w:document>' % (
        STRICT + NAMESPACES["w"][0], "<w:p>" * 350, "</w:p>" * 350)
    path = _zip(tmp_path / "deep.zip", {"part.xml": xml})
    with OOXMLPackage(path) as package:
        root = package.read_xml_part("part.xml")
        assert len(list(root.iter())) == 351
        assert all(node.tag.startswith("{" + TRANS) for node in root.iter())
        monkeypatch.setattr("dochan.ooxml.package.MAX_XML_ELEMENTS", 20)
        with pytest.raises(ValueError, match="element limit"):
            package.read_xml_part("part.xml")


def test_strict_xxe_remains_disabled(tmp_path):
    source = '<!DOCTYPE doc [<!ENTITY leak SYSTEM "file:///etc/passwd">]>' + _xml(
        '<w:document NS><w:body><w:p><w:r><w:t>safe &leak; &amp;</w:t></w:r></w:p></w:body></w:document>')
    path = _zip(tmp_path / "xxe.docx", {"word/document.xml": source})
    doc = DOCXReader().read(path)
    assert not doc.errors
    assert to_markdown(doc).strip() == "safe  &"


@pytest.mark.parametrize("streamed", [False, True])
def test_transitional_iso_date_output_is_unchanged(tmp_path, monkeypatch, streamed):
    if streamed:
        monkeypatch.setattr("dochan.ooxml.xlsx.MAX_XML_PART_SIZE", 1)
    value = "1990-01-01T12:30:45Z"
    path = _xlsx(tmp_path / "transitional.xlsx", '<s:c r="A1" t="d" s="1"><s:v>' + value + '</s:v></s:c>', strict=False)
    doc = XLSXReader().read(path)
    assert doc.find_all("table")[0].rows[0][0].text == value


def test_strict_namespace_work_budget(tmp_path, monkeypatch):
    xml = _xml('<w:document NS>' +
        '<w:p xmlns:a="urn:1" xmlns:b="urn:2" xmlns:c="urn:3"/>' * 30 + '</w:document>')
    path = _zip(tmp_path / "bounded.zip", {"part.xml": xml})
    monkeypatch.setattr("dochan.ooxml.package.MAX_XML_NAMESPACE_BINDINGS", 100, raising=False)
    with OOXMLPackage(path) as package:
        with pytest.raises(ValueError, match="namespace limit"):
            package.read_xml_part("part.xml")


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_strict_namespace_character_references_are_normalized(tmp_path, encoding):
    source = '<root><w:document xmlns:w="http://purl.oclc.org/ooxm&#108;/wordprocessingml/main"><w:body/></w:document></root>'
    path = _zip(tmp_path / 'reference.zip', {'part.xml': source.encode(encoding)})
    with OOXMLPackage(path) as package:
        root = package.read_xml_part('part.xml')
    assert root[0].tag == '{%s}document' % (TRANS + NAMESPACES['w'][1])


def test_strict_docx_chart_and_image_reuse_output_contract(tmp_path):
    docs = []
    for strict in (False, True):
        parts = {
            "word/document.xml": _xml('''<w:document NS><w:body><w:p><w:r><w:drawing>
              <wp:inline><wp:docPr id="1" name="Picture" descr="설명"/>
                <a:graphic><a:graphicData><pic:pic><pic:blipFill><a:blip r:embed="image"/>
                </pic:blipFill></pic:pic></a:graphicData></a:graphic>
              </wp:inline></w:drawing></w:r></w:p>
              <w:p><w:r><w:drawing><a:graphic><a:graphicData><c:chart r:id="chart"/>
              </a:graphicData></a:graphic></w:drawing></w:r></w:p></w:body></w:document>''', strict),
            "word/_rels/document.xml.rels": _rels(("image", "image", "media/pixel.png"),
                ("chart", "chart", "charts/chart1.xml"), strict=strict),
            "word/media/pixel.png": b"\x89PNG\r\n\x1a\n",
            "word/charts/chart1.xml": _xml('''<c:chartSpace NS><c:chart><c:plotArea><c:barChart><c:ser>
              <c:tx><c:v>Series</c:v></c:tx><c:cat><c:strLit><c:pt idx="0"><c:v>A</c:v></c:pt></c:strLit></c:cat>
              <c:val><c:numLit><c:pt idx="0"><c:v>42</c:v></c:pt></c:numLit></c:val>
              </c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>''', strict),
        }
        docs.append(DOCXReader().read(_zip(tmp_path / (str(strict) + ".docx"), parts)))
    assert not docs[0].errors and not docs[1].errors
    assert "42" in to_markdown(docs[0]) and "pixel.png" in to_markdown(docs[0])
    assert to_dict(docs[0]) == to_dict(docs[1])
    assert to_markdown(docs[0]) == to_markdown(docs[1])


def test_strict_unconsumed_visual_units_are_preserved(tmp_path):
    source = _xml('''<w:document NS><w:body><w:p><w:r><w:t>본문</w:t></w:r></w:p>
      <w:sectPr><w:pgSz w:w="612pt" w:h="792pt"/></w:sectPr></w:body>
      <a:gs pos="50%"><a:schemeClr val="accent1"><a:tint val="67%"/></a:schemeClr></a:gs>
      <a:xfrm rot="5400000"/></w:document>''')
    path = _zip(tmp_path / "units.docx", {"word/document.xml": source})
    with OOXMLPackage(path) as package:
        root = package.read_xml_part("word/document.xml")
    assert root.find(".//{%s}pgSz" % (TRANS + NAMESPACES["w"][1])).get("{%s}w" % (TRANS + NAMESPACES["w"][1])) == "612pt"
    assert root.find(".//{%s}gs" % (TRANS + NAMESPACES["a"][1])).get("pos") == "50%"
    assert root.find(".//{%s}xfrm" % (TRANS + NAMESPACES["a"][1])).get("rot") == "5400000"
    doc = DOCXReader().read(path)
    assert not doc.errors and to_markdown(doc) == "본문"


@pytest.mark.parametrize("strict", [False, True])
def test_strict_utf16_unresolved_entities_do_not_crash_or_expand(tmp_path, strict):
    source = '<!DOCTYPE doc [<!ENTITY opaque "MUST_NOT_EXPAND">]>' + _xml(
        '<w:document NS><w:body><w:p><w:r><w:t>safe</w:t></w:r>&opaque;</w:p></w:body></w:document>', strict)
    path = _zip(tmp_path / "entities.docx", {"word/document.xml": source.encode("utf-16")})
    with OOXMLPackage(path) as package:
        root = package.read_xml_part("word/document.xml")
        assert "MUST_NOT_EXPAND" not in etree.tostring(root).decode()
    doc = DOCXReader().read(path)
    assert not doc.errors
    assert to_markdown(doc) == "safe"
