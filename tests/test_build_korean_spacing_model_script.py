"""학습 카운터, 예외 쌍 압축과 실제 CLI 검증."""
import json
import unicodedata
from collections import Counter

from scripts.build_korean_spacing_model import build_model, count_text, merge_counts, _count_file
from test_hwpx_reader import _section, _text_para, _write_hwpx


def test_count_text_counts_only_adjacent_hangul_with_optional_space():
    counts = count_text("이사회의 운영에 관한")
    pairs = [("이", "사"), ("사", "회"), ("회", "의"), ("의", "운"),
             ("운", "영"), ("영", "에"), ("에", "관"), ("관", "한")]
    assert counts["total"] == Counter(pairs)
    assert counts["space"] == Counter({("의", "운"): 1, ("에", "관"): 1})
    assert counts["last_total"] == Counter("이사회의운영에관")
    assert counts["first_total"] == Counter("사회의운영에관한")
    assert counts["last_space"] == Counter("의에")
    assert counts["first_space"] == Counter("운관")
    assert count_text(unicodedata.normalize("NFD", "이사회의\n\t운영에  관한")) == counts
    assert not count_text("가,나|다1라|마漢바|사a아")["total"]


def test_merge_counts_adds_files_without_creating_cross_file_pairs():
    left, right = count_text("가 나"), count_text("다라")
    merged = merge_counts([left, right])
    assert merged["total"] == Counter({("가", "나"): 1, ("다", "라"): 1})
    assert merged["space"] == Counter({("가", "나"): 1})
    assert left == count_text("가 나") and right == count_text("다라")


def test_build_model_keeps_exception_pairs_and_rounds():
    # 주변 표를 제외하면 prior=0.5. 결정이 다른 가나와 차이가 큰 마바만 보존한다.
    counts = count_text("|".join(["가 나"] * 16 + ["가나"] * 14
                                 + ["다 라"] * 12 + ["다라"] * 18
                                 + ["마 바"] * 3 + ["마바"] * 27
                                 + ["사 아"] * 29 + ["사아"]
                                 + ["자 차", "자차"]))
    model = build_model(counts, min_pair_count=5, min_char_count=100,
                        exception_threshold=0.2)
    assert model == {"version": 1, "prior": 0.5, "min_pair_count": 5, "min_char_count": 100,
                     "last": {}, "first": {}, "pairs": {"가나": 0.53, "마바": 0.1, "사아": 0.97}}


def test_build_model_applies_minimum_counts_and_marginals():
    counts = count_text("|".join(["가 나"] * 20 + ["다라"] * 20 + ["마 바"]))
    model = build_model(counts)
    assert model["last"] == {"가": 1.0, "다": 0.0}
    assert model["first"] == {"나": 1.0, "라": 0.0}
    assert model["pairs"] == {}
    empty = build_model(count_text(""))
    assert empty["prior"] == 0.29
    assert empty["last"] == empty["first"] == empty["pairs"] == {}


def test_count_file_skips_missing_empty_invalid_and_oversized(tmp_path):
    assert _count_file(str(tmp_path / "missing.hwpx")) is None
    invalid = tmp_path / "invalid.hwp"
    invalid.write_bytes(b"invalid")
    assert _count_file(str(invalid)) is None
    empty = tmp_path / "empty.hwpx"
    _write_hwpx(empty, _section(_text_para(" ")))
    assert _count_file(str(empty)) is None
    huge = tmp_path / "huge.hwpx"
    with huge.open("wb") as handle:
        handle.truncate(50 * 1024 * 1024 + 1)
    assert _count_file(str(huge)) is None


def test_cli_builds_model_from_multiple_directories_case_insensitively(tmp_path, capsys):
    # subprocess 대신 main(argv) 를 직접 호출한다 — 인자 파싱까지 같은 경로를 타고, 보안 게이트의
    # subprocess 감사 규칙에도 걸리지 않는다
    from scripts.build_korean_spacing_model import main

    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _write_hwpx(first / "one.hwpx", _section(_text_para("이사회의 운영에 관한")))
    _write_hwpx(second / "two.HWPX", _section(_text_para("이사회의 운영에 관한")))
    (second / "bad.HWP").write_bytes(b"broken")
    (second / "ignored.txt").write_text("ignored")
    output = tmp_path / "model.json"
    exit_code = main([str(first), str(second), "--output", str(output), "--workers", "2",
                      "--min-pair-count", "1", "--min-char-count", "2",
                      "--exception-threshold", "0.2", "--limit", "0"])
    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    model = json.loads(output.read_text(encoding="utf-8"))
    assert model["version"] == 1
    assert model["prior"] == 0.25
    assert model["last"]["의"] == model["first"]["운"] == 1.0
    assert "parsed=2" in captured.out and "skipped=1" in captured.out
    assert "syllable_pairs=16" in captured.out
