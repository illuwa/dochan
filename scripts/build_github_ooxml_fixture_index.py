"""Build a license-tagged OOXML fixture index from selected GitHub repositories."""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, List
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.download_public_ooxml_corpus import atomic_write_text  # noqa: E402


GITHUB_OOXML_SOURCES = [
    {
        "repo": "python-openxml/python-docx",
        "ref": "e45454602b53e8e572b179ccf1c91093ec9f4ed7",
        "directories": ["tests/test_files", "features/steps/test_files"],
        "formats": ["docx"],
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/LICENSE",
    },
    {
        "repo": "scanny/python-pptx",
        "ref": "278b47b1dedd5b46ee84c286e77cdfb0bf4594be",
        "directories": ["tests/test_files", "features/steps/test_files"],
        "formats": ["pptx"],
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "repo": "pyexcel/pyexcel",
        "ref": "0bfeee32704678a9da498d62b5c55dc8d474853e",
        "directories": ["tests/fixtures"],
        "formats": ["xlsx"],
        "license": "BSD-3-Clause",
        "license_url": "https://github.com/pyexcel/pyexcel/blob/0bfeee32704678a9da498d62b5c55dc8d474853e/LICENSE",
    },
    {
        "repo": "ChrisPappalardo/eparse",
        "ref": "039e55266aad31711954be4d6fb74f3765104207",
        "directories": ["tests"],
        "formats": ["xlsx"],
        "license": "MIT",
        "license_url": "https://github.com/ChrisPappalardo/eparse/blob/039e55266aad31711954be4d6fb74f3765104207/LICENSE",
    },
]


def fetch_github_directory(url: str) -> List[dict]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("fixture index URL must use the GitHub HTTPS API")
    with urllib.request.urlopen(  # nosemgrep: dynamic-urllib-use-detected
        url,
        timeout=30,
    ) as response:
        return json.load(response)


def github_contents_url(repo: str, directory: str, ref: str) -> str:
    return f"https://api.github.com/repos/{repo}/contents/{directory}?ref={ref}"


def build_github_ooxml_fixture_index(
    formats: Iterable[str] = ("docx", "pptx", "xlsx"),
    sources: Iterable[dict] = GITHUB_OOXML_SOURCES,
    fetch_directory: Callable[[str], List[dict]] = fetch_github_directory,
) -> dict:
    requested = {fmt.lower().lstrip(".") for fmt in formats}
    fixtures = []
    source_summaries = []

    for source in sources:
        _validate_immutable_revision(source.get("ref"))
        source_formats = {fmt.lower().lstrip(".") for fmt in source.get("formats", [])}
        active_formats = requested & source_formats
        if not active_formats:
            continue

        source_count = 0
        for directory in source.get("directories", []):
            url = github_contents_url(source["repo"], directory, source["ref"])
            for entry in fetch_directory(url):
                fixture = github_entry_to_fixture(entry, source, directory, active_formats)
                if fixture:
                    fixtures.append(fixture)
                    source_count += 1
        source_summaries.append({
            "repo": source["repo"],
            "ref": source["ref"],
            "count": source_count,
        })

    return {
        "source": "github-ooxml-fixtures",
        "sources": source_summaries,
        "fixtures": sorted(fixtures, key=lambda item: (item["format"], item["source"], item["source_name"])),
        "counts": fixture_counts(fixtures),
    }


def github_entry_to_fixture(entry: dict, source: dict, directory: str, active_formats: Iterable[str]) -> dict:
    name = str(entry.get("name", ""))
    file_format = Path(name).suffix.lower().lstrip(".")
    if file_format not in set(active_formats):
        return {}
    if entry.get("type") != "file":
        return {}
    download_url = entry.get("download_url")
    if not download_url:
        return {}

    repo = source["repo"]
    source_revision = source["ref"]
    _validate_immutable_revision(source_revision)
    _validate_download_url(
        download_url,
        repo,
        source_revision,
        directory,
        name,
    )
    source_name = f"{directory}/{name}"
    unique_name = "__".join([
        repo.replace("/", "__"),
        directory.replace("/", "__"),
        name,
    ])
    return {
        "name": unique_name,
        "source_name": source_name,
        "format": file_format,
        "url": download_url,
        "source": repo,
        "source_revision": source_revision,
        "license": source["license"],
        "license_url": source["license_url"],
    }


def _validate_immutable_revision(revision: str) -> None:
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("GitHub source revision must be an immutable 40-character commit")


def _validate_download_url(
    url: str,
    repo: str,
    revision: str,
    directory: str,
    name: str,
) -> None:
    parsed = urlsplit(str(url))
    expected_prefix = "/{}/{}/".format(repo, revision)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "raw.githubusercontent.com"
        or not unquote(parsed.path).startswith(expected_prefix)
    ):
        raise ValueError("GitHub download URL does not match its source revision")
    expected_path = "/{}/{}/{}/{}".format(
        repo,
        revision,
        directory.strip("/"),
        name,
    )
    if unquote(parsed.path) != expected_path or parsed.query or parsed.fragment:
        raise ValueError("GitHub download URL does not match its source path")


def fixture_counts(fixtures: Iterable[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for fixture in fixtures:
        counts[fixture["format"]] = counts.get(fixture["format"], 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a GitHub OOXML fixture index JSON file.")
    parser.add_argument("output", type=Path, help="Path to write fixture index JSON")
    parser.add_argument("--formats", default="docx,pptx,xlsx", help="Comma-separated extensions")
    args = parser.parse_args()

    formats = [item.strip() for item in args.formats.split(",") if item.strip()]
    index = build_github_ooxml_fixture_index(formats=formats)
    atomic_write_text(
        args.output,
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps({"output": str(args.output), "counts": index["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
