"""Excel TEXT 캐시 프로브는 불리언을 숫자 서식기에 보내지 않는다."""

import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from scripts import probe_chart_review_text_cache as probe


def test_text_cache_probe_preserves_boolean_input_type(tmp_path, monkeypatch):
    """합성 OOXML: 불리언 저장값은 숫자가 아닌 TRUE 텍스트로 표시한다."""
    monkeypatch.setattr(probe, "FILES", ("boolean.xlsx",))
    with ZipFile(tmp_path / "boolean.xlsx", "w") as archive:
        archive.writestr("xl/workbook.xml", '''
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>
        ''')
        archive.writestr("xl/worksheets/sheet1.xml", '''
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData><row r="1">
                <c r="A1" t="b"><v>1</v></c>
                <c r="B1" t="inlineStr"><is><t>0.00</t></is></c>
                <c r="C1" t="str"><f>TEXT(A1,B1)</f><v>TRUE</v></c>
              </row></sheetData>
            </worksheet>
        ''')
    output = tmp_path / "results.json"
    probe.snapshot(SimpleNamespace(corpus=tmp_path, tree=Path.cwd(), output=output))
    row = json.loads(output.read_text())[0]
    assert row["input_type"] == "b"
    assert row["actual"] == "TRUE"
