"""실물 프로브의 완전 토큰 정렬이 추가와 중복도 검출하는지 확인한다."""
from lxml import etree

from scripts import verify_ooxml_docx as verify
from test_docx_remaining import write_docx, paragraph, R
import zipfile


def test_alignment_detects_duplicate_and_extra_output_tokens():
    for actual in ['alpha alpha beta', 'alpha beta gamma']:
        result = verify.align_tokens('alpha beta', actual)
        assert not result['exact']
        assert result['inserted'] == 1
        assert result['matched'] == 2


def test_alignment_detects_reordering_and_missing_tokens():
    assert not verify.align_tokens('alpha beta', 'beta alpha')['exact']
    assert verify.align_tokens('alpha beta', 'alpha')['deleted'] == 1
    assert verify.align_tokens('alpha beta', 'alpha\n beta')['exact']


def test_xml_stream_joins_runs_but_separates_paragraphs_and_ignores_fallback():
    root = etree.fromstring(('<w:body xmlns:w="%s" xmlns:mc="%s"><w:p>'
        '<w:r><w:t>hel</w:t></w:r><w:r><w:t>lo</w:t></w:r></w:p>'
        '<mc:AlternateContent><mc:Choice><w:p><w:r><w:t>world</w:t></w:r></w:p>'
        '</mc:Choice><mc:Fallback><w:p><w:r><w:t>duplicate</w:t></w:r></w:p>'
        '</mc:Fallback></mc:AlternateContent></w:body>') % (verify.NS['w'], verify.NS['mc']))
    assert verify.align_tokens(verify.xml_body_text(root), 'hello world')['exact']


def test_logical_oracle_requires_image_and_link_at_original_anchor(tmp_path):
    path = tmp_path / 'anchors.docx'
    write_docx(path, '<w:p><w:r><w:t>before</w:t><w:drawing>'
        '<a:blip r:embed="img"/></w:drawing><w:t>after</w:t></w:r>'
        '<w:hyperlink r:id="link"><w:r><w:t>label</w:t></w:r>'
        '</w:hyperlink></w:p>', {'word/media/a.png': b'PNG'},
        '<Relationship Id="img" Type="%s/image" Target="media/a.png"/>'
        '<Relationship Id="link" Type="%s/hyperlink" Target="https://example.org" TargetMode="External"/>' % (R, R))
    with zipfile.ZipFile(path) as package:
        expected = verify.logical_body_text(package)
    correct = 'before![image](word/media/a.png)afterlabel <https://example.org>'
    assert verify.align_tokens(expected, correct)['exact']
    for wrong in [correct.replace('![image](word/media/a.png)', ''),
                  correct + '![image](word/media/a.png)',
                  correct.replace('before!', '!').replace('afterlabel', 'beforeafterlabel')]:
        assert not verify.align_tokens(expected, wrong)['exact']


def test_logical_oracle_does_not_strip_literal_markdown_or_join_across_image(tmp_path):
    path = tmp_path / 'literal.docx'
    write_docx(path, paragraph('![image](word/media/a.png) [comment 1] &lt;#anchor&gt;'))
    with zipfile.ZipFile(path) as package:
        expected = verify.logical_body_text(package)
    assert verify.align_tokens(expected, '![image](word/media/a.png) [comment 1] <#anchor>')['exact']
    assert not verify.align_tokens(expected, '')['exact']


def test_logical_oracle_checks_table_boundaries(tmp_path):
    path = tmp_path / 'table.docx'
    write_docx(path, paragraph('before') + '<w:tbl><w:tr><w:tc>' +
               paragraph('cell') + '</w:tc></w:tr></w:tbl>' + paragraph('after'))
    with zipfile.ZipFile(path) as package:
        expected = verify.logical_body_text(package, structural=True)
    doc = verify.DOCXReader().read(str(path))
    actual = verify.model_body_text(doc.sections[0].elements, structural=True)
    assert verify.align_tokens(expected, actual)['exact']
    assert not verify.align_tokens(expected, 'before cell after')['exact']


def test_logical_oracle_keeps_chart_cells_at_anchor(tmp_path):
    from test_docx_review_fixes import PARTS, RELS, CHART
    path = tmp_path / 'chart.docx'
    write_docx(path, paragraph('before') + '<w:p><w:r>' + CHART + '</w:r></w:p>' + paragraph('after'), PARTS, RELS)
    with zipfile.ZipFile(path) as package:
        expected = verify.logical_body_text(package, structural=True)
    doc = verify.DOCXReader().read(str(path))
    actual = verify.model_body_text(doc.sections[0].elements, structural=True)
    assert verify.align_tokens(expected, actual)['exact']
    assert not verify.align_tokens(expected, actual.replace('42', '43'))['exact']
    assert not verify.align_tokens(expected, actual + '42')['exact']


def test_logical_oracle_preserves_encoded_external_link(tmp_path):
    path = tmp_path / 'link.docx'
    write_docx(path, '<w:p><w:hyperlink r:id="link"><w:r><w:t>label</w:t>'
               '</w:r></w:hyperlink></w:p>', rels='<Relationship Id="link" Type="%s/hyperlink" '
               'Target="https://example.org/a%%20b" TargetMode="External"/>' % R)
    with zipfile.ZipFile(path) as package:
        expected = verify.logical_body_text(package)
    assert verify.align_tokens(expected, 'label <https://example.org/a%20b>')['exact']


def test_story_oracle_detects_header_after_body_and_missing_note(tmp_path):
    path = tmp_path / 'stories.docx'
    w = verify.NS['w']
    write_docx(path, '<w:p><w:r><w:t>body</w:t><w:footnoteReference w:id="2"/></w:r></w:p>'
               '<w:sectPr><w:headerReference r:id="h"/></w:sectPr>',
               {'word/header1.xml': '<w:hdr xmlns:w="%s">%s</w:hdr>' % (w, paragraph('header')),
                'word/footnotes.xml': '<w:footnotes xmlns:w="%s"><w:footnote w:id="2">%s</w:footnote></w:footnotes>' % (w, paragraph('note'))},
               '<Relationship Id="h" Type="%s/header" Target="header1.xml"/>' % R)
    doc = verify.DOCXReader().read(str(path))
    with zipfile.ZipFile(path) as package:
        assert verify.story_evidence(package, doc)['exact']
        doc.sections[0].elements[0:2] = reversed(doc.sections[0].elements[0:2])
        assert not verify.story_evidence(package, doc)['exact']
        doc.sections[0].elements.pop()
        assert not verify.story_evidence(package, doc)['exact']


def test_probe_primary_result_does_not_pass_empty_unsupported_body(tmp_path):
    path = tmp_path / 'strict.docx'
    with zipfile.ZipFile(path, 'w') as package:
        package.writestr('[Content_Types].xml', '<Types/>')
        package.writestr('word/document.xml', '<w:document xmlns:w="http://purl.oclc.org/ooxml/wordprocessingml/main">'
                          '<w:body><w:p><w:r><w:t>missing</w:t><w:drawing><shape/></w:drawing></w:r></w:p></w:body></w:document>')
    result = verify.probe(tmp_path)['reading_order'][0]
    assert not result['exact']
    assert result['errors']
    assert result['raw_wt']['exact']  # 예전 빈 문자열끼리 비교가 만든 거짓 성공이다.
