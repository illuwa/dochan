"""Compare HWPX revision projections without storing complete document text.

Usage: python -m scripts.probe_hwpx_revisions SAMPLE --baseline-module PATH --output PATH
The baseline module can be made with `git show HEAD:dochan/hwpx/revisions.py`.
"""

import argparse
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import importlib.util
from pathlib import Path
import sys

import dochan.hwpx.parser as parser_module


def _load_projector(path):
    spec = importlib.util.spec_from_file_location("dochan.hwpx._baseline_revisions", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.RevisionProjector


def _capture(path, projector):
    parser_module.RevisionProjector = projector
    result = {}
    for mode in ("preserve", "final", "original"):
        doc = parser_module.HWPXParser().parse(path, include_assets=False,
                                               revision_mode=mode)
        paragraphs = [p.text for p in doc.find_all("paragraph")]
        result[mode] = (paragraphs, doc.errors)
    return result


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("sample", type=Path)
    cli.add_argument("--baseline-module", required=True, type=Path)
    cli.add_argument("--output", required=True, type=Path)
    args = cli.parse_args()
    current = parser_module.RevisionProjector
    baseline = _capture(args.sample, _load_projector(args.baseline_module))
    updated = _capture(args.sample, current)
    lines = ["# 공개 HWPX 변경 추적 전후 비교", ""]
    for mode in ("preserve", "final", "original"):
        old, old_errors = baseline[mode]
        new, new_errors = updated[mode]
        lines.extend([
            "## " + mode,
            "",
            "- 전: 문단 %d개, 글자 %d개, 진단 %d개, 본문 SHA-256 `%s`" %
            (len(old), sum(map(len, old)), len(old_errors), _digest("\n".join(old))),
            "- 후: 문단 %d개, 글자 %d개, 진단 %d개, 본문 SHA-256 `%s`" %
            (len(new), sum(map(len, new)), len(new_errors), _digest("\n".join(new))),
            "- 진단 전: " + str(Counter(e.split("[")[1].split("]")[0]
                                   for e in old_errors if "[" in e)),
            "- 진단 후: " + str(Counter(e.split("[")[1].split("]")[0]
                                   for e in new_errors if "[" in e)),
            "",
            "| 구분 | 문단 번호 | 앞 20자 |",
            "| --- | ---: | --- |",
        ])
        before_hashes = [_digest(text) for text in old]
        after_hashes = [_digest(text) for text in new]
        matcher = SequenceMatcher(None, before_hashes, after_hashes)
        for operation, before_start, before_end, after_start, after_end in matcher.get_opcodes():
            if operation == "equal":
                continue
            for index in range(before_start, before_end):
                prefix = old[index][:20].replace("|", "\\|").replace("\n", "\\n")
                lines.append("| 전 | %d | %s |" % (index + 1, prefix))
            for index in range(after_start, after_end):
                prefix = new[index][:20].replace("|", "\\|").replace("\n", "\\n")
                lines.append("| 후 | %d | %s |" % (index + 1, prefix))
        lines.append("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
