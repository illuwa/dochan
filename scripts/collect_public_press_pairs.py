"""Collect public HWP/HWPX/PDF press-release triples from korea.kr.

정책브리핑 보도자료 한 건에는 같은 글의 HWPX(·HWP)와 PDF 가 함께 붙는 경우가 많다.
공공누리 제1유형(출처표시) 글만 골라 `corpus/press-pairs/<newsId>.{hwpx,hwp,pdf}` 로 받고,
출처 URL·부처·제목·라이선스를 `manifest.json` 에 남긴다. 받은 파일은 로컬 검증에만 쓰고
저장소에 넣지 않는다(corpus/ 는 gitignore).

    python -m scripts.collect_public_press_pairs --pages 1-30 --max-bytes 1500000000
"""
import argparse
import html
import json
import re
import time
import urllib.request
from pathlib import Path

BASE = "https://www.korea.kr"
LIST_URL = BASE + "/briefing/pressReleaseList.do?pageIndex=%d"
VIEW_URL = BASE + "/briefing/pressReleaseView.do?newsId=%s"
FILE_URL = BASE + "/common/download.do?fileId=%s&tblKey=GMN"
USER_AGENT = "Mozilla/5.0 (Macintosh) dochan-corpus-collector"
MAGIC = {"pdf": b"%PDF", "hwpx": b"PK\x03\x04", "hwp": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"}
MAX_FILE_BYTES = 12 * 1024 * 1024


def fetch(url, timeout=30.0, limit=MAX_FILE_BYTES):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosemgrep: dynamic-urllib-use-detected
        data = response.read(limit + 1)
        disposition = response.headers.get("Content-Disposition", "")
    if len(data) > limit:
        raise ValueError("file too large")
    return data, disposition


def attachments(page):
    """보도자료 본문에서 (fileId, 파일 이름) 쌍을 읽는다."""
    text = html.unescape(page)
    found = []
    for match in re.finditer(r"fileId=(\d+)", text):
        window = re.sub(r"<[^>]+>", " ", text[match.end():match.end() + 600])
        name = re.search(r"([^\s\"'<>][^\"'<>\n]{0,160}?\.(hwpx|hwp|pdf))\b", window)
        if name and match.group(1) not in {item[0] for item in found}:
            found.append((match.group(1), name.group(1).strip(), name.group(2).lower()))
    return found


def license_type(page):
    match = re.search(r"공공누리 제([1-4])유형", page)
    return int(match.group(1)) if match else None


def collect(output, pages, max_bytes, delay):
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    total = sum(path.stat().st_size for path in output.iterdir() if path.suffix in (".pdf", ".hwp", ".hwpx"))
    for index in pages:
        listing, _ = fetch(LIST_URL % index)
        news_ids = sorted(set(re.findall(rb"pressReleaseView\.do\?newsId=(\d+)", listing)))
        time.sleep(delay)
        for raw_id in news_ids:
            news_id = raw_id.decode()
            if news_id in manifest:
                continue
            page = fetch(VIEW_URL % news_id)[0].decode("utf-8", "replace")
            time.sleep(delay)
            files = attachments(page)
            kinds = {kind: (file_id, name) for file_id, name, kind in files}
            entry = {"license": license_type(page), "files": {}}
            title = re.search(r"<title>(.*?)</title>", page, re.S)
            entry["title"] = html.unescape(title.group(1)).strip() if title else ""
            if entry["license"] != 1 or "pdf" not in kinds or not ({"hwpx", "hwp"} & set(kinds)):
                entry["skipped"] = True
                manifest[news_id] = entry
                continue
            for kind, (file_id, name) in sorted(kinds.items()):
                try:
                    data, _ = fetch(FILE_URL % file_id)
                except Exception as error:  # 네트워크 오류는 기록만 하고 다음 파일로
                    entry["files"][kind] = {"error": type(error).__name__}
                    continue
                finally:
                    time.sleep(delay)
                if not data.startswith(MAGIC[kind]):
                    entry["files"][kind] = {"error": "magic"}
                    continue
                (output / ("%s.%s" % (news_id, kind))).write_bytes(data)
                total += len(data)
                entry["files"][kind] = {"name": name, "url": FILE_URL % file_id, "bytes": len(data)}
            manifest[news_id] = entry
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
            if total >= max_bytes:
                return manifest, total
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest, total


def page_range(text):
    start, _, end = text.partition("-")
    return range(int(start), int(end or start) + 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("corpus/press-pairs"))
    parser.add_argument("--pages", type=page_range, default=page_range("1-10"))
    parser.add_argument("--max-bytes", type=int, default=1_000_000_000)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()
    manifest, total = collect(args.output, args.pages, args.max_bytes, args.delay)
    kept = [key for key, value in manifest.items() if not value.get("skipped")]
    print("releases %d, kept %d, bytes %d" % (len(manifest), len(kept), total))


if __name__ == "__main__":
    main()
