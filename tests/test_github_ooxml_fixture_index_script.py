import json
import sys

import pytest

from scripts.build_github_ooxml_fixture_index import (
    build_github_ooxml_fixture_index,
    fetch_github_directory,
    github_contents_url,
    github_entry_to_fixture,
)


@pytest.mark.parametrize("url", ["http://api.github.com/repos/owner/repo", "file:///etc/passwd"])
def test_fetch_github_directory_rejects_non_github_https_urls(url, monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not open")),
    )

    with pytest.raises(ValueError, match="GitHub HTTPS API"):
        fetch_github_directory(url)


def test_github_contents_url_targets_repo_directory_and_ref():
    assert github_contents_url("owner/repo", "tests/files", "main") == (
        "https://api.github.com/repos/owner/repo/contents/tests/files?ref=main"
    )


def test_github_entry_to_fixture_keeps_license_source_and_unique_name():
    revision = "1" * 40
    source = {
        "repo": "owner/repo",
        "ref": revision,
        "license": "MIT",
        "license_url": "https://example.test/license",
    }

    fixture = github_entry_to_fixture(
        {
            "name": "Example.docx",
            "type": "file",
            "download_url": f"https://raw.githubusercontent.com/owner/repo/{revision}/tests/files/Example.docx",
        },
        source,
        "tests/files",
        {"docx"},
    )

    assert fixture == {
        "name": "owner__repo__tests__files__Example.docx",
        "source_name": "tests/files/Example.docx",
        "format": "docx",
        "url": f"https://raw.githubusercontent.com/owner/repo/{revision}/tests/files/Example.docx",
        "source": "owner/repo",
        "source_revision": revision,
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
    revision = "1" * 40
    source = {
        "repo": "owner/repo",
        "ref": revision,
        "directories": ["b", "a"],
        "formats": ["docx", "xlsx"],
        "license": "MIT",
        "license_url": "https://example.test/license",
    }
    responses = {
        "b": [
            {"name": "z.xlsx", "type": "file", "download_url": f"https://raw.githubusercontent.com/owner/repo/{revision}/b/z.xlsx"},
            {"name": "ignore.pptx", "type": "file", "download_url": f"https://raw.githubusercontent.com/owner/repo/{revision}/b/ignore.pptx"},
        ],
        "a": [
            {"name": "a.docx", "type": "file", "download_url": f"https://raw.githubusercontent.com/owner/repo/{revision}/a/a.docx"},
        ],
    }
    seen_urls = []

    def fake_fetch(url):
        seen_urls.append(url)
        directory = url.split("/contents/")[1].split("?")[0]
        return responses[directory]

    index = build_github_ooxml_fixture_index(["xlsx", "docx"], sources=[source], fetch_directory=fake_fetch)

    assert seen_urls == [
        f"https://api.github.com/repos/owner/repo/contents/b?ref={revision}",
        f"https://api.github.com/repos/owner/repo/contents/a?ref={revision}",
    ]
    assert index["counts"] == {"docx": 1, "xlsx": 1}
    assert [(item["format"], item["source_name"]) for item in index["fixtures"]] == [
        ("docx", "a/a.docx"),
        ("xlsx", "b/z.xlsx"),
    ]
    assert index["sources"] == [{"repo": "owner/repo", "ref": revision, "count": 2}]
    assert {item["source_revision"] for item in index["fixtures"]} == {revision}


def test_github_fixture_rejects_download_url_for_a_different_revision():
    source = {
        "repo": "owner/repo",
        "ref": "1" * 40,
        "license": "MIT",
        "license_url": "https://example.test/license",
    }

    with pytest.raises(ValueError, match="source revision"):
        github_entry_to_fixture(
            {
                "name": "Example.docx",
                "type": "file",
                "download_url": "https://raw.githubusercontent.com/owner/repo/{}/tests/Example.docx".format(
                    "2" * 40
                ),
            },
            source,
            "tests",
            {"docx"},
        )


def test_github_fixture_rejects_download_url_for_a_different_path():
    revision = "1" * 40
    source = {
        "repo": "owner/repo",
        "ref": revision,
        "license": "MIT",
        "license_url": "https://example.test/license",
    }

    with pytest.raises(ValueError, match="source path"):
        github_entry_to_fixture(
            {
                "name": "Expected.docx",
                "type": "file",
                "download_url": (
                    "https://raw.githubusercontent.com/owner/repo/{}/"
                    "other/Different.docx"
                ).format(revision),
            },
            source,
            "expected/dir",
            {"docx"},
        )


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
