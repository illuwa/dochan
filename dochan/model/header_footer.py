"""HeaderFooter / Footnote model"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class HeaderFooter:
    """머리글/바닥글"""
    type: str = "header"  # "header" or "footer"
    paragraphs: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n'.join(p.text for p in self.paragraphs if hasattr(p, 'text'))


@dataclass
class Footnote:
    """각주/미주"""
    type: str = "footnote"  # "footnote" or "endnote"
    paragraphs: list = field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n'.join(p.text for p in self.paragraphs if hasattr(p, 'text'))
