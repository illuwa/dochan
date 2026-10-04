"""사전 값 문자열 뒤에 남은 짝 없는 `)` 를 건너뛴다.

한컴 PDF 는 링크 대상이 `)` 로 끝나면(자동 링크가 닫는 괄호까지 삼킨 경우) URI 문자열의 `)` 를
이스케이프하지 않고 `/URI (http://example.test))` 로 쓴다. 문자열은 첫 `)` 에서 끝나고 `)` 하나가
사전 키 자리에 남는다(ISO 32000-1 7.3.4.2 위반). 이 한 가지 꼴만 복구하고 경고를 남긴다.
"""
import pytest

from dochan import Dochan
from dochan.pdf.objects import PDFLexer, PDFSyntaxError
from test_pdf_structure import _build_pdf, _minimal_objects


def test_dict_skips_stray_closing_paren_after_string_value():
    lexer = PDFLexer(b'<< /URI (http://example.test)) /S /URI >>')
    assert lexer.parse_object() == {'URI': b'http://example.test', 'S': 'URI'}
    assert lexer.stray_closers == 1


def test_dict_skips_stray_closing_paren_before_dict_end():
    lexer = PDFLexer(b'<< /S /URI /URI (http://example.test)) >> 7')
    assert lexer.parse_object() == {'S': 'URI', 'URI': b'http://example.test'}
    assert lexer.stray_closers == 1
    assert lexer.parse_object() == 7


def test_balanced_dict_reports_no_stray_closer():
    lexer = PDFLexer(b'<< /URI (http://example.test/(a)) /S /URI >>')
    assert lexer.parse_object() == {'URI': b'http://example.test/(a)', 'S': 'URI'}
    assert lexer.stray_closers == 0


@pytest.mark.parametrize('source', [
    b'<< /URI (a) b /S /URI >>',
    b'<< /URI (a) ] /S /URI >>',
    b'<< /A 1 (s) >>',
    b'<< /A 1 ) /B 2 >>',
    b'<< ) /A 1 >>',
])
def test_dict_still_rejects_other_tokens_at_key_position(source):
    with pytest.raises(PDFSyntaxError):
        PDFLexer(source).parse_object()


def _link_pdf(action):
    content = b'BT /F1 10 Tf 100 700 Td (example) Tj ET'
    objects = _minimal_objects(content)
    objects[3] = ('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
                  '/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R /Annots [6 0 R] >>')
    objects[6] = ('<< /Type /Annot /Subtype /Link /Rect [99 696 137 712] /Border [0 0 0] '
                  '/A %s /H /I >>' % action)
    return _build_pdf(objects)


def test_link_with_unescaped_closing_paren_is_recovered_with_warning(tmp_path):
    path = tmp_path / 'stray.pdf'
    path.write_bytes(_link_pdf('<< /URI (http://example.test/a)) /S /URI >>'))
    converted = Dochan(str(path))
    markdown = converted.to_markdown()
    assert '[example](http://example.test/a)' in markdown
    assert not any('파싱 실패' in message for message in converted.errors)
    stray = [message for message in converted.errors if "짝 없는 ')'" in message]
    assert len(stray) == 1 and stray[0].startswith('WARN: 객체 6')


def test_well_formed_link_has_no_stray_paren_warning(tmp_path):
    path = tmp_path / 'clean.pdf'
    path.write_bytes(_link_pdf('<< /URI (http://example.test/a) /S /URI >>'))
    converted = Dochan(str(path))
    assert '[example](http://example.test/a)' in converted.to_markdown()
    assert not any("짝 없는 ')'" in message for message in converted.errors)
