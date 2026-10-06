"""scripts/probe_output_speed.py — 출력 해시·단계 시간 수집과 대조."""
import json
import zipfile

from scripts.probe_output_speed import collect, collect_paths, compare_records, differences, main

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _write_xlsx(path, value):
    workbook = ('<workbook xmlns="{}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>').format(NS)
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
    sheet = ('<worksheet xmlns="{}"><sheetData><row r="1"><c r="A1"><v>{}</v></c></row></sheetData></worksheet>'
             ).format(NS, value)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def test_collect_paths_keeps_supported_regular_files_only(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / ".hidden").mkdir()
    _write_xlsx(tmp_path / "a" / "one.XLSX", 1)
    (tmp_path / "a" / "notes.txt").write_text("skip")
    _write_xlsx(tmp_path / ".hidden" / "two.xlsx", 2)
    (tmp_path / "a" / "link.xlsx").symlink_to(tmp_path / "a" / "one.XLSX")
    assert collect_paths([str(tmp_path)]) == [str(tmp_path / "a" / "one.XLSX")]


def test_collect_records_hashes_and_stage_times(tmp_path):
    _write_xlsx(tmp_path / "one.xlsx", 7)
    _write_xlsx(tmp_path / "two.xlsx", 8)
    result = collect([str(tmp_path)], workers=1)
    records = result["records"]
    assert sorted(records) == [str(tmp_path / "one.xlsx"), str(tmp_path / "two.xlsx")]
    one, two = records[str(tmp_path / "one.xlsx")], records[str(tmp_path / "two.xlsx")]
    assert "failure" not in one and one["json_fallbacks"] == 0
    assert all(one[stage] >= 0 for stage in ("parse", "markdown", "json", "text"))
    assert len(one["json_sha256"]) == 64 and one["json_sha256"] != two["json_sha256"]
    assert one["errors_sha256"] == two["errors_sha256"]


def test_compare_flags_hash_changes_failures_missing_and_fallbacks():
    base = {"markdown_sha256": "m", "json_sha256": "j", "text_sha256": "t", "errors_sha256": "e",
            "parse": 1.0, "markdown": 0.5, "json": 2.0, "text": 0.25}
    before = {"a.xlsx": dict(base), "b.xlsx": dict(base), "c.pdf": {"failure": "parse:ValueError"},
              "d.pdf": dict(base), "e.hwp": dict(base)}
    after = {"a.xlsx": dict(base, json=0.5), "b.xlsx": dict(base, json_sha256="changed"),
             "c.pdf": {"failure": "parse:ValueError"}, "d.pdf": {"failure": "timeout:json"}}
    summary = compare_records(before, after)
    assert summary["xlsx"]["files"] == 2 and summary["xlsx"]["json_sha256"] == 1
    assert summary["xlsx"]["before_json"] == 4.0 and summary["xlsx"]["after_json"] == 2.5
    assert summary["pdf"]["both_failed"] == 1 and summary["pdf"]["failure_changed"] == 1
    assert summary["hwp"]["missing"] == 1
    assert differences(summary) == 3
    same = compare_records({"a.xlsx": dict(base)}, {"a.xlsx": dict(base, json=0.1)})
    assert differences(same) == 0
    assert differences(compare_records({"a.xlsx": dict(base)}, {"a.xlsx": dict(base, json_fallbacks=2)})) == 2


def test_cli_collect_then_compare_reports_identical_outputs(tmp_path, capsys):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _write_xlsx(corpus / "one.xlsx", 3)
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert main(["collect", str(corpus), "--output", str(first)]) == 0
    assert main(["collect", str(corpus), "--output", str(second)]) == 0
    assert json.loads(first.read_text(encoding="utf-8"))["workers"] == 1
    assert main(["compare", str(first), str(second)]) == 0
    assert "xlsx" in capsys.readouterr().out
