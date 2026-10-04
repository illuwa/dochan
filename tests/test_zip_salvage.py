"""손상 ZIP 복구는 연속 로컬 항목과 증명된 본문만 허용한다."""
import io
import struct
import zipfile
import zlib

import pytest

from dochan import Dochan
from dochan.batch import batch_convert
from dochan.hwpx.parser import HWPXParser
from dochan.ooxml.package import OOXMLPackage, detect_ooxml_format
from dochan.output.markdown import to_markdown
from dochan.utils import zip_salvage


_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_HWP_HEAD_NS = "http://www.hancom.co.kr/hwpml/2011/head"
_HWP_PARA_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HWP_SECTION_NS = "http://www.hancom.co.kr/hwpml/2011/section"
_WARN_PREFIX = "WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 "
_ERR_PREFIX = "ERR: 손상된 ZIP 문서"


def _local(name, payload=b"body", *, method=0, flags=0, descriptor=None,
           extra=b"", crc=None, declared_size=None, declared_compressed=None):
    """APPNOTE 4.3.7 로컬 헤더를 중앙 디렉터리 없이 직접 조립한다."""
    name_bytes = name.encode("utf-8")
    if method == 8:
        compressor = zlib.compressobj(wbits=-15)
        encoded = compressor.compress(payload) + compressor.flush()
    else:
        encoded = payload
    checksum = zlib.crc32(payload) & 0xffffffff if crc is None else crc
    size = len(payload) if declared_size is None else declared_size
    compressed_size = len(encoded) if declared_compressed is None else declared_compressed
    if descriptor is not None:
        flags |= 8
        head_crc = head_size = head_compressed = 0
    else:
        head_crc, head_size, head_compressed = checksum, size, compressed_size
    header = struct.pack("<IHHHHHIIIHH", 0x04034b50, 20, flags, method,
                         0, 0, head_crc, head_compressed, head_size,
                         len(name_bytes), len(extra))
    tail = b""
    if descriptor is not None:
        tail = (b"PK\x07\x08" if descriptor else b"")
        tail += struct.pack("<III", checksum, compressed_size, size)
    return header + name_bytes + extra + encoded + tail


def _zip(parts):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return output.getvalue()


def _without_directory(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return data[:archive.start_dir]


def _rels(items):
    body = "".join('<Relationship Id="r%d" Type="%s%s" Target="%s"%s/>' %
                   (index, _OFFICE_REL, kind, target,
                    ' TargetMode="External"' if external else "")
                   for index, (kind, target, external) in enumerate(items))
    return '<Relationships xmlns="%s">%s</Relationships>' % (_REL_NS, body)


def _docx_parts(relationships=()):
    result = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/'
                               'package/2006/content-types"/>',
        "_rels/.rels": _rels([("officeDocument", "word/document.xml", False)]),
        "word/document.xml": '<w:document xmlns:w="%s"><w:body><w:p><w:r>'
                             '<w:t>복구 본문</w:t></w:r></w:p></w:body></w:document>' % _WORD_NS,
        "word/_rels/document.xml.rels": _rels(relationships),
    }
    return result


def _hwpx_parts(count=1):
    return {
        "mimetype": "application/hwp+zip",
        "version.xml": '<version/>',
        "Contents/header.xml": '<hh:head xmlns:hh="%s" secCnt="%d"/>' %
                               (_HWP_HEAD_NS, count),
        "Contents/section0.xml": '<hs:sec xmlns:hs="%s" xmlns:hp="%s">'
                                 '<hp:p id="0" paraPrIDRef="0" styleIDRef="0">'
                                 '<hp:run charPrIDRef="0"><hp:t>복구 본문</hp:t>'
                                 '</hp:run></hp:p></hs:sec>' % (_HWP_SECTION_NS, _HWP_PARA_NS),
    }


def _pptx_parts():
    ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
    drawing = "http://schemas.openxmlformats.org/drawingml/2006/main"
    return {
        "[Content_Types].xml": "<Types/>",
        "_rels/.rels": _rels([("officeDocument", "ppt/presentation.xml", False)]),
        "ppt/presentation.xml": '<p:presentation xmlns:p="%s" xmlns:r="%s">'
                                '<p:sldIdLst><p:sldId id="256" r:id="r0"/>'
                                '</p:sldIdLst></p:presentation>' % (ns, _OFFICE_REL[:-1]),
        "ppt/_rels/presentation.xml.rels": _rels([("slide", "slides/slide1.xml", False)]),
        "ppt/slides/slide1.xml": '<p:sld xmlns:p="%s" xmlns:a="%s"><p:cSld><p:spTree>'
                                '<p:sp><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r>'
                                '<a:t>복구 본문</a:t></a:r></a:p></p:txBody></p:sp>'
                                '</p:spTree></p:cSld></p:sld>' % (ns, drawing),
    }


def _xlsx_parts():
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    return {
        "[Content_Types].xml": "<Types/>",
        "_rels/.rels": _rels([("officeDocument", "xl/workbook.xml", False)]),
        "xl/workbook.xml": '<workbook xmlns="%s" xmlns:r="%s"><sheets>'
                           '<sheet name="복구" sheetId="1" r:id="r0"/>'
                           '</sheets></workbook>' % (ns, _OFFICE_REL[:-1]),
        "xl/_rels/workbook.xml.rels": _rels([("worksheet", "worksheets/sheet1.xml", False)]),
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="%s"><sheetData><row r="1">'
                                   '<c r="A1" t="inlineStr"><is><t>복구 본문</t></is></c>'
                                   '</row></sheetData></worksheet>' % ns,
    }


def _recovered_names(data):
    restored = zip_salvage.salvage_zip(data)
    if restored is None:
        return []
    with zipfile.ZipFile(io.BytesIO(restored)) as archive:
        return archive.namelist()


@pytest.mark.parametrize("method", [0, 8])
def test_salvage_preserves_stored_and_deflate_original_bytes(method):
    original = _local("a.xml", b"plain text" * 20, method=method)
    restored = zip_salvage.salvage_zip(original + b"damaged ending")
    assert restored.startswith(original)
    with zipfile.ZipFile(io.BytesIO(restored)) as archive:
        assert archive.namelist() == ["a.xml"]
        assert archive.read("a.xml") == b"plain text" * 20


@pytest.mark.parametrize("signature", [False, True])
def test_salvage_deflate_data_descriptor_finds_exact_next_header(signature):
    first = _local("a.xml", b"inside PK\x03\x04 is not an entry" * 3,
                   method=8, descriptor=signature)
    second = _local("b.xml", b"second")
    restored = zip_salvage.salvage_zip(first + second)
    assert restored.startswith(first + second)
    with zipfile.ZipFile(io.BytesIO(restored)) as archive:
        assert archive.namelist() == ["a.xml", "b.xml"]
        assert archive.read("b.xml") == b"second"


@pytest.mark.parametrize("signature", [False, True])
def test_salvage_rejects_unconfirmed_data_descriptor(signature):
    first = _local("first.xml")
    broken = _local("broken.xml", b"data", method=8, descriptor=signature,
                    declared_size=999)
    assert _recovered_names(first + broken + _local("fake.xml")) == ["first.xml"]


def test_salvage_duplicate_name_keeps_first_and_continues():
    data = _local("a.xml", b"first") + _local("a.xml", b"second") + _local("b.xml")
    restored = zip_salvage.salvage_zip(data)
    with zipfile.ZipFile(io.BytesIO(restored)) as archive:
        assert archive.namelist() == ["a.xml", "b.xml"]
        assert archive.read("a.xml") == b"first"


def test_salvage_duplicate_normalized_name_keeps_first():
    data = _local("word\\a.xml", b"first") + _local("word/a.xml", b"second")
    restored = zip_salvage.salvage_zip(data)
    with zipfile.ZipFile(io.BytesIO(restored)) as archive:
        assert len(archive.namelist()) == 1
        assert archive.read(archive.namelist()[0]) == b"first"


def test_salvage_unknown_size_stored_descriptor_does_not_search_for_signature():
    data = _local("safe.xml") + _local("unknown.xml", b"PK\x07\x08fake", descriptor=True)
    assert _recovered_names(data + _local("later.xml")) == ["safe.xml"]


@pytest.mark.parametrize("rejected", [
    _local("zip64.xml", declared_size=0xffffffff),
    _local("zip64.xml", extra=struct.pack("<HHQQ", 1, 16, 4, 4)),
    _local("encrypted.xml", flags=1),
    _local("unknown.xml", method=99),
    _local("../outside.xml"),
    _local("folder\\..\\outside.xml"),
])
def test_salvage_stops_at_unsupported_or_unsafe_entry(rejected):
    data = _local("safe.xml") + rejected + _local("later.xml")
    assert _recovered_names(data) == ["safe.xml"]


def test_salvage_never_scans_past_non_header_garbage():
    data = _local("safe.xml") + b"garbage" + _local("forged.xml")
    assert _recovered_names(data) == ["safe.xml"]
    assert zip_salvage.salvage_zip(b"garbage" + _local("forged.xml")) is None


def test_salvage_truncated_entry_never_exposes_payload_embedded_header():
    truncated = _local("partial.xml", _local("forged.xml"), declared_compressed=9999)
    assert _recovered_names(_local("safe.xml") + truncated) == ["safe.xml"]


@pytest.mark.parametrize("limit,value,data", [
    ("MAX_INPUT_SIZE", 10, _local("first.xml")),
    ("MAX_ARCHIVE_ENTRIES", 1, _local("first.xml") + _local("second.xml")),
    ("MAX_PART_SIZE", 4, _local("first.xml", b"12345")),
    ("MAX_ARCHIVE_UNCOMPRESSED_SIZE", 6,
     _local("first.xml", b"1234") + _local("second.xml", b"1234")),
    ("MAX_COMPRESSION_RATIO", 2, _local("first.xml", b"a" * 200, method=8)),
])
def test_salvage_honors_all_resource_limits(monkeypatch, limit, value, data):
    monkeypatch.setattr(zip_salvage, limit, value)
    names = _recovered_names(data)
    expected = ["first.xml"] if limit in (
        "MAX_ARCHIVE_ENTRIES", "MAX_ARCHIVE_UNCOMPRESSED_SIZE") else []
    assert names == expected


def test_salvage_descriptor_inflate_is_bounded(monkeypatch):
    monkeypatch.setattr(zip_salvage, "MAX_PART_SIZE", 32)
    data = _local("large.xml", b"a" * 10000, method=8, descriptor=True)
    assert zip_salvage.salvage_zip(data) is None


def test_open_normal_zip_does_not_attempt_salvage(monkeypatch):
    def forbidden(data):
        raise AssertionError("valid ZIP must use the normal path")
    monkeypatch.setattr(zip_salvage, "salvage_zip", forbidden)
    errors = []
    with zip_salvage.open_document_zip(io.BytesIO(_zip(_docx_parts())), errors,
                                       kind="ooxml") as archive:
        assert archive.read("word/document.xml")
    assert errors == []


def test_open_non_zip_keeps_bad_zipfile_diagnostic():
    errors = []
    with pytest.raises(zipfile.BadZipFile):
        zip_salvage.open_document_zip(io.BytesIO(b"not a ZIP"), errors)
    assert errors == []


@pytest.mark.parametrize("kind,parts", [("ooxml", _docx_parts()), ("hwpx", _hwpx_parts())])
def test_open_complete_body_recovers_with_exact_warning(kind, parts):
    errors = []
    with zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                       errors, kind=kind) as archive:
        assert len(archive.namelist()) == len(parts)
    assert errors == [_WARN_PREFIX + str(len(parts)) + "개를 복구함"]


@pytest.mark.parametrize("parts,kind,missing", [
    (_hwpx_parts(2), "hwpx", "Contents/section1.xml"),
    ({"mimetype": "application/hwp+zip", "Contents/section0.xml": "<sec/>"},
     "hwpx", "Contents/header.xml"),
    (_docx_parts([("styles", "styles.xml", False)]), "ooxml", "word/styles.xml"),
    ({"word/document.xml": "<document/>"}, "ooxml", "_rels/.rels"),
])
def test_open_incomplete_body_is_fatal(parts, kind, missing):
    errors = []
    with pytest.raises(zip_salvage.ZipSalvageError) as caught:
        zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                      errors, kind=kind)
    assert str(caught.value).startswith(_ERR_PREFIX + " — 본문 부품 일부가 없음(")
    assert missing in str(caught.value)
    assert any(error.startswith(_WARN_PREFIX) for error in errors)


@pytest.mark.parametrize("relationship", ["styles", "numbering", "footnotes", "endnotes",
                                              "comments", "header", "footer", "chart"])
def test_open_checks_every_required_main_relationship(relationship):
    parts = _docx_parts([(relationship, relationship + ".xml", False)])
    with pytest.raises(zip_salvage.ZipSalvageError, match=relationship):
        zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                      [], kind="ooxml")


def test_open_checks_recursive_relationships_and_ignores_external_targets():
    parts = _docx_parts([("header", "header1.xml", False),
                         ("hyperlink", "https://example.invalid/", True)])
    parts["word/header1.xml"] = '<w:hdr xmlns:w="%s"/>' % _WORD_NS
    parts["word/_rels/header1.xml.rels"] = _rels([("chart", "charts/chart1.xml", False)])
    with pytest.raises(zip_salvage.ZipSalvageError, match="word/charts/chart1.xml"):
        zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                      [], kind="ooxml")


def test_open_requires_leaf_relationships_when_xml_references_relationship_ids():
    parts = _pptx_parts()
    parts["ppt/slides/slide1.xml"] = (
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="%s"><p:cSld><p:spTree><p:pic r:embed="rImage"/>'
        '</p:spTree></p:cSld></p:sld>' % _OFFICE_REL[:-1])
    with pytest.raises(zip_salvage.ZipSalvageError, match="slide1.xml.rels"):
        zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                      [], kind="ooxml")


def test_open_known_main_name_does_not_replace_missing_root_office_relationship():
    parts = _docx_parts()
    parts["_rels/.rels"] = _rels([])
    with pytest.raises(zip_salvage.ZipSalvageError, match=_ERR_PREFIX):
        zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                      [], kind="ooxml")


def test_open_relationship_cycles_terminate_without_missing_parts():
    parts = _docx_parts([("header", "header1.xml", False)])
    parts["word/header1.xml"] = '<w:hdr xmlns:w="%s"/>' % _WORD_NS
    parts["word/_rels/header1.xml.rels"] = _rels([("header", "document.xml", False)])
    with zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                       [], kind="ooxml") as archive:
        assert archive.read("word/document.xml")


def test_open_root_document_properties_are_optional():
    parts = _docx_parts()
    parts["_rels/.rels"] = _rels([
        ("officeDocument", "word/document.xml", False),
        ("extended-properties", "docProps/app.xml", False),
    ])
    errors = []
    with zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                       errors, kind="ooxml") as archive:
        assert archive.read("word/document.xml")
    assert not any(error.startswith("ERR:") for error in errors)


@pytest.mark.parametrize("kind,target", [
    ("image", "media/image1.png"), ("audio", "media/audio1.wav"),
    ("video", "media/video1.mp4"), ("oleObject", "embeddings/object1.bin"),
])
def test_open_missing_asset_does_not_disqualify_complete_body(kind, target):
    parts = _docx_parts([(kind, target, False)])
    errors = []
    with zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                       errors, kind="ooxml") as archive:
        assert archive.read("word/document.xml")
    assert errors and not any(error.startswith("ERR:") for error in errors)


@pytest.mark.parametrize("kind,parts,body", [
    ("ooxml", _docx_parts(), "word/document.xml"),
    ("ooxml", _docx_parts(), "_rels/.rels"),
    ("ooxml", _docx_parts(), "word/_rels/document.xml.rels"),
    ("hwpx", _hwpx_parts(), "Contents/section0.xml"),
    ("hwpx", _hwpx_parts(), "Contents/header.xml"),
])
def test_open_corrupt_body_crc_prevents_success(kind, parts, body):
    data = b"".join(_local(name, value.encode("utf-8"), crc=0 if name == body else None)
                    for name, value in parts.items())
    with pytest.raises(zip_salvage.ZipSalvageError, match=_ERR_PREFIX):
        zip_salvage.open_document_zip(io.BytesIO(data), [], kind=kind)


def test_open_no_recoverable_entries_has_specific_error_and_warning():
    errors = []
    with pytest.raises(zip_salvage.ZipSalvageError) as caught:
        zip_salvage.open_document_zip(io.BytesIO(b"PK\x03\x04short"), errors, kind="ooxml")
    assert str(caught.value) == _ERR_PREFIX + " — 중앙 디렉터리가 없고 본문 부품을 찾지 못함"
    assert errors == [_WARN_PREFIX + "0개를 복구함"]


@pytest.mark.parametrize("parts,missing", [
    (_pptx_parts(), "ppt/slides/slide1.xml"),
    (_xlsx_parts(), "xl/worksheets/sheet1.xml"),
])
def test_open_pptx_slide_and_xlsx_worksheet_are_required(parts, missing):
    parts = dict(parts)
    del parts[missing]
    with pytest.raises(zip_salvage.ZipSalvageError, match=missing):
        zip_salvage.open_document_zip(io.BytesIO(_without_directory(_zip(parts))),
                                      [], kind="ooxml")


@pytest.mark.parametrize("extension,parts", [
    ("docx", _docx_parts()), ("pptx", _pptx_parts()),
    ("xlsx", _xlsx_parts()), ("hwpx", _hwpx_parts()),
])
def test_recovered_four_formats_match_intact_markdown(tmp_path, extension, parts):
    intact = tmp_path / ("intact." + extension)
    recovered = tmp_path / ("recovered." + extension)
    original = _zip(parts)
    intact.write_bytes(original)
    recovered.write_bytes(_without_directory(original))
    expected = Dochan(str(intact))
    actual = Dochan(str(recovered))
    assert "복구 본문" in expected.to_markdown()
    assert actual.to_markdown() == expected.to_markdown()
    assert any(error.startswith(_WARN_PREFIX) for error in actual.errors)
    assert not any(error.startswith("ERR:") for error in actual.errors)


def test_direct_ooxml_package_and_detection_use_recovered_buffer(tmp_path):
    source = tmp_path / "renamed.hwp"
    source.write_bytes(_without_directory(_zip(_docx_parts())))
    assert detect_ooxml_format(str(source)) == "docx"
    with OOXMLPackage(io.BytesIO(source.read_bytes())) as package:
        assert package.read_xml_part("word/document.xml").tag.endswith("document")


def test_direct_hwpx_parser_emits_complete_body_and_warning():
    document = HWPXParser().parse(io.BytesIO(_without_directory(_zip(_hwpx_parts()))))
    assert to_markdown(document) == "복구 본문"
    assert any(error.startswith(_WARN_PREFIX) for error in document.errors)
    assert not any(error.startswith("ERR:") for error in document.errors)


@pytest.mark.parametrize("extension,parts,expected", [
    ("hwp", _hwpx_parts(), "hwpx"), ("hwpx", _docx_parts(), "docx"),
])
def test_dochan_uses_content_detection_even_for_wrong_extension(tmp_path, extension, parts, expected):
    source = tmp_path / ("renamed." + extension)
    source.write_bytes(_without_directory(_zip(parts)))
    document = Dochan(str(source))
    assert document.metadata["source_format"] == expected
    assert document.to_markdown() == "복구 본문"
    assert any(error.startswith(_WARN_PREFIX) for error in document.errors)
    assert not any(error.startswith("ERR:") for error in document.errors)


@pytest.mark.parametrize("extension,parts", [
    ("hwpx", _hwpx_parts(2)),
    ("docx", _docx_parts([("footnotes", "footnotes.xml", False)])),
])
def test_dochan_incomplete_recovery_discards_partial_body(tmp_path, extension, parts):
    source = tmp_path / ("incomplete." + extension)
    source.write_bytes(_without_directory(_zip(parts)))
    document = Dochan(str(source))
    assert document.to_markdown() == ""
    assert any(error.startswith(_ERR_PREFIX) for error in document.errors)
    assert any(error.startswith(_WARN_PREFIX) for error in document.errors)


@pytest.mark.parametrize("workers", [1, 2])
def test_batch_publishes_complete_recovery_and_rejects_incomplete(tmp_path, workers):
    source = tmp_path / "input"
    output = tmp_path / "output"
    source.mkdir()
    (source / "complete.hwpx").write_bytes(_without_directory(_zip(_hwpx_parts())))
    (source / "incomplete.docx").write_bytes(_without_directory(_zip(
        _docx_parts([("styles", "styles.xml", False)]))))
    summary = batch_convert(str(source), str(output), max_workers=workers)
    assert summary.total == 2
    assert summary.success == 1
    assert summary.failed == 1
    assert (output / "complete.md").read_text(encoding="utf-8") == "복구 본문"
    assert not (output / "incomplete.md").exists()
    results = {result.file_path.rsplit("/", 1)[-1]: result for result in summary.results}
    assert any(error.startswith(_WARN_PREFIX) for error in results["complete.hwpx"].errors)
    assert any(error.startswith(_ERR_PREFIX) for error in results["incomplete.docx"].errors)
