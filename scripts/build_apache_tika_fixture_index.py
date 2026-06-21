"""Build a JSON fixture index from Apache Tika OOXML test documents."""
import argparse
import json
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, List


APACHE_TIKA_BRANCH = "main"
APACHE_TIKA_LICENSE = "Apache-2.0"
APACHE_TIKA_LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt"
APACHE_TIKA_REPO = "apache/tika"
APACHE_TIKA_TEST_DOCUMENTS_DIR = (
    "tika-parsers/tika-parsers-standard/tika-parsers-standard-modules/"
    "tika-parser-microsoft-module/src/test/resources/test-documents"
)


def fetch_github_directory(url: str) -> List[dict]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def github_contents_url(directory: str = APACHE_TIKA_TEST_DOCUMENTS_DIR, branch: str = APACHE_TIKA_BRANCH) -> str:
    return f"https://api.github.com/repos/{APACHE_TIKA_REPO}/contents/{directory}?ref={branch}"


def build_apache_tika_fixture_index(
    formats: Iterable[str] = ("docx", "pptx", "xlsx"),
    branch: str = APACHE_TIKA_BRANCH,
    directory: str = APACHE_TIKA_TEST_DOCUMENTS_DIR,
    fetch_directory: Callable[[str], List[dict]] = fetch_github_directory,
) -> dict:
    requested = {fmt.lower().lstrip(".") for fmt in formats}
    url = github_contents_url(directory, branch)
    fixtures = [
        fixture
        for entry in fetch_directory(url)
        for fixture in [apache_tika_entry_to_fixture(entry, requested, directory)]
        if fixture
    ]
    return {
        "source": APACHE_TIKA_REPO,
        "branch": branch,
        "directories": [directory],
        "fixtures": sorted(fixtures, key=lambda item: (item["format"], item["source_name"])),
        "counts": fixture_counts(fixtures),
    }


def apache_tika_entry_to_fixture(entry: dict, active_formats: Iterable[str], directory: str) -> dict:
    name = str(entry.get("name", ""))
    file_format = Path(name).suffix.lower().lstrip(".")
    if file_format not in set(active_formats):
        return {}
    if entry.get("type") != "file":
        return {}
    download_url = entry.get("download_url")
    if not download_url:
        return {}
    source_name = f"{directory}/{name}"
    return {
        "name": name,
        "source_name": source_name,
        "format": file_format,
        "url": download_url,
        "source": APACHE_TIKA_REPO,
        "license": APACHE_TIKA_LICENSE,
        "license_url": APACHE_TIKA_LICENSE_URL,
    }


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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": index["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
