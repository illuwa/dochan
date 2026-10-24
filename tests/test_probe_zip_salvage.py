"""복구 결과를 보지 않는 원본 절단 표본 적격성 검사."""
import io
import struct
import zipfile

from scripts.probe_zip_salvage import discover_public, original_admissibility


REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"


def _archive(parts):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in parts.items():
            archive.writestr(name, payload)
    return target.getvalue()


def _docx(extra=None):
    parts = {
        "_rels/.rels": '<Relationships xmlns="%s"><Relationship Id="r1" '
        'Type="%sofficeDocument" Target="word/document.xml"/></Relationships>'
        % (REL_NS, OFFICE),
        "word/document.xml": "<document><body>body</body></document>",
    }
    parts.update(extra or {})
    return _archive(parts)


def test_original_minimal_docx_without_main_relationships_stays_eligible():
    result = original_admissibility(_docx(), "docx")
    assert result["eligible"]
    assert result["missing_main_relationships"]


def test_original_embedded_zip_is_eligible():
    data = _docx({"word/embeddings/inside.zip": _archive({"inside.xml": "<a/>"})})
    assert original_admissibility(data, "docx")["eligible"]


def test_original_missing_internal_relationship_target_is_excluded():
    relationships = ('<Relationships xmlns="%s"><Relationship Id="r1" '
                     'Type="%sfooter" Target="footer.xml"/></Relationships>') % (REL_NS, OFFICE)
    result = original_admissibility(_docx({"word/_rels/document.xml.rels": relationships}), "docx")
    assert result["reasons"] == ["missing_internal_target"]


def test_original_local_version_disagrees_with_central_is_excluded():
    data = bytearray(_docx())
    struct.pack_into("<H", data, 4, 788)
    assert original_admissibility(bytes(data), "docx")["reasons"] == ["unsupported_local_version"]


def test_original_crc_corruption_is_excluded():
    data = bytearray(_docx())
    struct.pack_into("<I", data, 14, 123)
    assert original_admissibility(bytes(data), "docx")["reasons"] == ["local_metadata_mismatch"]


def test_original_invalid_relationship_xml_is_excluded():
    data = _docx({"word/_rels/document.xml.rels": "CORRUPTED"})
    assert original_admissibility(data, "docx")["reasons"] == ["invalid_relationship_xml"]


def test_original_hwpx_section_count_mismatch_is_excluded():
    data = _archive({"mimetype": "application/hwp+zip",
                     "Contents/header.xml": '<head secCnt="1"/>',
                     "Contents/section0.xml": "<sec/>",
                     "Contents/section1.xml": "<sec/>"})
    assert original_admissibility(data, "hwpx")["reasons"] == ["hwpx_section_count_mismatch"]


def test_inventory_does_not_open_third_party_source_code(tmp_path, monkeypatch):
    from pathlib import Path

    corpus = tmp_path / 'corpus'
    public = corpus / 'lo-src'
    public.mkdir(parents=True)
    source = public / 'implementation.cxx'
    source.write_bytes(b'never read')
    (public / 'sample.docx').write_bytes(_docx())
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path != source, 'inventory must not read implementation files'
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded_open)
    assert discover_public(corpus, roots=('lo-src',)) == ['lo-src/sample.docx']
