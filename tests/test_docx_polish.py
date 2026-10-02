"""인라인 이미지 문단 보존과 반복 차트의 경량 복제 회귀 테스트."""
import pytest

from dochan.model.document import Paragraph
from dochan.output.markdown import to_markdown
from test_docx_review_fixes import IMAGE, CHART, CAPTION, read


@pytest.mark.parametrize('prefix', ['', '<w:t>before</w:t>'])
def test_docx_heading_keeps_inline_images_and_following_text(tmp_path, prefix):
    doc = read(tmp_path, '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
               '<w:r>' + prefix + IMAGE + IMAGE + '<w:t>Report</w:t></w:r></w:p>')
    paragraphs = doc.find_all('paragraph')
    assert len(paragraphs) == 1
    assert paragraphs[0].heading_level == 1
    assert paragraphs[0].text.endswith('![image](word/media/a.png)Report')
    assert to_markdown(doc).count('![') == 2
    assert to_markdown(doc).count('# ') == 1


def test_docx_image_alt_is_only_in_reference_in_original_order(tmp_path):
    drawing = ('<w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/'
               'drawingml/2006/wordprocessingDrawing"><wp:docPr title="tab1" '
               'descr="description" name="Picture"/><a:blip r:embed="img"/>'
               '</wp:inline></w:drawing>')
    doc = read(tmp_path, '<w:p><w:r><w:t>before</w:t>' + drawing +
               '<w:t>after</w:t></w:r></w:p>')
    assert to_markdown(doc) == 'before![tab1 description Picture](word/media/a.png)after'
    assert len(doc.find_all('image')) == 1


def test_docx_unresolved_image_keeps_drawing_description(tmp_path):
    drawing = ('<w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/'
               'drawingml/2006/wordprocessingDrawing"><wp:docPr descr="fallback"/>'
               '<a:blip r:embed="missing"/></wp:inline></w:drawing>')
    doc = read(tmp_path, '<w:p><w:r>' + drawing + '</w:r></w:p>')
    assert to_markdown(doc) == 'fallback'


def test_docx_linked_inline_image_stays_in_one_paragraph(tmp_path):
    doc = read(tmp_path, '<w:p><w:r><w:t>before</w:t></w:r>'
               '<w:hyperlink r:id="link"><w:r>' + IMAGE + '</w:r></w:hyperlink>'
               '<w:r><w:t>after</w:t></w:r></w:p>')
    assert len(doc.find_all('paragraph')) == 1
    assert to_markdown(doc) == ('before![image](word/media/a.png) '
                                '<https://example.org/target>after')


@pytest.mark.parametrize('above', [True, False])
def test_docx_inline_reference_keeps_caption_and_ocr(tmp_path, above):
    image = '<w:p><w:r>' + IMAGE + '</w:r></w:p>'
    caption = CAPTION % 'Figure caption'
    doc = read(tmp_path, caption + image if above else image + caption)
    extracted = doc.find_all('image')[0]
    assert extracted.image_data == b'PNG'
    assert extracted.caption_text == 'Figure caption'
    assert extracted.caption_side == ('TOP' if above else 'BOTTOM')
    extracted.ocr_text = 'OCR result'
    markdown = to_markdown(doc)
    assert markdown.count('![') == 1
    assert markdown.count('Figure caption') == 1
    assert markdown.count('OCR result') == 1


def test_docx_repeated_chart_keeps_occurrence_mutations_independent(tmp_path):
    doc = read(tmp_path, ('<w:p><w:r>' + CHART + '</w:r></w:p>') * 2)
    first, second = doc.find_all('table')
    assert first is not second
    assert first.rows is not second.rows
    assert first.caption is not second.caption
    first.caption.append(Paragraph())
    assert len(first.caption) == len(second.caption) + 1
    first.rows[1][1].paragraphs[0].runs[0].text = 'edited'
    assert second.rows[1][1].text == '42'
