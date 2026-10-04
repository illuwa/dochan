"""Public corpus diagnostic probe keeps messages and only output hashes."""
import json

from scripts.probe_error_sweep import message_template, public_files, summarize


def test_message_template_groups_variable_page_numbers_and_preserves_reason():
    assert message_template("WARN: 12페이지: 텍스트 없음") == "WARN: #페이지: 텍스트 없음"
    assert message_template("ERR: Error -3 while decompressing data") == (
        "ERR: Error -# while decompressing data")


def test_summarize_counts_messages_and_samples_by_distinct_file(tmp_path):
    records = [
        {"root": 0, "file": "one.pdf", "format": "pdf",
         "errors": ["WARN: 2페이지", "WARN: 3페이지"], "exception": None},
        {"root": 0, "file": "two.pdf", "format": "pdf",
         "errors": ["WARN: 4페이지"], "exception": None},
    ]
    output = tmp_path / "result.jsonl"
    output.write_text("\n".join(json.dumps(item) for item in records) + "\n",
                      encoding="utf-8")
    result = summarize(output)
    assert result["files"] == {"pdf": 2}
    assert result["affected_files"] == {"pdf": 2}
    assert result["templates"][0]["count"] == 3
    assert [item["file"] for item in result["templates"][0]["samples"]] == [
        "one.pdf", "two.pdf"]


def test_public_files_limits_to_supported_format(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"")
    (tmp_path / "b.docx").write_bytes(b"")
    (tmp_path / "c.txt").write_bytes(b"")
    assert [item[2].name for item in public_files([tmp_path], {".pdf"})] == [
        "a.pdf"]
