"""한글 줄 경계의 공백 확률 — 문자쌍과 주변 확률의 결합."""
import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Dict, Optional


def _odds(probability: float) -> float:
    probability = max(0.01, min(0.99, probability))
    return probability / (1 - probability)


@dataclass
class SpacingModel:
    """자주 관측한 문자쌍을 우선하고, 없으면 주변 확률로 판정한다."""
    prior: float = 0.29
    last: Dict[str, float] = field(default_factory=dict)
    first: Dict[str, float] = field(default_factory=dict)
    pairs: Dict[str, float] = field(default_factory=dict)

    def space_probability(self, last: str, first: str) -> float:
        pair = last + first
        if pair in self.pairs:
            return self.pairs[pair]
        if last not in self.last and first not in self.first:
            return self.prior
        odds = (_odds(self.last.get(last, self.prior))
                * _odds(self.first.get(first, self.prior)) / _odds(self.prior))
        return odds / (1 + odds)

    def joins_with_space(self, last: str, first: str) -> bool:
        # 수학적 동률(정확히 0.5)은 부동소수 오차로 0.5000…01 이 될 수 있다 — 동률은 무공백으로 둔다
        return self.space_probability(last, first) > 0.5 + 1e-9


_DEFAULT_MODEL: Optional[SpacingModel] = None


def _is_probability(value) -> bool:
    return type(value) in (int, float) and 0 <= value <= 1


def _read_model(path) -> SpacingModel:
    """누락·손상된 리소스는 빈 모델로 대체한다."""
    try:
        source = (resources.files("dochan.pdf").joinpath("korean_spacing.json")
                  if path is None else Path(path))
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            return SpacingModel()
        if not _is_probability(data.get("prior")):
            return SpacingModel()
        for name, length in (("last", 1), ("first", 1), ("pairs", 2)):
            table = data.get(name)
            if not isinstance(table, dict) or any(
                len(key) != length or not all("가" <= c <= "힣" for c in key)
                or not _is_probability(value) for key, value in table.items()
            ):
                return SpacingModel()
        for name in ("min_pair_count", "min_char_count"):
            if type(data.get(name, 1)) is not int or data.get(name, 1) < 1:
                return SpacingModel()
        return SpacingModel(prior=data["prior"], last=data["last"],
                            first=data["first"], pairs=data["pairs"])
    except Exception:  # 모델 로딩 실패가 문서 파싱을 중단시키면 안 된다
        return SpacingModel()


def load_model(path=None) -> SpacingModel:
    """기본 리소스는 최초 사용 시 한 번만 읽고, 지정 경로는 별도로 읽는다."""
    global _DEFAULT_MODEL
    if path is not None:
        return _read_model(path)
    if _DEFAULT_MODEL is None:
        _DEFAULT_MODEL = _read_model(None)
    return _DEFAULT_MODEL
