"""HWPX 문서 전체의 서식 런 예산과 무손실 폴백을 검증한다."""
import io
import zipfile

from dochan import Dochan
from dochan.hwpx import parser as hwpx
from dochan.model.document import TextRun


NS = ('xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
      'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
      'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"')


def _runs(text):
    return ''.join('<hp:run charPrIDRef="%d"><hp:t>%s</hp:t></hp:run>'
                   % (i % 2, char) for i, char in enumerate(text))


def _paragraph(text):
    return '<hp:p>%s</hp:p>' % _runs(text)


def _package(*sections):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('mimetype', 'application/hwp+zip')
        archive.writestr('Contents/header.xml',
                        '<hh:head %s><hh:charProperties>' % NS
                        + '<hh:charPr id="0" height="1000"><hh:bold/></hh:charPr>'
                        + '<hh:charPr id="1" height="1000"><hh:italic/></hh:charPr>'
                        + '</hh:charProperties></hh:head>')
        for i, section in enumerate(sections):
            archive.writestr('Contents/section%d.xml' % i,
                            '<hs:sec %s>%s</hs:sec>' % (NS, section))
    stream.seek(0)
    return stream


def _warnings(doc):
    return [error for error in doc.errors if 'text run budget' in error]


def test_hwpx_run_budget_preserves_prefix_and_plain_suffix(monkeypatch, tmp_path):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 2, raising=False)
    path = tmp_path / 'runs.hwpx'
    path.write_bytes(_package(_paragraph('가나다라마')).getvalue())
    reader = Dochan(str(path))
    paragraph = reader.doc.find_all('paragraph')[0]
    assert [run.text for run in paragraph.runs] == ['가', '나', '다라마']
    assert paragraph.runs[0].bold
    assert paragraph.runs[1].italic
    assert paragraph.runs[2] == TextRun(text='다라마')
    assert len(_warnings(reader.doc)) == 1
    assert '다라마' in reader.to_markdown()
    assert '다라마' in reader.to_json()


def test_hwpx_run_budget_shared_across_sections_and_nested_content(monkeypatch):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 2, raising=False)
    nested = '<hp:run><hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc>'
    nested += '<hp:subList>' + _paragraph('표안') + '</hp:subList>'
    nested += '</hp:tc></hp:tr></hp:tbl></hp:run>'
    note = '<hp:run><hp:ctrl><hp:footNote><hp:subList>'
    note += _paragraph('각주') + '</hp:subList></hp:footNote></hp:ctrl></hp:run>'
    doc = hwpx.HWPXParser().parse(_package(
        _paragraph('먼저') + '<hp:p>' + nested + _runs('뒤쪽') + note + '</hp:p>',
        _paragraph('다음')))
    paragraphs = doc.find_all('paragraph')
    assert [p.text for p in paragraphs] == ['먼저', '표안', '뒤쪽[1]', '각주', '다음']
    for paragraph in paragraphs[1:]:
        text_runs = [run for run in paragraph.runs if not run.note_ref]
        assert len(text_runs) == 1
        assert text_runs[0] == TextRun(text=text_runs[0].text)
    assert len(_warnings(doc)) == 1


def test_hwpx_run_budget_keeps_object_boundaries(monkeypatch):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 0, raising=False)
    body = '<hp:p>' + _runs('앞쪽')
    body += '<hp:run><hp:equation><hp:script>x</hp:script></hp:equation></hp:run>'
    body += _runs('뒷쪽') + '</hp:p>'
    doc = hwpx.HWPXParser().parse(_package(body))
    assert [p.text for p in doc.find_all('paragraph')] == ['앞쪽', '뒷쪽']
    assert len(doc.sections[0].elements) == 3
    assert all(len(p.runs) == 1 for p in doc.find_all('paragraph'))


def test_hwpx_run_budget_exact_limit_and_parser_reuse(monkeypatch):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 2, raising=False)
    parser = hwpx.HWPXParser()
    assert len(_warnings(parser.parse(_package(_paragraph('초과함'))))) == 1
    doc = parser.parse(_package(_paragraph('정상')))
    assert not _warnings(doc)
    assert [run.text for run in doc.find_all('paragraph')[0].runs] == ['정', '상']


def test_hwpx_run_budget_single_run_field_fanout(monkeypatch):
    monkeypatch.setattr(hwpx, 'MAX_DOCUMENT_TEXT_RUNS', 2, raising=False)
    content = ('<hp:t>글</hp:t><hp:ctrl><hp:fieldBegin type="CLICK_HERE"/>'
               '</hp:ctrl><hp:ctrl><hp:fieldEnd/></hp:ctrl>') * 30
    doc = hwpx.HWPXParser().parse(_package('<hp:p><hp:run>' + content + '</hp:run></hp:p>'))
    paragraph = doc.find_all('paragraph')[0]
    assert paragraph.text == '글' * 30
    assert len(paragraph.runs) == 3
    assert paragraph.runs[-1] == TextRun(text='글' * 28)
    assert len(_warnings(doc)) == 1
