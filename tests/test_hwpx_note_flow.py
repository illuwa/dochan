"""HWPX note references stay inline while definitions follow their paragraph."""

import json
import zipfile

import pytest

from dochan.hwpx.parser import HWPXParser
from dochan.model.document import Paragraph
from dochan.model.header_footer import Footnote, HeaderFooter
from dochan.model.image import Image
from dochan.model.table import Table
from dochan.output.json_out import to_json
from dochan.output.markdown import to_markdown


NS = ('xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
      'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
      'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
      'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"')


def _document(tmp_path, body, revision_mode='preserve'):
    path = tmp_path / 'note-flow.hwpx'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/hwp+zip')
        archive.writestr('Contents/header.xml',
                         '<hh:head %s><hh:trackChange id="1" type="Insert"/></hh:head>' % NS)
        archive.writestr('Contents/section0.xml', '<hs:sec %s>%s</hs:sec>' % (NS, body))
    return HWPXParser().parse(path, revision_mode=revision_mode, include_assets=False)


def _note(body, kind='footNote'):
    return ('<hp:ctrl><hp:%s><hp:subList><hp:p><hp:run><hp:t>%s</hp:t>'
            '</hp:run></hp:p></hp:subList></hp:%s></hp:ctrl>') % (kind, body, kind)


def _paragraph(content):
    return '<hp:p><hp:run>%s</hp:run></hp:p>' % content


def _table(content):
    return ('<hp:tbl rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList>%s'
            '</hp:subList><hp:cellAddr rowAddr="0" colAddr="0"/>'
            '<hp:cellSpan rowSpan="1" colSpan="1"/></hp:tc></hp:tr></hp:tbl>') % content


def test_note_inside_sentence_keeps_one_paragraph_and_json_link(tmp_path):
    doc = _document(tmp_path, _paragraph('<hp:t>앞</hp:t>' + _note('본문') + '<hp:t>뒤</hp:t>'))
    para, note = doc.sections[0].elements
    assert isinstance(para, Paragraph)
    assert isinstance(note, Footnote)
    assert para.text == '앞[1]뒤'
    assert [(run.text, run.note_ref) for run in para.runs] == [
        ('앞', 0), ('[1]', 1), ('뒤', 0)]
    assert (note.type, note.number, note.text) == ('footnote', 1, '본문')
    assert to_markdown(doc) == '앞[^1]뒤\n\n[^1]: 본문'
    elements = json.loads(to_json(doc))['sections'][0]['elements']
    assert elements[0]['runs'][1]['note_ref'] == elements[1]['number'] == 1
    assert elements[1]['text'] == '본문'


def test_multiple_notes_keep_reference_and_definition_order(tmp_path):
    body = _paragraph('<hp:t>A</hp:t>' + _note('첫째') + '<hp:t>B</hp:t>'
                      + _note('둘째', 'endNote') + '<hp:t>C</hp:t>')
    doc = _document(tmp_path, body)
    assert [type(item) for item in doc.sections[0].elements] == [Paragraph, Footnote, Footnote]
    assert doc.sections[0].elements[0].text == 'A[1]B[2]C'
    assert [(note.type, note.number, note.text) for note in doc.find_all('note')] == [
        ('footnote', 1, '첫째'), ('endnote', 2, '둘째')]
    assert to_markdown(doc) == 'A[^1]B[^2]C\n\n[^1]: 첫째\n\n[^2]: 둘째'


def test_note_and_picture_keep_object_order(tmp_path):
    picture = '<hp:pic><hp:shapeComment>그림</hp:shapeComment></hp:pic>'
    for objects, types in (( _note('본문') + picture, [Footnote, Image]),
                           (picture + _note('본문'), [Image, Footnote])):
        doc = _document(tmp_path, _paragraph('<hp:t>앞</hp:t>' + objects + '<hp:t>뒤</hp:t>'))
        assert [type(item) for item in doc.sections[0].elements] == [Paragraph] + types
        assert doc.sections[0].elements[0].text == '앞[1]뒤'


def test_note_before_table_keeps_table_boundary(tmp_path):
    body = _paragraph('<hp:t>앞</hp:t>' + _note('본문') + '<hp:t>중</hp:t>'
                      + _table(_paragraph('<hp:t>칸</hp:t>')) + '<hp:t>뒤</hp:t>')
    doc = _document(tmp_path, body)
    elements = doc.sections[0].elements
    assert [type(item) for item in elements] == [Paragraph, Footnote, Table, Paragraph]
    assert [item.text for item in elements if isinstance(item, Paragraph)] == ['앞[1]중', '뒤']
    assert elements[2].rows[0][0].text == '칸'


def test_note_inside_table_cell_stays_with_cell_paragraph(tmp_path):
    doc = _document(tmp_path, _paragraph(_table(_paragraph(
        '<hp:t>셀 앞</hp:t>' + _note('셀 주석') + '<hp:t>셀 뒤</hp:t>'))))
    cell = doc.sections[0].elements[0].rows[0][0]
    assert [type(item) for item in cell.paragraphs] == [Paragraph, Footnote]
    assert cell.paragraphs[0].text == '셀 앞[1]셀 뒤'
    assert '셀 앞[^1]셀 뒤' in to_markdown(doc)
    assert '[^1]: 셀 주석' in to_markdown(doc)


def test_endnote_inside_sentence_keeps_one_paragraph(tmp_path):
    doc = _document(tmp_path, _paragraph('<hp:t>앞</hp:t>' + _note('미주', 'endNote') + '<hp:t>뒤</hp:t>'))
    assert [type(item) for item in doc.sections[0].elements] == [Paragraph, Footnote]
    assert doc.sections[0].elements[0].text == '앞[1]뒤'
    assert doc.sections[0].elements[1].type == 'endnote'
    assert to_markdown(doc) == '앞[^1]뒤\n\n[^1]: 미주'


def test_note_inside_header_and_textbox_keeps_nested_paragraph(tmp_path):
    header = ('<hp:ctrl><hp:header><hp:subList>%s</hp:subList>'
              '</hp:header></hp:ctrl>') % _paragraph('<hp:t>머리</hp:t>' + _note('머리 주석') + '<hp:t>끝</hp:t>')
    textbox = ('<hp:rect><hp:drawText><hp:subList>%s</hp:subList>'
               '</hp:drawText></hp:rect>') % _paragraph('<hp:t>상자</hp:t>' + _note('상자 주석') + '<hp:t>끝</hp:t>')
    doc = _document(tmp_path, _paragraph(header + textbox))
    elements = doc.sections[0].elements
    assert isinstance(elements[0], HeaderFooter)
    assert [type(item) for item in elements[0].paragraphs] == [Paragraph, Footnote]
    assert elements[0].paragraphs[0].text == '머리[1]끝'
    assert [type(item) for item in elements[1:]] == [Paragraph, Footnote]
    assert elements[1].text == '상자[2]끝'
    assert [note.number for note in doc.find_all('note')] == [1, 2]


@pytest.mark.parametrize('mode, present', [
    ('preserve', True), ('final', True), ('original', False),
])
def test_revision_projection_keeps_or_removes_note_atomically(tmp_path, mode, present):
    body = _paragraph('<hp:t>앞<hp:insertBegin Id="i" TcId="1"/></hp:t>'
                      + _note('삽입 주석')
                      + '<hp:t><hp:insertEnd Id="i" TcId="1" paraend="0"/>뒤</hp:t>')
    doc = _document(tmp_path, body, revision_mode=mode)
    elements = doc.sections[0].elements
    assert len(elements) == (2 if present else 1)
    assert elements[0].text == ('앞[1]뒤' if present else '앞뒤')
    assert [note.number for note in doc.find_all('note')] == ([1] if present else [])
