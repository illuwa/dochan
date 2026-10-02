"""리뷰에서 발견한 공용 Markdown 캡션과 시트 경계 회귀."""
from types import SimpleNamespace

import pytest

from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.table import Cell, Table
from dochan.output.markdown import to_markdown


def test_caption_preserves_brackets_and_angle_brackets():
    table = Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun('data')])])]],
                  caption=[Paragraph(runs=[TextRun('<그림> [원문] * _ ~ ` 끝\\')])])
    output = to_markdown(Document(sections=[Section(elements=[table])]))
    assert output.endswith('*<그림> [원문] \\* \\_ \\~ \\` 끝\\\\*')


@pytest.mark.parametrize('source_format', ['xlsx', 'xls'])
@pytest.mark.parametrize('visibility,state', [(1, 'hidden'), (2, 'veryHidden')])
def test_hidden_sheet_forces_all_sheet_headings_and_separates_metadata(source_format, visibility, state):
    sections = []
    for name, value, hidden in [('Country Master (2) [hidden]', 'secret', True),
                                ('Sheet2', 'public', False)]:
        section = Section(elements=[Paragraph(runs=[TextRun(value)])])
        section.provenance = SimpleNamespace(sheet=name, hidden=hidden,
                                             visibility=visibility if hidden else 0)
        sections.append(section)
    rendered = to_markdown(Document(source_format=source_format, sections=sections))
    assert '## Country Master (2) [hidden]\n\n*Sheet visibility: %s*' % state in rendered
    assert '## Sheet2\n\npublic' in rendered
    assert rendered.count('Sheet visibility:') == 1
