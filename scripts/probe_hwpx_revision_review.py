"""Check four public change-tracking HWPX files without saving full output.

Usage: python -m scripts.probe_hwpx_revision_review CORPUS --baseline-module MODULE
CORPUS is the public hwpx directory; MODULE is the prior revisions.py source.
"""

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import dochan.hwpx.parser as parser_module
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown


SAMPLES = (
    "hwpxlib-ChangeTrack.hwpx",
    "reader_writer__ChangeTrack.hwpx",
    "admrul-관세조사-운영-훈령.hwpx",
    "korea-mid-30-7_*.hwpx",
)


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _model_digest(document):
    value = to_dict(document)
    value.get("metadata", {}).pop("errors", None)
    return _digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                              default=str))


def _paragraphs(document):
    return [paragraph.text for paragraph in document.find_all("paragraph")]


def _subsequence(needle, haystack):
    source = iter(haystack)
    return all(character in source for character in needle)


def _load_projector(path):
    spec = importlib.util.spec_from_file_location(
        "dochan.hwpx._review_baseline_revisions", path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.RevisionProjector


def _parse(path, projector, mode):
    parser_module.RevisionProjector = projector
    return parser_module.HWPXParser().parse(path, revision_mode=mode,
                                            include_assets=True)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("corpus", type=Path)
    cli.add_argument("--baseline-module", required=True, type=Path)
    arguments = cli.parse_args()
    current = parser_module.RevisionProjector
    baseline = _load_projector(arguments.baseline_module)
    results = []
    try:
        for pattern in SAMPLES:
            matches = sorted(arguments.corpus.glob(pattern))
            if len(matches) != 1:
                raise ValueError("Expected one public sample for " + pattern)
            path = matches[0]
            old = _parse(path, baseline, "preserve")
            new = {mode: _parse(path, current, mode)
                   for mode in ("preserve", "final", "original")}
            preserve = _paragraphs(new["preserve"])
            gold = re.sub(r"\[\d+\]", "", "".join(preserve))
            baseline_text = _paragraphs(old)
            row = {
                "sample": path.name,
                "preserve_equal": preserve == baseline_text,
                "preserve_model_equal": _model_digest(new["preserve"]) ==
                                        _model_digest(old),
                "preserve_markdown_equal": to_markdown(new["preserve"]) ==
                                           to_markdown(old),
                "modes": {},
            }
            for mode, document in new.items():
                paragraphs = _paragraphs(document)
                content = "".join(paragraphs)
                projected = re.sub(r"\[\d+\]", "", content)
                row["modes"][mode] = {
                    "paragraphs": len(paragraphs),
                    "characters": len(content),
                    "sha256": _digest("\n".join(paragraphs)),
                    "ordered_subsequence": _subsequence(projected, gold),
                    "multiset_subset": not bool(Counter(content) -
                                                Counter("".join(preserve))),
                    "diagnostics": document.errors,
                }
            for mode in ("final", "original"):
                # Fixed interpreter/module and argv list; no document-sourced command.
                argv = [sys.executable, "-m", "dochan.cli", "convert", str(path), "--format", "text", "--revision-mode", mode]
                process = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
                row["modes"][mode]["cli_exit"] = process.returncode
            results.append(row)
    finally:
        parser_module.RevisionProjector = current
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
