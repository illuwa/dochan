"""Download a public HWP/HWPX regression corpus from a fixture-index JSON.

Mirrors the pattern in scripts/download_public_ooxml_corpus.py, but adapted
for HWP/HWPX sources: GitHub-hosted open-source test fixtures, official
Korean government/public-institution form archives, and open data portals.
Fixture indexes are produced separately (see docs/benchmarks/hwp-corpus-*
JSON files) and passed via --fixture-index; this script only handles the
download/validate/manifest step.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, List

HWP_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # OLE2 compound file signature
ZIP_MAGIC = b"PK\x03\x04"  # HWPX is a ZIP (OWPML) package

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 dochan-corpus-collector"
)


def load_fixture_index(path: Path) -> List[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures = payload.get("fixtures", payload) if isinstance(payload, dict) else payload
    if not isinstance(fixtures, list):
        raise ValueError("fixture index must be a JSON list or an object with a 'fixtures' list")
    return [dict(fixture) for fixture in fixtures]


def merge_fixture_indexes(paths: Iterable[Path]) -> List[dict]:
    merged: List[dict] = []
    seen_urls = set()
    for path in paths:
        for fixture in load_fixture_index(path):
            url = fixture.get("url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(fixture)
    return merged


def _validate_magic(file_format: str, data: bytes) -> bool:
    file_format = file_format.lower().lstrip(".")
    if file_format == "hwp":
        return data.startswith(HWP_MAGIC)
    if file_format == "hwpx":
        return data.startswith(ZIP_MAGIC)
    return True


def download_fixture(fixture: dict, output_dir: Path, timeout: float = 20.0) -> dict:
    file_format = str(fixture.get("format", "")).lower().lstrip(".")
    format_dir = output_dir / (file_format or "unknown")
    format_dir.mkdir(parents=True, exist_ok=True)
    destination = format_dir / fixture["name"]

    max_bytes = 50 * 1024 * 1024  # 50MB guard against pathological/unexpected downloads
    request = urllib.request.Request(fixture["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"file too large ({content_length} bytes > {max_bytes})")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError(f"file too large (> {max_bytes} bytes, no Content-Length header)")

    if not _validate_magic(file_format, data):
        raise ValueError(
            f"magic bytes mismatch for format={file_format!r} "
            f"(got {data[:8]!r}; likely an HTML error/login page, not a real document)"
        )

    destination.write_bytes(data)
    record = dict(fixture)
    record["path"] = destination.relative_to(output_dir).as_posix()
    record["bytes"] = destination.stat().st_size
    return record


def write_sources(output_dir: Path, records: List[dict]) -> None:
    (output_dir / "SOURCES.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Public HWP/HWPX Corpus Sources",
        "",
        "| File | Format | Source | License | URL |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            "| {path} | {format} | {source} | {license} | {url} |".format(
                path=record["path"],
                format=record.get("format", ""),
                source=record.get("source", ""),
                license=record.get("license") or record.get("notes") or "",
                url=record["url"],
            )
        )
    lines.append("")
    (output_dir / "SOURCES.md").write_text("\n".join(lines), encoding="utf-8")


def write_failures(output_dir: Path, failures: List[dict]) -> None:
    (output_dir / "FAILURES.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def download_corpus(
    output_dir: Path,
    fixtures: List[dict],
    delay: float = 0.4,
    limit: int = 0,
    timeout: float = 20.0,
) -> "tuple[List[dict], List[dict]]":
    output_dir.mkdir(parents=True, exist_ok=True)
    if limit > 0:
        fixtures = fixtures[:limit]

    records: List[dict] = []
    failures: List[dict] = []

    for index, fixture in enumerate(fixtures, start=1):
        name = fixture.get("name", "?")
        try:
            record = download_fixture(fixture, output_dir, timeout=timeout)
            records.append(record)
            print(f"[{index}/{len(fixtures)}] OK   {name} ({record['bytes']} bytes)")
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
            failures.append({**fixture, "error": str(exc)})
            print(f"[{index}/{len(fixtures)}] FAIL {name}: {exc}")
        if delay > 0:
            time.sleep(delay)

    write_sources(output_dir, records)
    write_failures(output_dir, failures)
    return records, failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download a public HWP/HWPX corpus from one or more fixture-index JSON files."
    )
    parser.add_argument("output_dir", type=Path, help="Directory to write corpus files")
    parser.add_argument(
        "--fixture-index",
        type=Path,
        action="append",
        required=True,
        help="JSON list (or {'fixtures': [...]}) of fixture records; repeatable",
    )
    parser.add_argument("--delay", type=float, default=0.4, help="Seconds to sleep between downloads")
    parser.add_argument("--limit", type=int, default=0, help="Only download the first N fixtures (0 = no limit)")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout in seconds")
    args = parser.parse_args()

    fixtures = merge_fixture_indexes(args.fixture_index)
    records, failures = download_corpus(
        args.output_dir,
        fixtures,
        delay=args.delay,
        limit=args.limit,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            {
                "output_dir": str(args.output_dir),
                "downloaded": len(records),
                "failed": len(failures),
                "total_fixtures": len(fixtures),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
