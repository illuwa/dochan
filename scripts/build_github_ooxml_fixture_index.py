"""Build a license-tagged OOXML fixture index from selected GitHub repositories."""
import argparse
import json
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, List


GITHUB_OOXML_SOURCES = [
    {
        "repo": "python-openxml/python-docx",
        "ref": "master",
        "directories": ["tests/test_files", "features/steps/test_files"],
        "formats": ["docx"],
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/master/LICENSE",
    },
    {
        "repo": "scanny/python-pptx",
        "ref": "master",
        "directories": ["tests/test_files", "features/steps/test_files"],
        "formats": ["pptx"],
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "repo": "pyexcel/pyexcel",
        "ref": "dev",
        "directories": ["tests/fixtures"],
        "formats": ["xlsx"],
        "license": "BSD-3-Clause",
        "license_url": "https://github.com/pyexcel/pyexcel/blob/dev/LICENSE",
    },
    {
        "repo": "ChrisPappalardo/eparse",
        "ref": "main",
        "directories": ["tests"],
        "formats": ["xlsx"],
        "license": "MIT",
        "license_url": "https://github.com/ChrisPappalardo/eparse/blob/main/LICENSE",
    },
]


def fetch_github_directory(url: str) -> List[dict]:
    with urllib.request.urlopen(url, timeout=30) as response:
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
        "license": source["license"],
        "license_url": source["license_url"],
    }


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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": index["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
