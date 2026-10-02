"""PPT 리뷰의 문자별 서식 변화와 독립 PPTX XML 정답을 재측정한다.

snapshot --source SOURCE --list LIST --corpus-root CORPUS --output JSON
compare --before BEFORE --after AFTER --corpus-root CORPUS --output JSON
정답 범위는 p:sp 텍스트와 기본/마스터/레이아웃/문단/런 속성이다.
표, 노트, 그룹의 암시적 서식과 테마 글꼴은 정답 범위에서 제외한다.
"""

import argparse
from collections import Counter, defaultdict
import json
import multiprocessing
from pathlib import Path
import re
import signal
import sys

PROPERTIES = ("bold", "italic", "underline", "size", "superscript", "subscript")


def _timeout(*_args):
    raise TimeoutError("60 second document limit exceeded")


def _snapshot(job):
    path, root, key = job
    sys.path.insert(0, root)
    signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(60)
    try:
        from dochan import Dochan
        from dochan.model.document import Paragraph
        from scripts.compare_office_pairs import _walk

        document = Dochan(path)
        paragraphs = []
        for node in _walk(document.doc):
            if isinstance(node, Paragraph):
                provenance = getattr(node, "provenance", None)
                origin = getattr(provenance, "path", "") if provenance else ""
                runs = [
                    [
                        r.text,
                        r.bold,
                        r.italic,
                        r.underline,
                        r.font_size_pt,
                        r.superscript,
                        r.subscript,
                    ]
                    for r in node.runs
                ]
                paragraphs.append([origin, runs])
        return key, {
            "paras": paragraphs,
            "md": document.to_markdown(),
            "errors": list(document.errors),
        }
    except Exception as exc:
        return key, {"exception": "%s: %s" % (type(exc).__name__, exc)}
    finally:
        signal.alarm(0)


def snapshot(source, listing, corpus):
    jobs = []
    for line in Path(listing).read_text().splitlines():
        path = Path(line.strip()).resolve()
        if path.suffix.lower() == ".ppt":
            key = str(path.relative_to(corpus))
            jobs.append((str(path), str(Path(source).resolve()), key))
    with multiprocessing.get_context("fork").Pool(4, maxtasksperchild=1) as pool:
        return dict(pool.imap_unordered(_snapshot, jobs))


def _characters(runs):
    return [tuple(run[1:]) for run in runs for _ in run[0]]


def changes(before, after):
    chars, files, transitions = Counter(), Counter(), Counter()
    mismatch = []
    errors = []
    md_changed = []
    for path in sorted(before):
        b, n = before[path], after[path]
        if "exception" in b or "exception" in n:
            errors.append(path)
            continue
        if b["md"] != n["md"]:
            md_changed.append(path)
        if len(b["paras"]) != len(n["paras"]):
            mismatch.append(path)
            continue
        changed = set()
        for (_, rb), (_, rn) in zip(b["paras"], n["paras"]):
            if "".join(r[0] for r in rb) != "".join(r[0] for r in rn):
                mismatch.append(path)
                continue
            for x, y in zip(_characters(rb), _characters(rn)):
                for j, prop in enumerate(PROPERTIES):
                    if x[j] != y[j]:
                        chars[prop] += 1
                        changed.add(prop)
                        transitions[(prop, x[j], y[j])] += 1
        files.update(changed)
        files["any"] += bool(changed)
    return {
        "files": len(before),
        "changed_files": dict(files),
        "changed_characters": dict(chars),
        "text_mismatch": sorted(set(mismatch)),
        "exceptions": errors,
        "markdown_changed_files": md_changed,
        "transitions": [[*key, count] for key, count in transitions.items()],
    }


def pair_evidence(before, after, corpus):
    from scripts.pptx_style_reference import pptx_paragraphs

    total = {label: Counter() for label in ("before", "after", "denominator")}
    pairs = {}
    for path in sorted(before):
        pptx = (corpus / path).with_suffix(".pptx")
        if not pptx.exists():
            continue
        try:
            reference = pptx_paragraphs(pptx)
        except Exception as exc:
            pairs[path] = {"exception": "%s: %s" % (type(exc).__name__, exc)}
            continue
        answer = defaultdict(list)
        for slide, _kind, text, runs in reference:
            chars = []
            for text_run, props in runs:
                value = (
                    props.get("b", False),
                    props.get("i", False),
                    props.get("u", False),
                    props.get("sz"),
                    props.get("base", 0) > 0,
                    props.get("base", 0) < 0,
                )
                chars.extend([value] * len(text_run))
            answer[(slide, text.strip())].append((text, chars))
        stats = {label: Counter() for label in total}
        matched_paragraphs = Counter()
        changed_chars = Counter()
        for label, data in (("before", before[path]), ("after", after[path])):
            used = Counter()
            for origin, runs in data.get("paras", []):
                match = re.search(r"#slide(\d+)", origin)
                if not match or "#notes" in origin or "#master" in origin:
                    continue
                text = "".join(r[0] for r in runs)
                key = (int(match.group(1)), text.strip())
                if key not in answer or used[key] >= len(answer[key]):
                    continue
                truth_text, truth_chars = answer[key][used[key]]
                used[key] += 1
                matched_paragraphs[label] += 1
                chars = _characters(runs)
                needle = truth_text.strip()
                ts, ps = truth_text.find(needle), text.find(needle)
                for k, char in enumerate(needle):
                    if char.isspace():
                        continue
                    actual, expected = chars[ps + k], truth_chars[ts + k]
                    for j, prop in enumerate(PROPERTIES):
                        if prop == "size" and expected[j] is None:
                            continue
                        if label == "after":
                            stats["denominator"][prop] += 1
                        if actual[j] == expected[j]:
                            stats[label][prop] += 1
        # Changes within a pair are separately counted; pairing is not evidence
        # for a new property when all measured characters were unchanged.
        delta = changes({path: before[path]}, {path: after[path]})
        changed_chars.update(delta["changed_characters"])
        pairs[path] = {
            **{k: dict(v) for k, v in stats.items()},
            "matched_paragraphs": dict(matched_paragraphs),
            "changed_characters_all_paragraphs": dict(changed_chars),
        }
        for label in total:
            total[label].update(stats[label])
    return {"pairs": pairs, "totals": {k: dict(v) for k, v in total.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("--source", required=True)
    snap.add_argument("--list", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--before", required=True)
    compare.add_argument("--after", required=True)
    for command in (snap, compare):
        command.add_argument("--corpus-root", required=True)
        command.add_argument("--output", required=True)
    args = parser.parse_args()
    corpus = Path(args.corpus_root).resolve()
    if args.command == "snapshot":
        result = snapshot(args.source, args.list, corpus)
    else:
        before = json.loads(Path(args.before).read_text())
        after = json.loads(Path(args.after).read_text())
        if set(before) != set(after):
            parser.error("snapshot file sets differ")
        result = {
            "changes": changes(before, after),
            "reference": pair_evidence(before, after, corpus),
        }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    if args.command == "snapshot":
        print(
            "%d files, %d exceptions"
            % (len(result), sum("exception" in r for r in result.values()))
        )
    else:
        print(
            json.dumps(
                {
                    "changes": result["changes"]["changed_characters"],
                    "reference": result["reference"]["totals"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
