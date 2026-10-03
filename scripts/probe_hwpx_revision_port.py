"""공개 HWPX의 출력 해시를 소스 버전별로 수집한다.

코퍼스와 비교할 소스 루트는 인자로 받는다. 문서 출력은 저장하지 않는다.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path


TRACKED_PREFIXES = (
    "admrul-관세조사-운영-훈령",
    "hwpxlib-ChangeTrack",
    "reader_writer__ChangeTrack",
    "korea-mid-30-7_",
)


def fingerprint(value):
    return {"sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            "characters": len(value)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tracked", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_root.resolve()))
    from dochan import Dochan  # imported after source root is selected

    paths = sorted(args.corpus.glob("*.hwpx"))
    if args.tracked:
        paths = [path for path in paths if path.name.startswith(TRACKED_PREFIXES)]
    modes = ("preserve", "final", "original") if args.tracked else ("preserve",)
    with args.output.open("w", encoding="utf-8") as output:
        for index, path in enumerate(paths, 1):
            for mode in modes:
                row = {"file": path.name, "mode": mode}
                try:
                    if args.tracked:
                        reader = Dochan(str(path), include_assets=False,
                                        revision_mode=mode)
                    else:
                        reader = Dochan(str(path))
                    row["markdown"] = fingerprint(reader.to_markdown())
                    if args.tracked:
                        row["json"] = fingerprint(reader.to_json())
                        row["errors"] = list(reader.errors)
                except Exception as exc:
                    row["exception"] = type(exc).__name__ + ": " + str(exc)
                output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            if index % 100 == 0:
                print("processed %d/%d" % (index, len(paths)), flush=True)
    print("processed %d/%d" % (len(paths), len(paths)), flush=True)


if __name__ == "__main__":
    main()
