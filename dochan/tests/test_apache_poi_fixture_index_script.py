import json
import sys

from scripts.build_apache_poi_fixture_index import (
    APACHE_POI_LICENSE_URL,
    apache_poi_entry_to_fixture,
    build_apache_poi_fixture_index,
)


def test_apache_poi_entry_to_fixture_keeps_license_and_source_metadata():
    fixture = apache_poi_entry_to_fixture(
        {
            "name": "Example.docx",
            "download_url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/Example.docx",
        },
        "docx",
    )

    assert fixture == {
        "name": "Example.docx",
        "source_name": "Example.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/Example.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": APACHE_POI_LICENSE_URL,
    }


def test_build_apache_poi_fixture_index_filters_formats_and_sorts():
    responses = {
        "document": [
            {"name": "z.docx", "download_url": "https://example.test/z.docx"},
            {"name": "ignore.doc", "download_url": "https://example.test/ignore.doc"},
            {"name": "a.docx", "download_url": "https://example.test/a.docx"},
        ],
        "spreadsheet": [
            {"name": "b.xlsx", "download_url": "https://example.test/b.xlsx"},
            {"name": "missing-url.xlsx"},
        ],
    }
    seen_urls = []

    def fake_fetch(url):
        seen_urls.append(url)
        directory = url.split("/test-data/")[1].split("?")[0]
        return responses[directory]

    index = build_apache_poi_fixture_index(["xlsx", "docx"], branch="test-branch", fetch_directory=fake_fetch)

    assert seen_urls == [
        "https://api.github.com/repos/apache/poi/contents/test-data/spreadsheet?ref=test-branch",
        "https://api.github.com/repos/apache/poi/contents/test-data/document?ref=test-branch",
    ]
    assert index["counts"] == {"docx": 2, "xlsx": 1}
    assert [(item["format"], item["source_name"]) for item in index["fixtures"]] == [
        ("docx", "a.docx"),
        ("docx", "z.docx"),
        ("xlsx", "b.xlsx"),
    ]


def test_build_apache_poi_fixture_index_cli_writes_json(tmp_path, monkeypatch):
    from scripts import build_apache_poi_fixture_index as script

    def fake_index(formats, branch):
        return {
            "source": "apache/poi",
            "branch": branch,
            "fixtures": [{"name": "a.docx", "format": "docx"}],
            "counts": {"docx": 1},
        }

    monkeypatch.setattr(script, "build_apache_poi_fixture_index", fake_index)
    output = tmp_path / "apache-poi-fixtures.json"
    monkeypatch.setattr(sys, "argv", [
        "build_apache_poi_fixture_index.py",
        str(output),
        "--formats",
        "docx",
        "--branch",
        "test-branch",
    ])

    assert script.main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["branch"] == "test-branch"
    assert payload["counts"] == {"docx": 1}
