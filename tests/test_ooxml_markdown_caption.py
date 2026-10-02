"""공용 표·그림 캡션의 Markdown 특수문자 보존."""
import pytest

from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.image import Image
from dochan.model.table import Cell, Table
from dochan.output.markdown import to_markdown


@pytest.mark.parametrize("kind", ["table", "image"])
@pytest.mark.parametrize("side", ["TOP", "BOTTOM"])
def test_caption_escapes_literal_markdown_without_changing_model(kind, side):
    caption = Paragraph(runs=[TextRun("a*b _axis_ `code` [link] <tag> ~gone~ \\path")])
    elem = (Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun("value")])])]])
            if kind == "table" else Image(filename="plot.png"))
    elem.caption = [caption]
    elem.caption_side = side
    rendered = to_markdown(Document(sections=[Section(elements=[elem])]))
    expected = r"*a\*b \_axis\_ \`code\` [link] <tag> \~gone\~ \\path*"
    assert expected in rendered
    assert (rendered.startswith(expected) if side == "TOP" else rendered.endswith(expected))
    assert elem.caption_text == caption.text


def test_chart_caption_plain_text_contract_is_preserved():
    table = Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun("value")])])]],
                  caption=[Paragraph(runs=[TextRun("Chart type: column; Category axis: 분기")])],
                  caption_side="TOP")
    doc = Document(sections=[Section(elements=[table])])
    assert to_markdown(doc).startswith("*Chart type: column; Category axis: 분기*\n\n")
