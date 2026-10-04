"""Collect parser diagnostics from public document corpora.

Usage: /usr/bin/python3 -m scripts.probe_error_sweep CORPUS [CORPUS ...]
       --output .codex-work/error-sweep-before.jsonl --workers 6 --hash-output

Each file runs in a fresh process with a 120-second deadline. JSONL records
contain diagnostics and, optionally, only a SHA-256/length of Markdown output.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


EXTENSIONS = frozenset({".hwp", ".hwpx", ".pdf", ".doc", ".docx",
                        ".ppt", ".pptx", ".xls", ".xlsx"})


def message_template(message):
    """Remove volatile locations, numbers, and quoted values from a warning."""
    value = re.sub(r"/(?:Users|private|Volumes|tmp)/[^\s:(),]+", "<path>",
                   str(message))
    value = re.sub(r"(['\"])[^'\"]+\.(?:xml|hwp|hwpx|docx?|pptx?|xlsx?|pdf)\1",
                   r"\1<name>\1", value, flags=re.IGNORECASE)
    value = re.sub(r"0x[0-9a-fA-F]+|\d+", "#", value)
    return value[:500]


def summarize(path):
    from collections import Counter, defaultdict

    by_format = Counter()
    affected = Counter()
    patterns = Counter()
    samples = defaultdict(list)
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            kind = record["format"]
            by_format[kind] += 1
            messages = record["errors"] + ([record["exception"]]
                                           if record["exception"] else [])
            if messages:
                affected[kind] += 1
            for message in messages:
                key = (kind, message_template(message))
                patterns[key] += 1
                sample = {"root": record["root"], "file": record["file"],
                          "message": message}
                if (len(samples[key]) < 3 and not any(
                        prior["root"] == sample["root"]
                        and prior["file"] == sample["file"]
                        for prior in samples[key])):
                    samples[key].append(sample)
    return {"files": dict(by_format), "affected_files": dict(affected),
            "templates": [{"format": kind, "template": template,
                           "count": count, "samples": samples[kind, template]}
                          for (kind, template), count in patterns.most_common()]}


def child(path, hash_output, repo=None):
    if repo is not None:
        sys.path.insert(0, str(repo.resolve()))
    from dochan.reader import Dochan

    result = {"errors": [], "exception": None}
    try:
        reader = Dochan(str(path))
        result["errors"] = [str(item)[:1000] for item in reader.doc.errors[:1000]]
        if hash_output:
            body = reader.to_markdown()
            encoded = body.encode("utf-8", "replace")
            result["markdown_sha256"] = hashlib.sha256(encoded).hexdigest()
            result["markdown_chars"] = len(body)
    except Exception as exc:
        result["exception"] = "%s: %s" % (type(exc).__name__, str(exc)[:1000])
    return result


def collect_one(item, hash_output, timeout, repo=None):
    root_number, root, path = item
    command = [sys.executable, "-m", "scripts.probe_error_sweep", "--child",
               str(path)]
    if hash_output:
        command.append("--hash-output")
    if repo is not None:
        command.extend(("--repo", str(repo)))
    started = time.monotonic()
    try:
        # nosemgrep: dangerous-subprocess-use-audit
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=timeout, check=False)
        if completed.returncode:
            result = {"errors": [], "exception": "worker exit %d: %s" % (
                completed.returncode, completed.stderr[-1000:])}
        else:
            result = json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        result = {"errors": [], "exception": "timeout after %d seconds" % timeout}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"errors": [], "exception": "%s: %s" % (
            type(exc).__name__, str(exc)[:1000])}
    result.update(root=root_number, file=str(path.relative_to(root)),
                  format=path.suffix.lower().lstrip("."),
                  seconds=round(time.monotonic() - started, 3))
    return result


def public_files(roots, extensions=EXTENSIONS):
    for root_number, root in enumerate(roots):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensions:
                yield root_number, root, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--hash-output", action="store_true")
    parser.add_argument("--format", action="append", choices=sorted(
        extension.lstrip(".") for extension in EXTENSIONS),
        help="limit collection to this format; repeat for more formats")
    parser.add_argument("--repo", type=Path,
                        help="read parser code from this repository snapshot")
    parser.add_argument("--child", type=Path)
    parser.add_argument("--summarize", type=Path,
                        help="read collection JSONL and write template counts")
    args = parser.parse_args()
    if args.child:
        print(json.dumps(child(args.child, args.hash_output, args.repo),
                         ensure_ascii=False))
        return
    if args.summarize:
        report = summarize(args.summarize)
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
        return
    if not args.roots or not args.output:
        parser.error("corpus roots and --output are required")
    if args.workers < 1 or args.timeout < 1:
        parser.error("workers and timeout must be positive")
    roots = [root.resolve() for root in args.roots]
    extensions = ({"." + kind for kind in args.format}
                  if args.format else EXTENSIONS)
    files = list(public_files(roots, extensions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending = [pool.submit(collect_one, item, args.hash_output,
                                   args.timeout, args.repo) for item in files]
            for count, future in enumerate(as_completed(pending), 1):
                stream.write(json.dumps(future.result(), ensure_ascii=False) + "\n")
                if count % 100 == 0:
                    stream.flush()
                    print("%d/%d" % (count, len(files)), file=sys.stderr,
                          flush=True)
    print("collected %d files in %s" % (len(files), args.output),
          file=sys.stderr)


if __name__ == "__main__":
    main()
