"""HWP/HWPX 본문에서 한글 줄 경계 공백 모델을 학습한다."""
from __future__ import annotations

import argparse
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
    """인접 한글 음절 또는 공백 하나를 사이에 둔 음절만 센다."""
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFC", text))
    counts = {name: Counter() for name in _COUNT_NAMES}
    for i in range(len(text) - 1):
        last = text[i]
        if not "가" <= last <= "힣":
            continue
        spaced = text[i + 1] == " "
        j = i + 2 if spaced else i + 1
        if j >= len(text) or not "가" <= text[j] <= "힣":
            continue
        first = text[j]
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
    """주변 확률과 차이가 있는 문자쌍만 남기고 소수 둘째 자리로 저장한다."""
    total = sum(counts["total"].values())
    prior = sum(counts["space"].values()) / total if total else 0.29
    marginals = {
        side: {char: counts[side + "_space"][char] / count
               for char, count in sorted(counts[side + "_total"].items())
               if count >= min_char_count}
        for side in ("last", "first")
    }
    marginal_model = SpacingModel(prior=prior, **marginals)
    pairs = {}
    for (last, first), count in sorted(counts["total"].items()):
        if count < min_pair_count:
            continue
        probability = counts["space"][(last, first)] / count
        marginal = marginal_model.space_probability(last, first)
        if ((probability > 0.5) != (marginal > 0.5)
                or abs(probability - marginal) >= exception_threshold):
            pairs[last + first] = round(probability, 2)
    return {"version": 1, "prior": round(prior, 2), "min_pair_count": min_pair_count,
            "min_char_count": min_char_count,
            **{side: {char: round(p, 2) for char, p in table.items()}
               for side, table in marginals.items()}, "pairs": pairs}


def _count_file(file_path):
    """파싱 실패·빈 문서·50MB 초과 파일은 건너뛴다."""
    from dochan import Dochan

    try:
        if Path(file_path).stat().st_size > _MAX_FILE_BYTES:
            return None
        text = Dochan(file_path).to_plain_text()
        return count_text(text) if text.strip() else None
    except Exception:
        return None


def _corpus_counts(files, workers, stats):
    """파일 하나당 작업 하나를 보내고 완료된 카운터를 부모에서 합친다."""
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_count_file, str(path)) for path in files]
        for index, future in enumerate(as_completed(futures), start=1):
            counts = future.result()
            stats["skipped" if counts is None else "parsed"] += 1
            if index % 200 == 0:
                print(f"...{index}/{len(files)} files", flush=True)
            if counts is not None:
                yield counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus_dir", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) // 2))
    parser.add_argument("--min-pair-count", type=int, default=5)
    parser.add_argument("--min-char-count", type=int, default=20)
    parser.add_argument("--exception-threshold", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=0, help="최대 파일 수 (0: 전체)")
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
    stats = {"parsed": 0, "skipped": 0}
    counts = merge_counts(_corpus_counts(files, args.workers, stats))
    model = build_model(counts, args.min_pair_count, args.min_char_count, args.exception_threshold)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"parsed={stats['parsed']} skipped={stats['skipped']} "
          f"syllable_pairs={sum(counts['total'].values())} "
          f"last={len(model['last'])} first={len(model['first'])} pairs={len(model['pairs'])} "
          f"output_bytes={args.output.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
