import json
import sys

from scripts.build_github_ooxml_fixture_index import (
    build_github_ooxml_fixture_index,
    github_contents_url,
    github_entry_to_fixture,
)


def test_github_contents_url_targets_repo_directory_and_ref():
    assert github_contents_url("owner/repo", "tests/files", "main") == (
        "https://api.github.com/repos/owner/repo/contents/tests/files?ref=main"
    )


def test_github_entry_to_fixture_keeps_license_source_and_unique_name():
    source = {
        "repo": "owner/repo",
        "ref": "main",
        "license": "MIT",
        "license_url": "https://example.test/license",
    }

    fixture = github_entry_to_fixture(
        {
            "name": "Example.docx",
            "type": "file",
            "download_url": "https://raw.githubusercontent.com/owner/repo/main/tests/Example.docx",
        },
        source,
        "tests/files",
        {"docx"},
    )

    assert fixture == {
        "name": "owner__repo__tests__files__Example.docx",
        "source_name": "tests/files/Example.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/owner/repo/main/tests/Example.docx",
        "source": "owner/repo",
        "license": "MIT",
        "license_url": "https://example.test/license",
    }


def test_github_entry_to_fixture_ignores_directories_missing_urls_and_unrequested_formats():
    source = {"repo": "owner/repo", "ref": "main", "license": "MIT", "license_url": "https://example.test"}

    assert github_entry_to_fixture({"name": "Example.docx", "type": "dir"}, source, "tests", {"docx"}) == {}
    assert github_entry_to_fixture({"name": "Example.docx", "type": "file"}, source, "tests", {"docx"}) == {}
    assert github_entry_to_fixture(
        {"name": "Example.pptx", "type": "file", "download_url": "https://example.test/Example.pptx"},
        source,
        "tests",
        {"docx"},
    ) == {}


def test_build_github_ooxml_fixture_index_filters_formats_and_sorts():
    source = {
        "repo": "owner/repo",
        "ref": "main",
        "directories": ["b", "a"],
        "formats": ["docx", "xlsx"],
        "license": "MIT",
        "license_url": "https://example.test/license",
    }
    responses = {
        "b": [
            {"name": "z.xlsx", "type": "file", "download_url": "https://example.test/z.xlsx"},
            {"name": "ignore.pptx", "type": "file", "download_url": "https://example.test/ignore.pptx"},
        ],
        "a": [
            {"name": "a.docx", "type": "file", "download_url": "https://example.test/a.docx"},
        ],
    }
    seen_urls = []

    def fake_fetch(url):
        seen_urls.append(url)
        directory = url.split("/contents/")[1].split("?")[0]
        return responses[directory]

    index = build_github_ooxml_fixture_index(["xlsx", "docx"], sources=[source], fetch_directory=fake_fetch)

    assert seen_urls == [
        "https://api.github.com/repos/owner/repo/contents/b?ref=main",
        "https://api.github.com/repos/owner/repo/contents/a?ref=main",
    ]
    assert index["counts"] == {"docx": 1, "xlsx": 1}
    assert [(item["format"], item["source_name"]) for item in index["fixtures"]] == [
        ("docx", "a/a.docx"),
        ("xlsx", "b/z.xlsx"),
    ]
    assert index["sources"] == [{"repo": "owner/repo", "ref": "main", "count": 2}]


def test_build_github_ooxml_fixture_index_cli_writes_json(tmp_path, monkeypatch):
    from scripts import build_github_ooxml_fixture_index as script

    def fake_index(formats):
        return {
            "source": "github-ooxml-fixtures",
            "fixtures": [{"name": "a.docx", "format": "docx"}],
            "counts": {"docx": 1},
        }

    monkeypatch.setattr(script, "build_github_ooxml_fixture_index", fake_index)
    output = tmp_path / "github-ooxml-fixtures.json"
    monkeypatch.setattr(sys, "argv", [
        "build_github_ooxml_fixture_index.py",
        str(output),
        "--formats",
        "docx",
    ])

    assert script.main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"] == "github-ooxml-fixtures"
    assert payload["counts"] == {"docx": 1}
