"""The corpus probe counts only tables between text in their own paragraph."""
import zipfile

from scripts.probe_hwpx_float_table import inspect


def test_probe_distinguishes_floating_inline_and_nested_tables(tmp_path):
    path = tmp_path / 'sample.hwpx'
    namespace = ('xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
                 'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"')
    floating = ('<hp:tbl textWrap="SQUARE"><hp:pos treatAsChar="0" '
                'vertRelTo="PARA" horzRelTo="COLUMN"/></hp:tbl>')
    inline = ('<hp:tbl textWrap="TOP_AND_BOTTOM"><hp:pos treatAsChar="1" '
              'vertRelTo="PARA" horzRelTo="PARA"/></hp:tbl>')
    nested = ('<hp:tbl><hp:tr><hp:tc><hp:subList><hp:p><hp:run>'
              '<hp:t>셀 앞</hp:t>%s<hp:t>셀 뒤</hp:t>'
              '</hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl>') % inline
    section = ('<hs:sec %s><hp:p><hp:run><hp:t>앞</hp:t>%s<hp:t>뒤</hp:t>'
               '</hp:run></hp:p><hp:p><hp:run>%s</hp:run></hp:p></hs:sec>') % (
                   namespace, floating, nested)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('Contents/section0.xml', section)
        archive.writestr('Preview/PrvText.txt', '앞뒤')

    rows = inspect(path)
    assert len(rows) == 2
    assert rows[0]['attrs'] == {
        'vertRelTo': 'PARA', 'horzRelTo': 'COLUMN',
        'treatAsChar': '0', 'textWrap': 'SQUARE'}
    assert rows[0]['preview_joined'] is True
    assert rows[1]['attrs']['treatAsChar'] == '1'
    assert rows[1]['before'] == '셀 앞'
    assert rows[1]['after'] == '셀 뒤'
