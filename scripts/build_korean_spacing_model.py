"""HWP/HWPX 본문에서 한글 줄 경계 공백 모델을 학습한다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from dochan.pdf.spacing import SpacingModel

_COUNT_NAMES = ("total", "space", "last_total", "last_space", "first_total", "first_space")
_MAX_FILE_BYTES = 50 * 1024 * 1024


def count_text(text):
    """인접 한글 음절 또는 공백 하나를 사이에 둔 음절만 센다.

    문단(\\n)·표 셀(\\t) 같은 구조 경계는 어절 경계가 아니므로 세그먼트를 나눠 안에서만 센다.
    PDF 줄 병합은 언제나 문단 안에서 일어나기 때문에 학습 분포를 거기에 맞춘다.
    """
    counts = {name: Counter() for name in _COUNT_NAMES}
    for segment in re.split(r"[\n\t\r\f\v]+", unicodedata.normalize("NFC", text)):
        segment = re.sub(r" +", " ", segment)
        for i in range(len(segment) - 1):
            last = segment[i]
            if not "가" <= last <= "힣":
                continue
            spaced = segment[i + 1] == " "
            j = i + 2 if spaced else i + 1
            if j >= len(segment) or not "가" <= segment[j] <= "힣":
                continue
            first = segment[j]
            counts["total"][(last, first)] += 1
            counts["last_total"][last] += 1
            counts["first_total"][first] += 1
            if spaced:
                counts["space"][(last, first)] += 1
                counts["last_space"][last] += 1
                counts["first_space"][first] += 1
    return counts


def merge_counts(counts):
    """파일별 카운터를 순서와 무관하게 합친다. 입력은 바꾸지 않는다."""
    merged = {name: Counter() for name in _COUNT_NAMES}
    for item in counts:
        for name in _COUNT_NAMES:
            merged[name].update(item[name])
    return merged


def build_model(counts, min_pair_count=5, min_char_count=20, exception_threshold=0.2):
    """주변 확률과 차이가 있는 문자쌍만 남기고 소수 둘째 자리로 저장한다.

    예외 쌍 선별은 런타임이 실제로 읽는 '반올림된' 주변 확률·사전확률로 판정한다.
    반올림 전 값으로 고르면 저장된 모델의 판정이 학습 때와 달라질 수 있다.
    """
    total = sum(counts["total"].values())
    prior = round(sum(counts["space"].values()) / total, 2) if total else 0.29
    marginals = {
        side: {char: round(counts[side + "_space"][char] / count, 2)
               for char, count in sorted(counts[side + "_total"].items())
               if count >= min_char_count}
        for side in ("last", "first")
    }
    marginal_model = SpacingModel(prior=prior, **marginals)
    pairs = {}
    for (last, first), count in sorted(counts["total"].items()):
        if count < min_pair_count:
            continue
        probability = round(counts["space"][(last, first)] / count, 2)
        marginal = marginal_model.space_probability(last, first)
        pair_model = SpacingModel(prior=prior, pairs={last + first: probability})
        if (pair_model.joins_with_space(last, first) != marginal_model.joins_with_space(last, first)
                or abs(probability - marginal) >= exception_threshold):
            pairs[last + first] = probability
    return {"version": 1, "prior": prior, "min_pair_count": min_pair_count,
            "min_char_count": min_char_count, **marginals, "pairs": pairs}


def _count_file(file_path):
    """(카운터, 실패 사유). 파싱 실패·빈 문서·50MB 초과는 사유와 함께 건너뛴다."""
    from dochan import Dochan

    try:
        if Path(file_path).stat().st_size > _MAX_FILE_BYTES:
            return None, "too_large"
        text = Dochan(file_path).to_plain_text()
    except Exception as exc:  # 학습은 한 파일 실패로 멈추지 않되 사유는 남긴다
        return None, f"error:{type(exc).__name__}"
    if not text.strip():
        return None, "empty"
    return count_text(text), None


def _corpus_counts(files, workers, stats):
    """파일 하나당 작업 하나를 보내고, 끝난 Future 는 바로 버려 결과가 상주하지 않게 한다."""
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending = {executor.submit(_count_file, str(path)): str(path) for path in files}
        for index, future in enumerate(as_completed(list(pending)), start=1):
            path = pending.pop(future)
            counts, reason = future.result()
            if index % 200 == 0:
                print(f"...{index}/{len(files)} files", flush=True)
            if counts is None:
                stats["skipped"].append((path, reason))
                continue
            stats["parsed"].append(path)
            yield counts


def _corpus_manifest(files, stats):
    """배포 모델을 감사할 수 있도록 코퍼스 구성을 남긴다 (정렬된 파일명의 SHA-256)."""
    names = "\n".join(sorted(Path(path).name for path in files)).encode("utf-8")
    return {"files": len(files), "parsed": len(stats["parsed"]), "skipped": len(stats["skipped"]),
            "names_sha256": hashlib.sha256(names).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus_dir", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) // 2))
    parser.add_argument("--min-pair-count", type=int, default=5)
    parser.add_argument("--min-char-count", type=int, default=20)
    parser.add_argument("--exception-threshold", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=0, help="최대 파일 수 (0: 전체)")
    parser.add_argument("--report", type=Path, help="파싱/건너뛴 파일과 사유를 기록할 JSON 경로")
    args = parser.parse_args(argv)
    if min(args.workers, args.min_pair_count, args.min_char_count) < 1:
        parser.error("workers와 최소 관측 수는 1 이상이어야 합니다")
    if args.limit < 0 or not 0 <= args.exception_threshold <= 1:
        parser.error("limit는 0 이상, exception-threshold는 0~1이어야 합니다")
    if any(not path.is_dir() for path in args.corpus_dir):
        parser.error("corpus_dir는 존재하는 디렉터리여야 합니다")
    files = sorted({path.resolve() for root in args.corpus_dir for path in root.rglob("*")
                    if path.is_file() and path.suffix.lower() in (".hwp", ".hwpx")})
    if args.limit:
        files = files[:args.limit]
    stats = {"parsed": [], "skipped": []}
    counts = merge_counts(_corpus_counts(files, args.workers, stats))
    model = build_model(counts, args.min_pair_count, args.min_char_count, args.exception_threshold)
    model["corpus"] = _corpus_manifest(files, stats)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(
            {"parsed": sorted(stats["parsed"]), "skipped": sorted(stats["skipped"])},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"parsed={len(stats['parsed'])} skipped={len(stats['skipped'])} "
          f"syllable_pairs={sum(counts['total'].values())} "
          f"last={len(model['last'])} first={len(model['first'])} pairs={len(model['pairs'])} "
          f"output_bytes={args.output.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
