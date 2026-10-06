"""서식이 같은 인접 런을 합치는 Markdown 변경을 문서 전수로 대조한다.

같은 모델을 두 번 렌더한다: 기준(PPT·PDF 에서만 합치던 이전 규칙)과 현재. 바뀐 문서마다
(1) 강조·밑줄·취소선·위아래 첨자 마커를 뺀 글자가 같은지, (2) CommonMark 로 해석했을 때 글자로
남는 별표가 늘지 않았는지를 센다. CommonMark 해석에는 이미 설치된 markdown-it-py 를 검증
도구로만 쓴다(런타임 의존성이 아니다). 본문은 저장하지 않고 집계와 공개 경로만 남긴다.

예: python -m scripts.probe_markdown_run_merge corpus/hwp-public corpus/poi-src --workers 8 \\
        --output .codex-work/run-merge.json
"""
import argparse
import json
import multiprocessing
import os
import re
import signal
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

from scripts.probe_output_speed import collect_paths

_FIELDS = ('bold', 'italic', 'underline', 'strikeout', 'superscript', 'subscript', 'link', 'note_ref')
_MARKERS = re.compile(r"\*+|~~|</?u>|</?su[pb]>|\\")
_ADJACENT_BOLD = re.compile(r"(?<!\*)\*{4}(?!\*)")
MAX_RENDER_CHARS = 400000


class _Timeout(Exception):
    pass


def _raise_timeout(signum, frame):
    raise _Timeout()


def baseline_runs(runs):
    """이전 규칙: 출처가 PPT·PDF 인 런만 합친다."""
    result = []
    index = 0
    while index < len(runs):
        run = runs[index]
        provenance = getattr(run, 'provenance', None)
        if (getattr(provenance, 'source_format', '') not in ('ppt', 'pdf') or getattr(run, 'note_ref', 0)
                or run.equation is not None):
            result.append(run)
            index += 1
            continue
        key = tuple(getattr(run, name, None) for name in _FIELDS)
        end = index + 1
        while end < len(runs):
            following = runs[end]
            if (following.equation is not None or following.provenance != provenance
                    or tuple(getattr(following, name, None) for name in _FIELDS) != key):
                break
            end += 1
        result.append(replace(run, text=''.join(r.text for r in runs[index:end])) if end > index + 1 else run)
        index = end
    return result


def stripped_words(text):
    """서식 마커와 이스케이프 역슬래시를 뺀 낱말 목록."""
    return _MARKERS.sub("", text).split()


def literal_stars(parser, text):
    """CommonMark 해석 뒤에도 글자로 남는 별표 수."""
    return sum(child.content.count("*") for token in parser.parse(text)
               for child in token.children or () if child.type == "text")


def compare_renderings(before, after, parser=None):
    record = {"changed": before != after}
    if not record["changed"]:
        return record
    record["text_equal"] = stripped_words(before) == stripped_words(after)
    record["adjacent_before"] = len(_ADJACENT_BOLD.findall(before))
    record["adjacent_after"] = len(_ADJACENT_BOLD.findall(after))
    if parser is not None and max(len(before), len(after)) <= MAX_RENDER_CHARS:
        record["literal_before"] = literal_stars(parser, before)
        record["literal_after"] = literal_stars(parser, after)
    return record


def _init_worker():
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _raise_timeout)


def measure_file(path):
    from dochan import Dochan
    from dochan.output import markdown

    try:
        from markdown_it import MarkdownIt
        parser = MarkdownIt("commonmark").enable("strikethrough").enable("table")
    except ImportError:
        parser = None
    alarm = hasattr(signal, "SIGALRM")
    if alarm:
        signal.alarm(120)
    current = markdown._markdown_runs
    try:
        doc = Dochan(path).doc
        after = markdown.to_markdown(doc)
        markdown._markdown_runs = baseline_runs
        try:
            before = markdown.to_markdown(doc)
        finally:
            markdown._markdown_runs = current
        return path, compare_renderings(before, after, parser)
    except _Timeout:
        return path, {"failure": "timeout"}
    except Exception as exc:
        return path, {"failure": type(exc).__name__}
    finally:
        if alarm:
            signal.alarm(0)


def summarize(records):
    summary = {}
    flagged = []
    for path, record in sorted(records.items()):
        row = summary.setdefault(os.path.splitext(path)[1].lower().lstrip("."), Counter())
        row["files"] += 1
        if "failure" in record:
            row["failures"] += 1
            continue
        if not record["changed"]:
            continue
        row["changed"] += 1
        row["text_equal"] += record["text_equal"]
        row["adjacent_before"] += record["adjacent_before"]
        row["adjacent_after"] += record["adjacent_after"]
        if "literal_before" in record:
            row["rendered"] += 1
            row["literal_before"] += record["literal_before"]
            row["literal_after"] += record["literal_after"]
            row["literal_fewer"] += record["literal_after"] < record["literal_before"]
            row["literal_more"] += record["literal_after"] > record["literal_before"]
        if not record["text_equal"] or record.get("literal_after", 0) > record.get("literal_before", 0):
            flagged.append(path)
    return {suffix: dict(row) for suffix, row in summary.items()}, flagged


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    paths = collect_paths(args.roots)
    paths.sort(key=lambda path: -os.path.getsize(path))
    if args.workers <= 1:
        _init_worker()
        records = dict(measure_file(path) for path in paths)
    else:
        with multiprocessing.Pool(args.workers, _init_worker, maxtasksperchild=300) as pool:
            records = dict(pool.imap_unordered(measure_file, paths, chunksize=2))
    summary, flagged = summarize(records)
    Path(args.output).write_text(json.dumps({"summary": summary, "flagged": flagged}, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    for suffix in sorted(summary):
        print(suffix, summary[suffix])
    print("flagged:", len(flagged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
