"""Build a JSON fixture index from Apache POI OOXML test-data directories."""
import argparse
import json
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, List


APACHE_POI_BRANCH = "trunk"
APACHE_POI_LICENSE = "Apache-2.0"
APACHE_POI_LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0.txt"
APACHE_POI_REPO_API = "https://api.github.com/repos/apache/poi/contents/test-data/{directory}?ref={branch}"
APACHE_POI_TEST_DATA_DIRS = {
    "docx": "document",
    "pptx": "slideshow",
    "xlsx": "spreadsheet",
}


def fetch_github_directory(url: str) -> List[dict]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def build_apache_poi_fixture_index(
    formats: Iterable[str] = APACHE_POI_TEST_DATA_DIRS,
    branch: str = APACHE_POI_BRANCH,
    fetch_directory: Callable[[str], List[dict]] = fetch_github_directory,
) -> dict:
    requested = [fmt.lower().lstrip(".") for fmt in formats]
    fixtures = []

    for file_format in requested:
        directory = APACHE_POI_TEST_DATA_DIRS[file_format]
        url = APACHE_POI_REPO_API.format(directory=directory, branch=branch)
        entries = fetch_directory(url)
        for entry in entries:
            fixture = apache_poi_entry_to_fixture(entry, file_format)
            if fixture:
                fixtures.append(fixture)

    return {
        "source": "apache/poi",
        "branch": branch,
        "fixtures": sorted(fixtures, key=lambda item: (item["format"], item["source_name"])),
        "counts": fixture_counts(fixtures),
    }


def apache_poi_entry_to_fixture(entry: dict, file_format: str) -> dict:
    name = str(entry.get("name", ""))
    if not name.lower().endswith(f".{file_format}"):
        return {}
    download_url = entry.get("download_url")
    if not download_url:
        return {}
    return {
        "name": name,
        "source_name": name,
        "format": file_format,
        "url": download_url,
        "source": "apache/poi",
        "license": APACHE_POI_LICENSE,
        "license_url": APACHE_POI_LICENSE_URL,
    }


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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": index["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
