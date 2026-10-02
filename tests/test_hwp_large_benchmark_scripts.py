"""합성 벤치마크가 공개 API와 실제 입력 경로를 거치는지 검증한다."""
import json

from scripts import benchmark_hwp_large_limits as benchmark


def test_resource_benchmark_retains_public_api_outputs(monkeypatch):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_RECORDS", 20)
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_RECORDS", 26)
    monkeypatch.setattr("dochan.hwp.doc_info.MAX_HWP_RECORDS", 4)
    row = benchmark.measure("docinfo_and_document_records_over_limit")
    assert row["api"] == "Dochan -> to_markdown -> to_json"
    assert row["char_shapes"] == 4
    assert row["elements"] == 13
    assert row["json"]["characters"] > row["markdown"]["characters"] > 0
    assert row["peak_rss_bytes"] > 0
    assert any("document record count" in error for error in row["errors"])


def test_synthetic_ole_runs_real_public_reader_and_serializers():
    from scripts.probe_hwp_corrupt_sections import deflate, parse_public, section, streams

    reader, markdown, serialized, stats = parse_public(streams([deflate(section("tail"))]))
    assert reader.doc.sections[0].elements[0].text == "tail"
    assert "tail" in markdown
    assert json.loads(serialized)["sections"][0]["elements"][0]["text"] == "tail"
    assert not reader.errors
    assert stats["seconds"] >= stats["parse_seconds"]


def test_distribution_synthetic_fixture_is_actually_encrypted():
    from dochan.hwp.distdoc import decode_distribution_section
    from dochan.utils.safe_decompress import safe_zlib_decompress
    from scripts.probe_hwp_corrupt_sections import distribution_stream, section

    body = section("encrypted")
    encoded = distribution_stream(body, bad_checksum=False)
    assert body not in encoded
    decoded = decode_distribution_section(encoded, is_compressed=True)
    assert safe_zlib_decompress(decoded) == body


def test_link_resource_cases_retain_links_and_docinfo(monkeypatch):
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_RECORDS", 20)
    monkeypatch.setattr("dochan.hwp.section.MAX_HWP_DOCUMENT_RECORDS", 26)
    monkeypatch.setattr("dochan.hwp.doc_info.MAX_HWP_RECORDS", 4)
    for case, links, shapes, sections in (
        ("links_at_limit", 18, 0, 1),
        ("links_and_docinfo_at_document_limit", 22, 4, 2),
    ):
        row = benchmark.measure(case)
        assert row["api"] == "Dochan -> to_markdown -> to_json"
        assert row["link_runs"] == links
        assert row["char_shapes"] == shapes
        assert row["retained_sections"] == sections
        assert row["markdown"]["characters"] > 0
        assert row["json"]["characters"] > 0
        assert row["errors"] == []
