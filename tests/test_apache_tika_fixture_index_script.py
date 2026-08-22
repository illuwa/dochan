import json
import sys

import pytest

from scripts.build_apache_tika_fixture_index import (
    APACHE_TIKA_BRANCH,
    APACHE_TIKA_TEST_DOCUMENTS_DIR,
    apache_tika_entry_to_fixture,
    build_apache_tika_fixture_index,
    fetch_github_directory,
    github_contents_url,
)


@pytest.mark.parametrize("url", ["http://api.github.com/repos/apache/tika", "file:///etc/passwd"])
def test_fetch_github_directory_rejects_non_github_https_urls(url, monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not open")),
    )

    with pytest.raises(ValueError, match="GitHub HTTPS API"):
        fetch_github_directory(url)


def test_github_contents_url_targets_tika_test_documents_directory():
    assert github_contents_url("tests/docs", "branch") == (
        "https://api.github.com/repos/apache/tika/contents/tests/docs?ref=branch"
    )


def test_default_tika_directory_points_to_microsoft_test_documents():
    assert "tika-parser-microsoft-module" in APACHE_TIKA_TEST_DOCUMENTS_DIR
    assert APACHE_TIKA_TEST_DOCUMENTS_DIR.endswith("src/test/resources/test-documents")


def test_apache_tika_entry_to_fixture_keeps_license_and_source_path():
    fixture = apache_tika_entry_to_fixture(
        {
            "name": "Example.docx",
            "type": "file",
            "download_url": f"https://raw.githubusercontent.com/apache/tika/{APACHE_TIKA_BRANCH}/tests/docs/Example.docx",
        },
        {"docx"},
        "tests/docs",
        source_revision=APACHE_TIKA_BRANCH,
    )

    assert fixture == {
        "name": "Example.docx",
        "source_name": "tests/docs/Example.docx",
        "format": "docx",
        "url": f"https://raw.githubusercontent.com/apache/tika/{APACHE_TIKA_BRANCH}/tests/docs/Example.docx",
        "source": "apache/tika",
        "source_revision": APACHE_TIKA_BRANCH,
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    }


def test_apache_tika_entry_to_fixture_ignores_directories_missing_urls_and_unrequested_formats():
    assert apache_tika_entry_to_fixture({"name": "Example.docx", "type": "dir"}, {"docx"}, "tests") == {}
    assert apache_tika_entry_to_fixture({"name": "Example.docx", "type": "file"}, {"docx"}, "tests") == {}
    assert apache_tika_entry_to_fixture(
        {"name": "Example.pptx", "type": "file", "download_url": "https://example.test/Example.pptx"},
        {"docx"},
        "tests",
    ) == {}


def test_build_apache_tika_fixture_index_filters_formats_and_sorts():
    revision = "1" * 40
    entries = [
        {"name": "z.xlsx", "type": "file", "download_url": f"https://raw.githubusercontent.com/apache/tika/{revision}/tests/docs/z.xlsx"},
        {"name": "a.docx", "type": "file", "download_url": f"https://raw.githubusercontent.com/apache/tika/{revision}/tests/docs/a.docx"},
        {"name": "ignore.pdf", "type": "file", "download_url": f"https://raw.githubusercontent.com/apache/tika/{revision}/tests/docs/ignore.pdf"},
    ]
    seen_urls = []

    def fake_fetch(url):
        seen_urls.append(url)
        return entries

    index = build_apache_tika_fixture_index(
        ["xlsx", "docx"],
        branch=revision,
        directory="tests/docs",
        fetch_directory=fake_fetch,
    )

    assert seen_urls == [f"https://api.github.com/repos/apache/tika/contents/tests/docs?ref={revision}"]
    assert index["counts"] == {"docx": 1, "xlsx": 1}
    assert [(item["format"], item["source_name"]) for item in index["fixtures"]] == [
        ("docx", "tests/docs/a.docx"),
        ("xlsx", "tests/docs/z.xlsx"),
    ]
    assert {item["source_revision"] for item in index["fixtures"]} == {revision}


def test_apache_tika_fixture_rejects_download_url_for_a_different_revision():
    with pytest.raises(ValueError, match="source revision"):
        apache_tika_entry_to_fixture(
            {
                "name": "Example.docx",
                "type": "file",
                "download_url": "https://raw.githubusercontent.com/apache/tika/{}/tests/Example.docx".format(
                    "2" * 40
                ),
            },
            {"docx"},
            "tests",
            source_revision="1" * 40,
        )


def test_apache_tika_fixture_rejects_download_url_for_a_different_path():
    revision = "1" * 40
    with pytest.raises(ValueError, match="source path"):
        apache_tika_entry_to_fixture(
            {
                "name": "Expected.docx",
                "type": "file",
                "download_url": (
                    "https://raw.githubusercontent.com/apache/tika/{}/"
                    "other/Different.docx"
                ).format(revision),
            },
            {"docx"},
            "expected/dir",
            source_revision=revision,
        )


def test_build_apache_tika_fixture_index_cli_writes_json(tmp_path, monkeypatch):
    from scripts import build_apache_tika_fixture_index as script

    def fake_index(formats, branch, directory):
        return {
            "source": "apache/tika",
            "branch": branch,
            "directories": [directory],
            "fixtures": [{"name": "a.docx", "format": "docx"}],
            "counts": {"docx": 1},
        }

    monkeypatch.setattr(script, "build_apache_tika_fixture_index", fake_index)
    output = tmp_path / "apache-tika-fixtures.json"
    monkeypatch.setattr(sys, "argv", [
        "build_apache_tika_fixture_index.py",
        str(output),
        "--formats",
        "docx",
        "--branch",
        "branch",
        "--directory",
        "tests/docs",
    ])

    assert script.main() == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["source"] == "apache/tika"
    assert payload["counts"] == {"docx": 1}
