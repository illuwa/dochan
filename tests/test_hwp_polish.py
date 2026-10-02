"""재감수 회귀를 합성 HWP 레코드와 HWPX XML로 재현한다."""
import struct

import pytest

from dochan import Dochan
from dochan.hwp.doc_info import DocInfo, DocInfoParser
from dochan.hwp.records.para_text import parse_para_text
from dochan.hwp.section import SectionParser
from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Paragraph, TextRun
from dochan.model.style import StyleEntry
from test_hwp_review_fixes import _click, _inline
from test_hwp_revision_reader import TrackedOle, _section
from test_hwpx_controls import package


@pytest.mark.parametrize('value', ['', 'VALUE', 'PROMPT'])
def test_clickhere_only_emits_stored_body_in_both_formats(tmp_path, value):
    raw = _inline(3, b'klc%') + value.encode('utf-16-le') + _inline(4)
    actual, _ = SectionParser()._form_text_result(parse_para_text(raw), [_click()])
    body = ('<hp:p><hp:run><hp:t>prefix</hp:t><hp:ctrl>'
            '<hp:fieldBegin type="CLICK_HERE" id="1"><hp:parameters>'
            '<hp:stringParam name="Direction">PROMPT</hp:stringParam>'
            '</hp:parameters></hp:fieldBegin></hp:ctrl><hp:t>%s</hp:t>'
            '<hp:ctrl><hp:fieldEnd beginIDRef="1"/></hp:ctrl></hp:run></hp:p>') % value
    gold = HWPXParser().parse(package(tmp_path, body))
    assert 'prefix' + actual['text'] == gold.sections[0].elements[0].text
    assert actual['text'] == value


@pytest.mark.parametrize('level', [3, 4, 5])
@pytest.mark.parametrize('size', [10, 13, 16, 20])
def test_deep_direct_outline_stays_body(level, size):
    info = DocInfo(styles=[StyleEntry(name='Heading 1', para_shape_id=0)])
    DocInfoParser()._parse_para_shape(struct.pack('<I', (1 << 23) | (level << 25)), info)
    para = Paragraph(runs=[TextRun('text', font_size_pt=size)], para_shape_id=0, style_id=0)
    assert SectionParser(info)._detect_heading_level(para) == 0


def _tracked_reader(monkeypatch, tmp_path, mode='preserve', missing_body=False):
    class OversizedView(TrackedOle):
        def __init__(self, path):
            super().__init__(path)
            self.streams['ViewText/Section0'] = _section('VIEW') * 3
            self.streams['BodyText/Section0'] = _section('COMPLETE BODY')
            self.streams['ViewText/Section1'] = _section('NEXT VIEW')
            self.streams['BodyText/Section1'] = _section('NEXT BODY')
            if missing_body:
                del self.streams['BodyText/Section0']
    monkeypatch.setattr('dochan.reader.olefile.OleFileIO', OversizedView)
    monkeypatch.setattr('dochan.hwp.section.MAX_HWP_RECORDS', 3)
    path = tmp_path / 'tracked-limit.hwp'
    path.write_bytes(b'\xd0\xcf\x11\xe0')
    return Dochan(path, revision_mode=mode)


def test_preserve_record_limit_falls_back_to_body_and_warns(monkeypatch, tmp_path):
    reader = _tracked_reader(monkeypatch, tmp_path)
    assert [p.text for p in reader.find_all('paragraph')] == ['COMPLETE BODY', 'NEXT VIEW']
    assert any(e.startswith('WARN:') and 'BodyText' in e for e in reader.errors)
    assert not any(e.startswith('ERR:') for e in reader.errors)


def test_original_record_limit_does_not_substitute_final_body(monkeypatch, tmp_path):
    reader = _tracked_reader(monkeypatch, tmp_path, mode='original')
    assert 'COMPLETE BODY' not in reader.to_plain_text()
    assert any(e.startswith('ERR:') and 'record count' in e for e in reader.errors)


def test_preserve_record_limit_without_body_keeps_partial_view(monkeypatch, tmp_path):
    reader = _tracked_reader(monkeypatch, tmp_path, missing_body=True)
    assert 'VIEW' in reader.to_plain_text()
    assert any(e.startswith('ERR:') and 'record count' in e for e in reader.errors)


def test_preserve_body_fallback_still_enforces_record_limit(monkeypatch, tmp_path):
    class BothOversized(TrackedOle):
        def __init__(self, path):
            super().__init__(path)
            self.streams['ViewText/Section0'] = _section('VIEW') * 3
            self.streams['BodyText/Section0'] = _section('BODY') * 3
    monkeypatch.setattr('dochan.reader.olefile.OleFileIO', BothOversized)
    monkeypatch.setattr('dochan.hwp.section.MAX_HWP_RECORDS', 3)
    path = tmp_path / 'both-limit.hwp'
    path.write_bytes(b'\xd0\xcf\x11\xe0')
    reader = Dochan(path)
    assert reader.find_all('paragraph')[0].text == 'BODY'
    assert any(e.startswith('WARN:') and 'BodyText' in e for e in reader.errors)
    assert any(e.startswith('ERR:') and 'record count' in e for e in reader.errors)
