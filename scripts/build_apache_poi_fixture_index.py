"""Build a JSON fixture index from Apache POI OOXML test-data directories."""
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


APACHE_POI_BRANCH = "379bcdcc4cfe9d899eabc2e226a1322161413c7f"
APACHE_POI_LICENSE = "Apache-2.0"
APACHE_POI_LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt"
APACHE_POI_REPO_API = "https://api.github.com/repos/apache/poi/contents/test-data/{directory}?ref={branch}"
APACHE_POI_TEST_DATA_DIRS = {
    "docx": "document",
    "pptx": "slideshow",
    "xlsx": "spreadsheet",
}


def fetch_github_directory(url: str) -> List[dict]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("Apache POI fixture index URL must use the GitHub HTTPS API")
    with urllib.request.urlopen(  # nosemgrep: dynamic-urllib-use-detected
        url,
        timeout=30,
    ) as response:
        return json.load(response)


def build_apache_poi_fixture_index(
    formats: Iterable[str] = APACHE_POI_TEST_DATA_DIRS,
    branch: str = APACHE_POI_BRANCH,
    fetch_directory: Callable[[str], List[dict]] = fetch_github_directory,
) -> dict:
    _validate_immutable_revision(branch)
    requested = [fmt.lower().lstrip(".") for fmt in formats]
    fixtures = []

    for file_format in requested:
        directory = APACHE_POI_TEST_DATA_DIRS[file_format]
        url = APACHE_POI_REPO_API.format(directory=directory, branch=branch)
        entries = fetch_directory(url)
        for entry in entries:
            fixture = apache_poi_entry_to_fixture(
                entry,
                file_format,
                source_revision=branch,
            )
            if fixture:
                fixtures.append(fixture)

    return {
        "source": "apache/poi",
        "branch": branch,
        "fixtures": sorted(fixtures, key=lambda item: (item["format"], item["source_name"])),
        "counts": fixture_counts(fixtures),
    }


def apache_poi_entry_to_fixture(
    entry: dict,
    file_format: str,
    source_revision: str = APACHE_POI_BRANCH,
) -> dict:
    name = str(entry.get("name", ""))
    if not name.lower().endswith(f".{file_format}"):
        return {}
    download_url = entry.get("download_url")
    if not download_url:
        return {}
    _validate_immutable_revision(source_revision)
    _validate_download_url(download_url, source_revision, file_format, name)
    return {
        "name": name,
        "source_name": name,
        "format": file_format,
        "url": download_url,
        "source": "apache/poi",
        "source_revision": source_revision,
        "license": APACHE_POI_LICENSE,
        "license_url": APACHE_POI_LICENSE_URL,
    }


def _validate_immutable_revision(revision: str) -> None:
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Apache POI source revision must be an immutable 40-character commit")


def _validate_download_url(
    url: str,
    revision: str,
    file_format: str,
    name: str,
) -> None:
    parsed = urlsplit(str(url))
    expected_prefix = "/apache/poi/{}/".format(revision)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "raw.githubusercontent.com"
        or not unquote(parsed.path).startswith(expected_prefix)
    ):
        raise ValueError("Apache POI download URL does not match its source revision")
    directory = APACHE_POI_TEST_DATA_DIRS[file_format]
    expected_path = "/apache/poi/{}/test-data/{}/{}".format(
        revision,
        directory,
        name,
    )
    if unquote(parsed.path) != expected_path or parsed.query or parsed.fragment:
        raise ValueError("Apache POI download URL does not match its source path")


def fixture_counts(fixtures: Iterable[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for fixture in fixtures:
        counts[fixture["format"]] = counts.get(fixture["format"], 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an Apache POI OOXML fixture index JSON file.")
    parser.add_argument("output", type=Path, help="Path to write fixture index JSON")
    parser.add_argument("--formats", default="docx,pptx,xlsx", help="Comma-separated extensions")
    parser.add_argument("--branch", default=APACHE_POI_BRANCH, help="Apache POI git branch or ref")
    args = parser.parse_args()

    formats = [item.strip() for item in args.formats.split(",") if item.strip()]
    index = build_apache_poi_fixture_index(formats=formats, branch=args.branch)
    atomic_write_text(
        args.output,
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps({"output": str(args.output), "counts": index["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
