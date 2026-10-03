"""본문 섹션은 다른 XML 파트보다 큰 상한을 쓴다(공개 통계 보도자료의 41.7MB 섹션)."""
import zipfile

from dochan import Dochan
from dochan.hwpx import parser as hwpx_parser
from dochan.hwpx.parser import HWPXParser

NS = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"'


def _package(path, text):
    section = ('<hs:sec %s><hp:p><hp:run><hp:t>%s</hp:t></hp:run></hp:p></hs:sec>' % (NS, text)).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", section)
    return len(section)


def test_section_larger_than_generic_xml_limit_is_read(tmp_path, monkeypatch):
    size = _package(tmp_path / "big.hwpx", "x" * 400)
    monkeypatch.setattr(hwpx_parser, "MAX_XML_FILE_SIZE", size - 1)
    monkeypatch.setattr(hwpx_parser, "MAX_SECTION_XML_SIZE", size + 1)
    document = Dochan(str(tmp_path / "big.hwpx"))
    assert "x" * 400 in document.to_markdown()
    assert not any("크기 초과" in error for error in document.errors)


def test_section_over_section_limit_is_rejected(tmp_path, monkeypatch):
    size = _package(tmp_path / "huge.hwpx", "y" * 400)
    monkeypatch.setattr(hwpx_parser, "MAX_SECTION_XML_SIZE", size - 1)
    document = HWPXParser().parse(str(tmp_path / "huge.hwpx"))
    assert any("크기 초과" in error for error in document.errors)


def test_previous_section_tree_is_released_before_next_section(tmp_path, monkeypatch):
    path = tmp_path / "two.hwpx"
    section = ('<hs:sec %s><hp:p><hp:run><hp:t>s</hp:t></hp:run></hp:p></hs:sec>' % NS).encode()
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", section)
        archive.writestr("Contents/section1.xml", section)
    seen = []
    original = HWPXParser._read_zip_part

    def spy(self, zf, name, limit):
        if name.startswith("Contents/section"):
            seen.append(self._section_root is None)
        return original(self, zf, name, limit)

    monkeypatch.setattr(HWPXParser, "_read_zip_part", spy)
    HWPXParser().parse(str(path))
    assert seen == [True, True]
