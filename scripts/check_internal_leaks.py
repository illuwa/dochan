"""저장소에 내부 실물 문서의 이름·본문이 들어가지 않았는지 검사한다.

내부 문서는 저장소 밖 폴더(예: test_pairs/, corpus/local-samples/)에만 있다. 이 스크립트는 그 폴더들에서 파일 이름 조각과
본문의 고유 문장을 뽑아 추적 파일 전체와 (선택) 커밋 메시지에서 찾는다. 검사 목록 자체는 어디에도 저장하지 않는다.

실행: python -m scripts.check_internal_leaks --internal-dir test_pairs --internal-dir corpus/local-samples [--messages-since REF]
찾으면 종료 코드 1 과 함께 파일 이름만 출력한다(찾은 문자열은 출력하지 않는다).
"""
import argparse
import os
import re
import subprocess
import sys
import unicodedata

_SPLIT = re.compile(r"[()\[\]_\s\-·,]+")
_SPACE = re.compile(r"\s+")
_HANGUL = re.compile("[가-힣]{4}")


def _nfc(text):
    return unicodedata.normalize("NFC", text)


def internal_terms(directories, with_body=True):
    terms = set()
    for directory in directories:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            stem = _nfc(os.path.splitext(name)[0]).strip()
            # 일반 영어 단어 오탐을 막으려고 한글이 4자 이상 이어지는 이름·조각만 쓴다
            if len(stem) >= 6 and _HANGUL.search(stem):
                terms.add(stem)
            terms.update(part for part in _SPLIT.split(stem) if len(part) >= 6 and _HANGUL.search(part))
            if with_body and name.lower().endswith((".hwpx", ".hwp")):
                terms.update(_body_lines(os.path.join(directory, name)))
    return terms


def _body_lines(path):
    try:
        from dochan import Dochan

        text = Dochan(path).to_plain_text()
    except Exception:
        return set()
    lines = set()
    for line in text.split("\n"):
        line = _nfc(_SPACE.sub(" ", line)).strip()
        if 18 <= len(line) <= 200 and re.search("[가-힣]{6}", line):
            lines.add(line)
    return lines


def _tracked_files(root):
    out = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True, check=True).stdout
    return [name.decode() for name in out.split(b"\0") if name]


def find_leaks(root, terms, messages_since=None):
    leaked = []
    for name in _tracked_files(root):
        try:
            with open(os.path.join(root, name), "rb") as handle:
                data = _nfc(_SPACE.sub(" ", handle.read().decode("utf-8", "ignore")))
        except OSError:
            continue
        if any(term in data for term in terms):
            leaked.append(name)
    if messages_since:
        log = subprocess.run(["git", "-C", root, "log", "--format=%B", messages_since + "..HEAD"],
                             capture_output=True, text=True, check=True).stdout
        if any(term in _nfc(_SPACE.sub(" ", log)) for term in terms):
            leaked.append("<commit messages since " + messages_since + ">")
    return leaked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal-dir", action="append", default=[])
    parser.add_argument("--public-dir", action="append", default=[],
                        help="공개 코퍼스 폴더 — 여기 파일 이름에도 있는 조각은 공개 정보로 보고 뺀다")
    parser.add_argument("--public-text", action="append", default=[],
                        help="공개 출처 색인 파일(예: docs/benchmarks/hwp-corpus-fixtures.json) — 이 안의 조각도 공개 정보로 본다")
    parser.add_argument("--root", default=".")
    parser.add_argument("--messages-since")
    parser.add_argument("--names-only", action="store_true", help="본문 문장 검사를 건너뛴다(빠름)")
    args = parser.parse_args(argv)
    terms = internal_terms(args.internal_dir, with_body=not args.names_only)
    public = " ".join(_nfc(name) for directory in args.public_dir if os.path.isdir(directory)
                      for _, _, names in os.walk(directory) for name in names)
    for path in args.public_text:
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="ignore") as handle:
                public += " " + _nfc(_SPACE.sub(" ", handle.read()))
    terms = {term for term in terms if term not in public}
    if not terms:
        print("내부 문서 폴더가 없어 검사를 건너뜁니다.")
        return 0
    leaked = find_leaks(args.root, terms, args.messages_since)
    for name in leaked:
        print("내부 문서 이름·본문이 들어 있음:", name)
    return 1 if leaked else 0


if __name__ == "__main__":
    sys.exit(main())
