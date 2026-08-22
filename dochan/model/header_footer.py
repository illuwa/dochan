"""Header/footer and note models."""
from dataclasses import dataclass, field
from typing import Optional


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
    number: Optional[int] = None

    @property
    def text(self) -> str:
        return '\n'.join(p.text for p in self.paragraphs if hasattr(p, 'text'))


@dataclass
class Comment(Footnote):
    """DOCX comment with its document-order number and author."""
    type: str = "comment"
    author: str = ""
