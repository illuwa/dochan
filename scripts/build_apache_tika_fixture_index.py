"""Build a JSON fixture index from Apache Tika OOXML test documents."""
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


APACHE_TIKA_BRANCH = "cf9c2c8660f9af82701d89c1824a190556774db0"
APACHE_TIKA_LICENSE = "Apache-2.0"
APACHE_TIKA_LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt"
APACHE_TIKA_REPO = "apache/tika"
APACHE_TIKA_TEST_DOCUMENTS_DIR = (
    "tika-parsers/tika-parsers-standard/tika-parsers-standard-modules/"
    "tika-parser-microsoft-module/src/test/resources/test-documents"
)


def fetch_github_directory(url: str) -> List[dict]:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("Apache Tika fixture index URL must use the GitHub HTTPS API")
    with urllib.request.urlopen(  # nosemgrep: dynamic-urllib-use-detected
        url,
        timeout=30,
    ) as response:
        return json.load(response)


def github_contents_url(directory: str = APACHE_TIKA_TEST_DOCUMENTS_DIR, branch: str = APACHE_TIKA_BRANCH) -> str:
    return f"https://api.github.com/repos/{APACHE_TIKA_REPO}/contents/{directory}?ref={branch}"


def build_apache_tika_fixture_index(
    formats: Iterable[str] = ("docx", "pptx", "xlsx"),
    branch: str = APACHE_TIKA_BRANCH,
    directory: str = APACHE_TIKA_TEST_DOCUMENTS_DIR,
    fetch_directory: Callable[[str], List[dict]] = fetch_github_directory,
) -> dict:
    _validate_immutable_revision(branch)
    requested = {fmt.lower().lstrip(".") for fmt in formats}
    url = github_contents_url(directory, branch)
    fixtures = [
        fixture
        for entry in fetch_directory(url)
        for fixture in [
            apache_tika_entry_to_fixture(
                entry,
                requested,
                directory,
                source_revision=branch,
            )
        ]
        if fixture
    ]
    return {
        "source": APACHE_TIKA_REPO,
        "branch": branch,
        "directories": [directory],
        "fixtures": sorted(fixtures, key=lambda item: (item["format"], item["source_name"])),
        "counts": fixture_counts(fixtures),
    }


def apache_tika_entry_to_fixture(
    entry: dict,
    active_formats: Iterable[str],
    directory: str,
    source_revision: str = APACHE_TIKA_BRANCH,
) -> dict:
    name = str(entry.get("name", ""))
    file_format = Path(name).suffix.lower().lstrip(".")
    if file_format not in set(active_formats):
        return {}
    if entry.get("type") != "file":
        return {}
    download_url = entry.get("download_url")
    if not download_url:
        return {}
    _validate_immutable_revision(source_revision)
    _validate_download_url(download_url, source_revision, directory, name)
    source_name = f"{directory}/{name}"
    return {
        "name": name,
        "source_name": source_name,
        "format": file_format,
        "url": download_url,
        "source": APACHE_TIKA_REPO,
        "source_revision": source_revision,
        "license": APACHE_TIKA_LICENSE,
        "license_url": APACHE_TIKA_LICENSE_URL,
    }


def _validate_immutable_revision(revision: str) -> None:
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("Apache Tika source revision must be an immutable 40-character commit")


def _validate_download_url(
    url: str,
    revision: str,
    directory: str,
    name: str,
) -> None:
    parsed = urlsplit(str(url))
    expected_prefix = "/apache/tika/{}/".format(revision)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "raw.githubusercontent.com"
        or not unquote(parsed.path).startswith(expected_prefix)
    ):
        raise ValueError("Apache Tika download URL does not match its source revision")
    expected_path = "/apache/tika/{}/{}/{}".format(
        revision,
        directory.strip("/"),
        name,
    )
    if unquote(parsed.path) != expected_path or parsed.query or parsed.fragment:
        raise ValueError("Apache Tika download URL does not match its source path")


def fixture_counts(fixtures: Iterable[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for fixture in fixtures:
        counts[fixture["format"]] = counts.get(fixture["format"], 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an Apache Tika OOXML fixture index JSON file.")
    parser.add_argument("output", type=Path, help="Path to write fixture index JSON")
    parser.add_argument("--formats", default="docx,pptx,xlsx", help="Comma-separated extensions")
    parser.add_argument("--branch", default=APACHE_TIKA_BRANCH, help="Apache Tika git branch or ref")
    parser.add_argument("--directory", default=APACHE_TIKA_TEST_DOCUMENTS_DIR, help="Apache Tika test-documents path")
    args = parser.parse_args()

    formats = [item.strip() for item in args.formats.split(",") if item.strip()]
    index = build_apache_tika_fixture_index(formats=formats, branch=args.branch, directory=args.directory)
    atomic_write_text(
        args.output,
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps({"output": str(args.output), "counts": index["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
