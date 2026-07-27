"""Image model — 이미지 참조 + OCR 텍스트"""
from dataclasses import dataclass, field


@dataclass
class Image:
    """문서 내 이미지 참조"""
    bin_id: int = -1
    filename: str = ""
    width: int = 0
    height: int = 0
    image_data: bytes = b""
    ocr_text: str = ""  # OCR 추출 텍스트
    alt_text: str = ""  # 그림 설명문 (HWPX shapeComment 등) — 대체 텍스트로 쓴다
    caption: list = field(default_factory=list)   # 캡션 문단 목록
    caption_side: str = "BOTTOM"                  # TOP | BOTTOM | LEFT | RIGHT

    @property
    def has_data(self) -> bool:
        return len(self.image_data) > 0

    @property
    def caption_text(self) -> str:
        from .table import flatten_block_texts
        return '\n'.join(flatten_block_texts(self.caption))

    def run_ocr(self) -> str:
        """이미지 데이터에 OCR 실행, 결과를 ocr_text에 저장"""
        if not self.has_data:
            return ""
        from ..utils.ocr import ocr_image
        self.ocr_text = ocr_image(self.image_data)
        return self.ocr_text
