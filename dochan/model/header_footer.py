"""HeaderFooter / Footnote model"""
from dataclasses import dataclass, field
from typing import List

from .table import flatten_block_texts


@dataclass
class HeaderFooter:
    """머리글/바닥글"""
    type: str = "header"  # "header" or "footer"
    paragraphs: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n'.join(flatten_block_texts(self.paragraphs))


@dataclass
class Footnote:
    """각주/미주/주석"""
    type: str = "footnote"  # "footnote" | "endnote" | "comment"
    paragraphs: list = field(default_factory=list)
    number: int = 0  # 파서가 부여한 참조 번호 (0이면 렌더러가 자체 부여)

    @property
    def text(self) -> str:
        return '\n'.join(flatten_block_texts(self.paragraphs))
