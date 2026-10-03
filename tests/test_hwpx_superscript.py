"""HWPX charPr 의 위·아래 첨자(<hh:supscript/>·<hh:subscript/>)를 런 서식으로 읽는다.

공개 정책브리핑 보도자료 156784175 의 `파악됐다*` 의 `*` 는 HWPX charPr 39 가 위 첨자이고, 같은 문서 HWP 출력은 `<sup>*</sup>` 다.
"""
import zipfile

from dochan.hwpx.parser import HWPXParser
from dochan.output.markdown import to_markdown

NS = ('xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
      'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
      'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head"')


def _document(tmp_path):
    header = ('<hh:head %s><hh:refList><hh:charProperties>'
              '<hh:charPr id="1" height="1000"/>'
              '<hh:charPr id="2" height="1000"><hh:supscript/></hh:charPr>'
              '<hh:charPr id="3" height="1000"><hh:subscript/></hh:charPr>'
              '</hh:charProperties></hh:refList></hh:head>') % NS
    body = ('<hp:p><hp:run charPrIDRef="1"><hp:t>파악됐다</hp:t></hp:run>'
            '<hp:run charPrIDRef="2"><hp:t>*</hp:t></hp:run>'
            '<hp:run charPrIDRef="1"><hp:t>. H</hp:t></hp:run>'
            '<hp:run charPrIDRef="3"><hp:t>2</hp:t></hp:run>'
            '<hp:run charPrIDRef="1"><hp:t>O</hp:t></hp:run></hp:p>')
    path = tmp_path / 'sup.hwpx'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/hwp+zip')
        archive.writestr('Contents/header.xml', header)
        archive.writestr('Contents/section0.xml', '<hs:sec %s>%s</hs:sec>' % (NS, body))
    return HWPXParser().parse(path, include_assets=False)


def test_supscript_and_subscript_become_run_formatting(tmp_path):
    runs = _document(tmp_path).sections[0].elements[0].runs
    assert [(run.text, run.superscript, run.subscript) for run in runs] == [
        ('파악됐다', False, False), ('*', True, False), ('. H', False, False),
        ('2', False, True), ('O', False, False)]


def test_superscript_markdown_matches_hwp_contract(tmp_path):
    markdown = to_markdown(_document(tmp_path))
    assert '파악됐다<sup>*</sup>. H<sub>2</sub>O' in markdown
