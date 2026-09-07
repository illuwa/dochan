"""페이지 본문과 표 셀에 공통으로 쓰는 줄바꿈 병합."""
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from ..conversion import Provenance
from ..model.document import Paragraph, TextRun
from .spacing import load_model

# 숫자·문자 표식은 뒤에 공백이 와야 한다 — 줄 끝에서 잘린 "2023.12.19." 의
# 뒷부분("3.12.19.]")을 새 항목으로 오판하지 않기 위해서다.
_BLOCK_MARKER = re.compile(
    r'^(제\s*\d+\s*(조|항|호|장|절)|[①-⑳]|[⑴-⒇]|'
    r'(\(\d+\)|\d+[.)]|[가-힣][.)]|[a-zA-Z][.)])(?=\s|$)|[-•▪◦※○●■□◇◆])'
)
_CJK = re.compile(r'[가-힣\u3400-\u9fff\uf900-\ufaff]')
# 측정 전용 훅 (직전 줄 원문, 다음 줄, 공백 삽입 여부). 스레드 안전하지 않으며 라이브러리 동작을
# 바꾸지 않는다 — 훅의 예외는 삼킨다.
JOIN_OBSERVER: Optional[Callable[[str, str, bool], None]] = None


@dataclass
class TextBlock:
    """첫 줄의 크기와 그리기 순서를 보존하는 문단 후보."""
    text: str
    size: float
    order: int
    runs: List[Tuple[str, bool, bool]] = field(default_factory=list)

    def paragraph(self, page_number: Optional[int] = None) -> Paragraph:
        provenance = Provenance(source_format='pdf', page=page_number)
        return Paragraph(
            runs=[TextRun(text=t, bold=b, italic=i, provenance=provenance)
                  for t, b, i in self.runs], provenance=provenance,
        )


def _trim_runs(runs):
    """줄 가장자리 공백만 제거하며 내부 서식과 공백은 보존한다."""
    runs = list(runs)
    while runs:
        text, bold, italic = runs[0]
        if text.lstrip():
            runs[0] = (text.lstrip(), bold, italic)
            break
        runs.pop(0)
    while runs:
        text, bold, italic = runs[-1]
        if text.rstrip():
            runs[-1] = (text.rstrip(), bold, italic)
            break
        runs.pop()
    return runs


def _joins_without_space(last: str, first: str) -> bool:
    """한글 경계는 통계로 판정하고, 한자·숫자는 기존 규칙으로 잇는다."""
    if len(last) == len(first) == 1 and '가' <= last <= '힣' and '가' <= first <= '힣':
        return not load_model().joins_with_space(last, first)
    if _CJK.fullmatch(last) and _CJK.fullmatch(first):
        return True
    return last.isdigit() and (first.isdigit() or first == '.')


def merge_lines(lines, inner_bounds=None) -> List[TextBlock]:
    """같은 흐름의 꽉 찬 줄만 다음 줄과 이어 붙인다."""
    if not lines:
        return []
    right = max(line.right for line in lines)
    full_edge = 0.90 * right
    if inner_bounds is not None and len(lines) >= 2:
        left, right = inner_bounds
        full_edge = left + 0.90 * (right - left)
    blocks = []
    previous = None
    for line in lines:
        if not line.text:
            continue
        joins = (previous is not None and previous.right >= full_edge
                 and 0 < previous.y - line.y <= 1.8 * previous.size
                 and 0.85 * previous.last_size <= line.first_size <= 1.15 * previous.last_size
                 and not _BLOCK_MARKER.match(line.text))
        if joins:
            block = blocks[-1]
            sep = '' if _joins_without_space(block.text[-1:], line.text[:1]) else ' '
            if JOIN_OBSERVER is not None:
                # 직전 '줄' 원문을 넘긴다 — 병합 블록을 넘기면 앞선 예측 구분자가 라벨 문맥에 섞인다
                try:
                    JOIN_OBSERVER(previous.text, line.text, bool(sep))
                except Exception:  # 측정 훅의 실패가 문서 파싱을 중단시키면 안 된다
                    pass
            block.text += sep + line.text
            if sep:
                block.runs.append((sep, False, False))
            block.runs.extend(_trim_runs(line.runs))
        else:
            blocks.append(TextBlock(line.text, line.size, line.order, _trim_runs(line.runs)))
        previous = line
    return blocks
