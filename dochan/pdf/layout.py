"""페이지 본문과 표 셀에 공통으로 쓰는 줄바꿈 병합."""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..conversion import Provenance
from ..model.document import Paragraph, TextRun

# 숫자·문자 표식은 뒤에 공백이 와야 한다 — 줄 끝에서 잘린 "2023.12.19." 의
# 뒷부분("3.12.19.]")을 새 항목으로 오판하지 않기 위해서다.
_BLOCK_MARKER = re.compile(
    r'^(제\s*\d+\s*(조|항|호|장|절)|[①-⑳]|[⑴-⒇]|'
    r'(\(\d+\)|\d+[.)]|[가-힣][.)]|[a-zA-Z][.)])(?=\s|$)|[-•▪◦※○●■□◇◆])'
)
_CJK = re.compile(r'[가-힣\u3400-\u9fff\uf900-\ufaff]')


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
    """줄 끝에서 잘린 한글 어절과 숫자는 공백 없이 잇는다.

    한글은 글자 단위로 줄이 바뀌므로 어절 안에서 끊긴 경우가 많고,
    "2023.12.19." 같은 숫자도 줄 끝에서 갈라진다. 그 외(영문 단어 사이 등)는
    공백 하나로 잇는다.
    """
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
            block.text += sep + line.text
            if sep:
                block.runs.append((sep, False, False))
            block.runs.extend(_trim_runs(line.runs))
        else:
            blocks.append(TextBlock(line.text, line.size, line.order, _trim_runs(line.runs)))
        previous = line
    return blocks
