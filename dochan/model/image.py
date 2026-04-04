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

    @property
    def has_data(self) -> bool:
        return len(self.image_data) > 0

    def run_ocr(self) -> str:
        """이미지 데이터에 OCR 실행, 결과를 ocr_text에 저장"""
        if not self.has_data:
            return ""
        from ..utils.ocr import ocr_image
        self.ocr_text = ocr_image(self.image_data)
        return self.ocr_text
