import json
import sys

import pytest

from scripts.build_apache_poi_fixture_index import (
    APACHE_POI_BRANCH,
    APACHE_POI_LICENSE_URL,
    fetch_github_directory,
    apache_poi_entry_to_fixture,
    build_apache_poi_fixture_index,
)


@pytest.mark.parametrize("url", ["http://api.github.com/repos/apache/poi", "file:///etc/passwd"])
def test_fetch_github_directory_rejects_non_github_https_urls(url, monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not open")),
    )

    with pytest.raises(ValueError, match="GitHub HTTPS API"):
        fetch_github_directory(url)


def test_apache_poi_entry_to_fixture_keeps_license_and_source_metadata():
    fixture = apache_poi_entry_to_fixture(
        {
            "name": "Example.docx",
            "download_url": f"https://raw.githubusercontent.com/apache/poi/{APACHE_POI_BRANCH}/test-data/document/Example.docx",
        },
        "docx",
    )

    assert fixture == {
        "name": "Example.docx",
        "source_name": "Example.docx",
        "format": "docx",
        "url": f"https://raw.githubusercontent.com/apache/poi/{APACHE_POI_BRANCH}/test-data/document/Example.docx",
        "source": "apache/poi",
        "source_revision": APACHE_POI_BRANCH,
        "license": "Apache-2.0",
        "license_url": APACHE_POI_LICENSE_URL,
    }


def test_build_apache_poi_fixture_index_filters_formats_and_sorts():
    revision = "1" * 40
    responses = {
        "document": [
            {"name": "z.docx", "download_url": f"https://raw.githubusercontent.com/apache/poi/{revision}/test-data/document/z.docx"},
            {"name": "ignore.doc", "download_url": f"https://raw.githubusercontent.com/apache/poi/{revision}/test-data/document/ignore.doc"},
            {"name": "a.docx", "download_url": f"https://raw.githubusercontent.com/apache/poi/{revision}/test-data/document/a.docx"},
        ],
        "spreadsheet": [
            {"name": "b.xlsx", "download_url": f"https://raw.githubusercontent.com/apache/poi/{revision}/test-data/spreadsheet/b.xlsx"},
            {"name": "missing-url.xlsx"},
        ],
    }
    seen_urls = []

    def fake_fetch(url):
        seen_urls.append(url)
        directory = url.split("/test-data/")[1].split("?")[0]
        return responses[directory]

    index = build_apache_poi_fixture_index(["xlsx", "docx"], branch=revision, fetch_directory=fake_fetch)

    assert seen_urls == [
        f"https://api.github.com/repos/apache/poi/contents/test-data/spreadsheet?ref={revision}",
        f"https://api.github.com/repos/apache/poi/contents/test-data/document?ref={revision}",
    ]
    assert index["counts"] == {"docx": 2, "xlsx": 1}
    assert [(item["format"], item["source_name"]) for item in index["fixtures"]] == [
        ("docx", "a.docx"),
        ("docx", "z.docx"),
        ("xlsx", "b.xlsx"),
    ]
    assert {item["source_revision"] for item in index["fixtures"]} == {revision}


def test_apache_poi_fixture_rejects_download_url_for_a_different_revision():
    with pytest.raises(ValueError, match="source revision"):
        apache_poi_entry_to_fixture(
            {
                "name": "Example.docx",
                "download_url": "https://raw.githubusercontent.com/apache/poi/{}/test-data/document/Example.docx".format(
                    "2" * 40
                ),
            },
            "docx",
            source_revision="1" * 40,
        )


def test_apache_poi_fixture_rejects_download_url_for_a_different_path():
    revision = "1" * 40
    with pytest.raises(ValueError, match="source path"):
        apache_poi_entry_to_fixture(
            {
                "name": "Expected.docx",
                "download_url": (
                    "https://raw.githubusercontent.com/apache/poi/{}/"
                    "test-data/spreadsheet/Different.docx"
                ).format(revision),
            },
            "docx",
            source_revision=revision,
        )


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
