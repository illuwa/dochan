"""코퍼스 없이 조립한 PDF로 강조 절 제목과 기존 크기 기준을 검증한다."""
import pytest

from dochan.pdf.reader import PDFReader
from test_pdf_structure import _build_pdf


BODY = ['본문 내용은 제목과 같은 크기로 작성했습니다.',
        '다음 본문에도 여러 어절과 충분한 글자가 있습니다.',
        '마지막 본문 문단으로 본문 크기를 확인합니다.']


def _line(text, y, size=12, bold=False, x=60, mode=0, width=0.4):
    return (b'q %g w BT /%s %g Tf %d Tr 1 0 0 1 %g %g Tm <%s> Tj ET Q\n' %
            (width, b'F2' if bold else b'F1', size, mode, x, y,
             text.encode('utf-16-be').hex().encode('ascii')))


def _pdf(tmp_path, contents, texts, extra=None):
    mapping = b' '.join(b'<%04X> <%s>' % (ord(c), c.encode('utf-16-be').hex().encode())
                        for c in sorted(set(''.join(texts))))
    cmap = b'%d beginbfchar %s endbfchar' % (len(set(''.join(texts))), mapping)
    objects = {1: '<< /Type /Catalog /Pages 2 0 R >>',
               2: '<< /Type /Pages /Kids [%s] /Count %d /MediaBox [0 0 600 800] '
                  '/Resources << /Font << /F1 20 0 R /F2 21 0 R >> >> >>' % (
                      ' '.join('%d 0 R' % (3 + i) for i in range(len(contents))), len(contents)),
               20: '<< /Type /Font /Subtype /Type0 /BaseFont /Test-Regular /Encoding /Identity-H '
                   '/DescendantFonts [22 0 R] /ToUnicode 23 0 R >>',
               21: '<< /Type /Font /Subtype /Type0 /BaseFont /Test-Bold /Encoding /Identity-H '
                   '/DescendantFonts [22 0 R] /ToUnicode 23 0 R >>',
               22: '<< /Type /Font /Subtype /CIDFontType2 /DW 500 >>',
               23: b'<< /Length %d >>\nstream\n%s\nendstream' % (len(cmap), cmap)}
    for i, content in enumerate(contents):
        objects[3 + i] = '<< /Type /Page /Parent 2 0 R /Contents %d 0 R >>' % (10 + i)
        objects[10 + i] = b'<< /Length %d >>\nstream\n%s\nendstream' % (len(content), content)
    if extra:
        objects.update(extra)
    path = tmp_path / 'headings.pdf'
    path.write_bytes(_build_pdf(objects))
    return PDFReader().read(str(path))


def _document(tmp_path, title, **kwargs):
    content = _line(title, 680, **kwargs)
    content += b''.join(_line(text, 600 - i * 40) for i, text in enumerate(BODY))
    return _pdf(tmp_path, [content], [title] + BODY)


@pytest.mark.parametrize('title', ['□ 추진배경', '■ 추진계획', '< 보도내용 요약 >',
                                  '▶ 추진방향', '◆ 추진방향', '>> 추진방향', 'Q.1 추진방향'])
def test_bold_section_marker_promoted(tmp_path, title):
    doc = _document(tmp_path, title, bold=True)
    para = doc.sections[0].elements[0]
    assert para.text == title
    assert para.heading_level == 3
    assert all(p.heading_level == 0 for p in doc.sections[0].elements[1:])


def test_nonbold_marker_is_body(tmp_path):
    assert _document(tmp_path, '□ 추진배경').sections[0].elements[0].heading_level == 0


@pytest.mark.parametrize('title', ['□ (지원) 규모를 확대', '□ 지원하고 성과를 확인',
                                  '□ 현재 → 향후', '□ ' + '내용' * 31, '□ 사업을 추진한다.'])
def test_statement_is_not_heading(tmp_path, title):
    assert _document(tmp_path, title, bold=True).sections[0].elements[0].heading_level == 0


def test_size_headings_and_unmarked_h3_remain_unchanged(tmp_path):
    titles = ['기존 큰 제목', '기존 중간 제목', '조금 큰 본문']
    content = b''.join(_line(t, 710 - i * 40, size=s) for i, (t, s) in enumerate(zip(titles, [18, 15, 13.2])))
    content += b''.join(_line(t, 500 - i * 40) for i, t in enumerate(BODY))
    content += _line(BODY[0], 340)
    doc = _pdf(tmp_path, [content], titles + BODY)
    assert [p.heading_level for p in doc.sections[0].elements] == [1, 2, 0, 0, 0, 0, 0]


def test_number_needs_larger_content_and_marker_size_is_ignored(tmp_path):
    assert _document(tmp_path, '1. 추진배경', bold=True).sections[0].elements[0].heading_level == 0
    assert _document(tmp_path, 'Ⅰ. 추진배경', size=13.2).sections[0].elements[0].heading_level == 3
    content = _line('□', 680, size=8) + _line(' 추진배경', 680, x=64, size=13.2)
    content += b''.join(_line(t, 600 - i * 40) for i, t in enumerate(BODY))
    doc = _pdf(tmp_path, [content], ['□ 추진배경'] + BODY)
    assert doc.sections[0].elements[0].heading_level == 3
    assert [r.font_size_pt for r in doc.sections[0].elements[0].runs if r.text.strip()] == [8, 13.2]


@pytest.mark.parametrize('mode,width,expected', [(2, 0.4, True), (6, 0.4, True),
                                              (0, 0.4, False), (1, 0.4, False), (2, 0, False)])
def test_fill_and_stroke_bold_is_per_run(tmp_path, mode, width, expected):
    doc = _document(tmp_path, '□ 추진배경', mode=mode, width=width)
    para = doc.sections[0].elements[0]
    assert all(r.bold == expected for r in para.runs)
    assert para.heading_level == (3 if expected else 0)
    assert all(not r.bold for p in doc.sections[0].elements[1:] for r in p.runs)


def test_extgstate_line_width_overrides_stroke_bold(tmp_path):
    title = '□ 추진배경'
    content = _line(title, 680, mode=2, width=0.4).replace(
        b'0.4 w BT', b'0.4 w /Zero gs BT')
    content += b''.join(_line(text, 600 - i * 40) for i, text in enumerate(BODY))
    extra = {
        2: '<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 600 800] '
           '/Resources << /Font << /F1 20 0 R /F2 21 0 R >> '
           '/ExtGState << /Zero 30 0 R >> >> >>',
        30: '<< /LW 0 >>',
    }
    para = _pdf(tmp_path, [content], [title] + BODY, extra=extra).sections[0].elements[0]
    assert not para.runs[0].bold
    assert para.heading_level == 0


def test_key_value_group_is_body(tmp_path):
    titles = ['□ (일시)', '□ (장소)']
    content = b''.join(_line(t, 680 - i * 40, bold=True) for i, t in enumerate(titles))
    content += b''.join(_line(t, 530 - i * 40) for i, t in enumerate(BODY))
    doc = _pdf(tmp_path, [content], titles + BODY)
    assert all(p.heading_level == 0 for p in doc.sections[0].elements)


def test_centered_caption_before_table_and_table_cell_are_not_headings(tmp_path):
    titles = ['< 현황 >', '□ 추진배경']
    # 6글자 * 6pt 폭의 캡션을 페이지 중앙에 놓고 닫힌 격자를 바로 뒤에 그린다.
    content = _line(titles[0], 680, bold=True, x=282)
    content += b'60 580 m 400 580 l 400 650 l 60 650 l h S 230 580 m 230 650 l S\n'
    content += _line(titles[1], 625, bold=True, x=75) + _line('값', 625, x=245)
    content += b''.join(_line(t, 520 - i * 40) for i, t in enumerate(BODY))
    doc = _pdf(tmp_path, [content], titles + BODY + ['값'])
    assert doc.sections[0].elements[0].heading_level == 0
    assert len(doc.find_all('table')) == 1
    assert all(p.heading_level == 0 for row in doc.find_all('table')[0].rows
               for cell in row for p in cell.paragraphs)


def test_repeated_header_and_note_body_are_not_promoted(tmp_path):
    header = '□ 반복 머리말'
    contents = [_line(header, 755, bold=True) + b''.join(
        _line(t, 500 - i * 40) for i, t in enumerate(BODY)) for _ in range(2)]
    doc = _pdf(tmp_path, contents, [header] + BODY)
    assert doc.find_all('header_footer')
    assert all(p.heading_level == 0 for hf in doc.find_all('header_footer') for p in hf.paragraphs)
    assert all(p.heading_level == 0 for s in doc.sections for p in s.elements if hasattr(p, 'heading_level'))


def test_font_size_boundaries_do_not_fragment_markdown_emphasis(tmp_path):
    from dochan.output.markdown import to_markdown

    title = '□ 추진배경'
    content = _line('□', 680, size=8, bold=True)
    content += _line(' 추진배경', 680, size=12, bold=True, x=64)
    content += b''.join(_line(t, 600 - i * 40) for i, t in enumerate(BODY))
    doc = _pdf(tmp_path, [content], [title] + BODY)
    assert '### **□ 추진배경**' in to_markdown(doc)


def test_geometric_caption_is_excluded_when_table_is_painted_after_body(tmp_path):
    title = '< 현황 >'
    content = _line(title, 680, bold=True, x=282)
    content += b''.join(_line(t, 520 - i * 40) for i, t in enumerate(BODY))
    content += b'60 580 m 540 580 l 540 665 l 60 665 l h S 300 580 m 300 665 l S\n'
    content += _line('구분', 625, x=75) + _line('값', 625, x=315)
    doc = _pdf(tmp_path, [content], [title, '구분', '값'] + BODY)
    assert doc.sections[0].elements[0].heading_level == 0
    assert len(doc.find_all('table')) == 1


def test_dot_leader_toc_entry_is_not_an_emphasized_heading(tmp_path):
    assert _document(tmp_path, '1. Heading 1 .................. 1', size=13.2).sections[0].elements[0].heading_level == 0


def test_detected_footnote_definition_never_gets_font_heading(tmp_path):
    texts = ['Body', '1)', '1) □ 각주제목'] + BODY
    content = _line('Body', 500) + _line('1)', 502.5, size=9, x=84)
    content += b''.join(_line(t, 440 - i * 40) for i, t in enumerate(BODY))
    content += b'60 115 m 180 115 l S\n' + _line('1) □ 각주제목', 100, size=10.5, bold=True)
    doc = _pdf(tmp_path, [content], texts)
    notes = doc.find_all('footnote')
    assert len(notes) == 1
    assert notes[0].text == '□ 각주제목'
    assert notes[0].paragraphs[0].heading_level == 0


def test_partial_bold_and_wrapped_marker_are_not_headings(tmp_path):
    title = '□ 추진배경'
    content = _line('□ 추진', 680, bold=True) + _line('배경', 680, x=84)
    content += b''.join(_line(t, 600 - i * 40) for i, t in enumerate(BODY))
    doc = _pdf(tmp_path, [content], [title] + BODY)
    assert doc.sections[0].elements[0].heading_level == 0
    content = _line('□ 추진배경', 680, bold=True) + _line('세부설명', 662, bold=True)
    content += b''.join(_line(t, 600 - i * 40, x=60, size=12) for i, t in enumerate(['본문', '내용', '끝']))
    doc = _pdf(tmp_path, [content], [title, '세부설명', '본문', '내용', '끝'])
    # 첫 줄은 이 흐름의 오른쪽 경계까지 차므로 다음 줄과 같은 문단이 된다.
    assert '세부설명' in doc.sections[0].elements[0].text
    assert doc.sections[0].elements[0].heading_level == 0


def test_font_heading_budget_keeps_size_titles_and_cleans_metadata(tmp_path, monkeypatch):
    import dochan.pdf.headings as headings

    monkeypatch.setattr(headings, 'MAX_FONT_HEADING_PARAGRAPHS', 2)
    doc = _document(tmp_path, '□ 추진배경', bold=True)
    assert all(p.heading_level == 0 for p in doc.sections[0].elements)
    assert any('제목 문단 한도' in warning for warning in doc.errors)
    assert all(not hasattr(p, '_pdf_heading') for p in doc.sections[0].elements)


def test_form_inherits_stroke_bold_without_leaking_it_to_caller(tmp_path):
    from test_pdf_forms import _read, _stream

    doc = _read(tmp_path, b'q 0.4 w 2 Tr /F Do Q BT /F1 12 Tf 60 400 Td (AFTER) Tj ET', {
        6: _stream(b'BT /F1 12 Tf 60 500 Td (FORM) Tj ET', '/Subtype /Form')})
    form, after = doc.sections[0].elements
    assert form.text == 'FORM' and form.runs[0].bold
    assert after.text == 'AFTER' and not after.runs[0].bold
