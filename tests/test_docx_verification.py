"""실물 프로브의 완전 토큰 정렬이 추가와 중복도 검출하는지 확인한다."""
from lxml import etree

from scripts import verify_ooxml_docx as verify


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
