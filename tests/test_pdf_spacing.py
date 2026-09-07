"""한글 줄 경계 확률과 모델 로딩 회귀 테스트."""
import json

import pytest

from dochan.pdf import layout, spacing
from dochan.pdf.content import Fragment, assemble_lines
from dochan.pdf.spacing import SpacingModel, load_model


def test_pair_probability_overrides_marginals_and_uses_strict_threshold():
    model = SpacingModel(prior=0.25, last={"의": 0.1}, first={"운": 0.1},
                         pairs={"의운": 0.9, "안보": 0.5})
    assert model.space_probability("의", "운") == 0.9
    assert model.joins_with_space("의", "운")
    assert not model.joins_with_space("안", "보")


def test_marginal_combination_uses_prior_odds():
    # odds = (1/1) * (1/3) / (1/3) = 1 → 확률 1/2
    model = SpacingModel(prior=0.25, last={"의": 0.5}, first={"운": 0.25})
    assert model.space_probability("의", "운") == pytest.approx(0.5)
    assert model.space_probability("의", "영") == pytest.approx(0.5)
    assert model.space_probability("안", "운") == pytest.approx(0.25)
    assert model.space_probability("안", "녕") == 0.25


@pytest.mark.parametrize("prior", [0.0, 1.0])
def test_extreme_probabilities_are_clamped_for_odds(prior):
    model = SpacingModel(prior=prior, last={"가": 1.0}, first={"나": 0.0})
    assert model.space_probability("가", "나") == pytest.approx(1 - max(0.01, min(0.99, prior)))


def _data(**changes):
    data = {"version": 1, "prior": 0.29, "min_pair_count": 5, "min_char_count": 20,
            "last": {"의": 0.8}, "first": {}, "pairs": {"의운": 0.9}}
    data.update(changes)
    return data


@pytest.mark.parametrize("content", [
    "", "{", "null", "[]", "{}", "\udcff",
    json.dumps(_data(version=2)), json.dumps(_data(prior="0.29")),
    json.dumps(_data(prior=float("nan"))), json.dumps(_data(prior=2)),
    json.dumps(_data(last=[])), json.dumps(_data(first={"운": True})),
    json.dumps(_data(pairs={"의운": -1})), json.dumps(_data(pairs={"의": 0.9})),
    json.dumps(_data(last={"a": 0.9})),
])
def test_invalid_model_returns_empty_model(tmp_path, content):
    path = tmp_path / "invalid.json"
    path.write_bytes(content.encode("utf-8", errors="surrogateescape"))
    model = load_model(path)
    assert model.prior == 0.29
    assert model.last == model.first == model.pairs == {}
    assert model.space_probability("의", "운") == 0.29


def test_missing_model_and_unreadable_resource_never_raise(tmp_path, monkeypatch):
    assert load_model(tmp_path / "missing.json").pairs == {}
    assert load_model(tmp_path).pairs == {}
    monkeypatch.setattr(spacing, "_DEFAULT_MODEL", None)

    def unavailable(package):
        raise RuntimeError("resource unavailable")

    monkeypatch.setattr(spacing.resources, "files", unavailable)
    assert load_model().pairs == {}


def test_default_model_is_lazy_singleton_and_explicit_path_is_independent(tmp_path, monkeypatch):
    path = tmp_path / "korean_spacing.json"
    path.write_text(json.dumps(_data()), encoding="utf-8")
    calls = []
    monkeypatch.setattr(spacing, "_DEFAULT_MODEL", None)

    def package_files(package):
        calls.append(package)
        return tmp_path

    monkeypatch.setattr(spacing.resources, "files", package_files)
    assert calls == []
    model = load_model()
    assert load_model() is model
    assert calls == ["dochan.pdf"]
    assert model.space_probability("의", "운") == 0.9
    assert load_model(tmp_path / "missing.json").pairs == {}
    assert load_model() is model


@pytest.mark.parametrize("last,first,without_space", [
    ("의", "운", False), ("안", "보", True), ("國", "民", True),
    ("한", "字", True), ("字", "한", True), ("2", "3", True),
    ("3", ".", True), (".", "3", False), ("a", "b", False),
    ("한", "a", False), ("", "가", False),
])
def test_layout_uses_model_and_preserves_other_rules(monkeypatch, last, first, without_space):
    model = SpacingModel(pairs={"의운": 0.9, "안보": 0.1})
    monkeypatch.setattr(layout, "load_model", lambda: model)
    assert layout._joins_without_space(last, first) is without_space


def test_observer_sees_previous_block_and_spacing_before_each_join(monkeypatch):
    monkeypatch.setattr(layout, "load_model", lambda: SpacingModel(pairs={"의운": 0.9, "안보": 0.1}))
    observed = []
    monkeypatch.setattr(layout, "JOIN_OBSERVER", lambda *args: observed.append(args))
    lines = assemble_lines([
        Fragment(0, 100 - 14 * i, 100, 10, text, 5, order=i)
        for i, text in enumerate(["이사회의", "운영안", "보", "hello", "제2조 목적"])
    ])
    blocks = layout.merge_lines(lines)
    # 관찰자는 병합된 블록이 아니라 직전 '줄' 원문을 받는다 — 앞선 예측 구분자가 라벨 문맥에 섞이지 않게
    assert observed == [("이사회의", "운영안", True),
                        ("운영안", "보", False),
                        ("보", "hello", True)]
    assert blocks[0].text == blocks[0].paragraph().text == "이사회의 운영안보 hello"
    monkeypatch.setattr(layout, "JOIN_OBSERVER", None)
    assert layout.merge_lines(lines) == blocks
    assert len(observed) == 3


def test_exact_marginal_tie_is_not_a_space():
    # prior 0.25, last 0.1, first 0.75 → 수학적으로 정확히 0.5 (부동소수 반올림으로 0.5000…01 이 될 수 있다)
    model = SpacingModel(prior=0.25, last={"다": 0.1}, first={"클": 0.75})
    assert not model.joins_with_space("다", "클")
    assert SpacingModel(prior=0.25, last={"다": 0.1}, first={"클": 0.76}).joins_with_space("다", "클")
