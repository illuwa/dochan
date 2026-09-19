"""HWPX asset loading is optional; image references remain part of the document."""

import zipfile
from dataclasses import asdict
from inspect import signature

import pytest

from dochan import Dochan
from dochan.conversion import ConversionOptions
from dochan.hwpx.parser import HWPXParser

_NS = (
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'
)
_ASSETS = {
    "BinData/photo.png": b"\x89PNG\r\n\x1a\nasset-one",
    "BinData/nested.jpg": b"\xff\xd8\xffasset-two",
}


def _paragraph(body):
    return f"<hp:p><hp:run>{body}</hp:run></hp:p>"


def _picture(reference, caption):
    return (
        f'<hp:pic><hc:img binaryItemIDRef="{reference}"/>'
        f'<hp:shapeComment>{caption} 설명</hp:shapeComment>'
        '<hp:caption side="BOTTOM"><hp:subList>'
        + _paragraph(f"<hp:t>{caption}</hp:t>")
        + '</hp:subList></hp:caption></hp:pic>'
    )


@pytest.fixture
def hwpx_path(tmp_path):
    path = tmp_path / "images.hwpx"
    body = _paragraph('<hp:t>본문</hp:t>' + _picture("mapped-image", "그림 1"))
    body += _paragraph(
        '<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
        '<hp:cellAddr rowAddr="0" colAddr="0"/><hp:subList>'
        + _paragraph(_picture("nested", "표 안 그림"))
        + '</hp:subList></hp:tc></hp:tr></hp:tbl>'
    )
    body += _paragraph(
        '<hp:ctrl><hp:header><hp:subList>'
        + _paragraph(_picture("mapped-image", "머리글 그림"))
        + '</hp:subList></hp:header></hp:ctrl>'
    )
    body += _paragraph(_picture("missing-image", "누락된 그림"))
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", f'<hs:sec {_NS}>{body}</hs:sec>')
        archive.writestr(
            "Contents/content.hpf",
            '<package><manifest>'
            '<item id="s0" href="section0.xml"/>'
            '<item id="mapped-image" href="BinData/photo.png"/>'
            '</manifest></package>',
        )
        for name, data in _ASSETS.items():
            archive.writestr(name, data)
        archive.writestr("BinData/unused.png", b"unused asset")
    return path


@pytest.fixture(params=["reader", "parser"])
def read_document(request):
    if request.param == "reader":
        return lambda path, **kwargs: Dochan(path, **kwargs).doc
    return HWPXParser().parse


@pytest.fixture
def bin_accesses(monkeypatch):
    accesses = {"read": [], "open": []}
    original_read = zipfile.ZipFile.read
    original_open = zipfile.ZipFile.open

    def track_read(archive, name, *args, **kwargs):
        filename = name.filename if isinstance(name, zipfile.ZipInfo) else name
        if filename.startswith("BinData/"):
            accesses["read"].append(filename)
        return original_read(archive, name, *args, **kwargs)

    def track_open(archive, name, *args, **kwargs):
        filename = name.filename if isinstance(name, zipfile.ZipInfo) else name
        if filename.startswith("BinData/"):
            accesses["open"].append(filename)
        return original_open(archive, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "read", track_read)
    monkeypatch.setattr(zipfile.ZipFile, "open", track_open)
    return accesses


@pytest.mark.parametrize("kwargs", [{}, {"include_assets": True}])
def test_default_and_explicit_true_load_assets(hwpx_path, read_document, bin_accesses, kwargs):
    document = read_document(hwpx_path, **kwargs)

    assert document.errors == []
    images = document.find_all("image")
    assert [image.filename for image in images] == [
        "BinData/photo.png", "BinData/nested.jpg", "BinData/photo.png", "missing-image",
    ]
    assert [image.image_data for image in images] == [
        _ASSETS["BinData/photo.png"], _ASSETS["BinData/nested.jpg"],
        _ASSETS["BinData/photo.png"], b"",
    ]
    # A shared image is read once; unreferenced BinData is never loaded.
    assert bin_accesses == {"read": list(_ASSETS), "open": list(_ASSETS)}


def test_false_preserves_document_and_never_reads_bindata(hwpx_path, read_document, bin_accesses):
    expected = read_document(hwpx_path)
    assert expected.errors == []
    for image in expected.find_all("image"):
        image.image_data = b""
    for accesses in bin_accesses.values():
        accesses.clear()

    document = read_document(hwpx_path, include_assets=False)

    assert bin_accesses == {"read": [], "open": []}
    assert document == expected
    images = document.find_all("image")
    assert [image.caption_text for image in images] == [
        "그림 1", "표 안 그림", "머리글 그림", "누락된 그림",
    ]
    assert all(image.caption_side == "BOTTOM" for image in images)
    assert all(image.alt_text == image.caption_text + " 설명" for image in images)
    assert all(not image.has_data for image in images)


def test_parser_option_is_per_call(hwpx_path):
    parser = HWPXParser()
    skipped = parser.parse(hwpx_path, include_assets=False)
    loaded = parser.parse(hwpx_path)
    skipped_again = parser.parse(hwpx_path, include_assets=False)

    assert skipped.errors == loaded.errors == skipped_again.errors == []
    assert sum(image.has_data for image in loaded.find_all("image")) == 3
    assert skipped == skipped_again
    assert all(not image.has_data for image in skipped.find_all("image"))


@pytest.mark.parametrize("ocr", [False, True])
@pytest.mark.parametrize("kwargs", [{}, {"include_assets": True}])
def test_reader_preserves_positional_path_and_ocr(hwpx_path, monkeypatch, ocr, kwargs):
    calls = []
    monkeypatch.setattr(Dochan, "_run_ocr", lambda reader: calls.append(
        sum(image.has_data for image in reader.doc.find_all("image"))
    ))

    reader = Dochan(str(hwpx_path), ocr, **kwargs)

    assert reader.doc.errors == []
    assert calls == ([3] if ocr else [])


def test_include_assets_is_keyword_only(hwpx_path):
    reader_signature = signature(Dochan)
    parser_signature = signature(HWPXParser().parse)
    reader_signature.bind(hwpx_path, False, include_assets=False)
    parser_signature.bind(hwpx_path, include_assets=False)

    with pytest.raises(TypeError, match="too many positional arguments"):
        reader_signature.bind(hwpx_path, False, False)
    with pytest.raises(TypeError, match="too many positional arguments"):
        parser_signature.bind(hwpx_path, False)


def test_ocr_without_assets_is_rejected_before_parsing(hwpx_path, monkeypatch, bin_accesses):
    monkeypatch.setattr(Dochan, "_parse", lambda reader: pytest.fail("must not parse"))
    monkeypatch.setattr(Dochan, "_run_ocr", lambda reader: pytest.fail("must not OCR"))

    with pytest.raises(ValueError, match=r"ocr=True.*include_assets=False"):
        Dochan(hwpx_path, True, include_assets=False)
    assert bin_accesses == {"read": [], "open": []}


def test_existing_conversion_options_can_be_forwarded(hwpx_path):
    options = ConversionOptions(include_assets=False)

    reader = Dochan(hwpx_path, **asdict(options))

    assert reader.doc.errors == []
    assert len(reader.doc.find_all("image")) == 4
    assert all(not image.has_data for image in reader.doc.find_all("image"))


@pytest.mark.parametrize("suffix", [".hwp", ".docx", ".pdf", ".bin", ""])
def test_hwpx_option_uses_package_identity_not_extension(hwpx_path, suffix):
    renamed = hwpx_path.with_name("renamed" + suffix)
    hwpx_path.rename(renamed)

    reader = Dochan(renamed, False, include_assets=False)

    assert reader.doc.source_format == "hwpx"
    assert reader.doc.errors == []
    assert len(reader.doc.find_all("image")) == 4
    assert all(not image.has_data for image in reader.doc.find_all("image"))


@pytest.mark.parametrize("suffix, content", [
    (".hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    (".doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    (".ppt", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    (".xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    (".pdf", b"%PDF-1.7\n"),
    (".hwpx", b"%PDF-1.7\n"),
    (".txt", b"plain text"),
])
def test_false_is_rejected_for_non_hwpx_before_parsing(tmp_path, monkeypatch, suffix, content):
    path = tmp_path / ("other" + suffix)
    path.write_bytes(content)
    monkeypatch.setattr(Dochan, "_parse", lambda reader: pytest.fail("must not parse"))

    with pytest.raises(ValueError, match=r"include_assets=False.*HWPX"):
        Dochan(path, include_assets=False)


@pytest.mark.parametrize("part", ["word/document.xml", "ppt/presentation.xml", "xl/workbook.xml"])
@pytest.mark.parametrize("hwpx_marker", [False, True])
def test_false_rejects_ooxml_and_ambiguous_packages(tmp_path, part, hwpx_marker):
    path = tmp_path / "other.hwpx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(part, "<document/>")
        if hwpx_marker:
            archive.writestr("mimetype", "application/hwp+zip")

    with pytest.raises(ValueError, match=r"include_assets=False.*HWPX"):
        Dochan(path, include_assets=False)
