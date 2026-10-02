"""공개 HWP/HWPX 쌍의 제목과 유효 글자서식을 비교한다.

실행: /usr/bin/python3 -m scripts.probe_hwp_styles CORPUS
표본을 읽기만 하며 텍스트 본문을 기록하지 않는다.
"""
import argparse
import json
from pathlib import Path

from dochan import Dochan
from scripts.compare_hwp_pairs import format_match_stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    rows = []
    for name in ("sample-outline-list", "sample-mixed-lists-with-outline", "charstyle"):
        hwp = args.corpus / "hwp" / (name + ".hwp")
        hwpx = args.corpus / "hwpx" / (name + ".hwpx")
        if not hwp.is_file() or not hwpx.is_file():
            continue
        actual, answer = Dochan(hwp).doc, Dochan(hwpx).doc
        expected_levels = [p.heading_level for p in answer.find_all("paragraph")]
        actual_levels = [p.heading_level for p in actual.find_all("paragraph")]
        formatted, text_match, _, _ = format_match_stats(answer, actual)
        rows.append(dict(file=hwp.name, answer=hwpx.name,
                         expected_levels=expected_levels, actual_levels=actual_levels,
                         formatted_matches=formatted, matched_paragraphs=text_match,
                         errors=len(actual.errors) + len(answer.errors),
                         passed=expected_levels == actual_levels and formatted == text_match
                         and not actual.errors and not answer.errors))
    print(json.dumps(rows, ensure_ascii=False))
    return 0 if rows and all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
