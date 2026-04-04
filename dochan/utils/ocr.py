"""
utils/ocr.py — Tesseract OCR 연동
이미지 바이너리 → 텍스트 추출 (한국어+영어)
"""

import io
import logging
from typing import Optional

logger = logging.getLogger('dochan')

# OCR 사용 가능 여부
_ocr_available = None


def is_ocr_available() -> bool:
    """Tesseract OCR 사용 가능 여부"""
    global _ocr_available
    if _ocr_available is not None:
        return _ocr_available

    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _ocr_available = True
    except Exception:
        _ocr_available = False

    return _ocr_available


def ocr_image(image_data: bytes, lang: str = 'kor+eng') -> str:
    """
    이미지 바이너리 → 텍스트 추출

    Args:
        image_data: 이미지 바이너리 (PNG/JPG/BMP 등)
        lang: Tesseract 언어 코드 (기본: 한국어+영어)

    Returns:
        추출된 텍스트 (빈 문자열 = 실패 또는 텍스트 없음)
    """
    if not is_ocr_available():
        return ""

    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_data))

        # 이미지 전처리 — OCR 정확도 향상
        # 그레이스케일 변환
        if img.mode != 'L':
            img = img.convert('L')

        # 너무 작은 이미지는 확대
        w, h = img.size
        if w < 200 or h < 50:
            scale = max(200 / w, 50 / h, 2)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        text = pytesseract.image_to_string(img, lang=lang, config='--psm 6')
        # 노이즈 제거: 1글자 줄, 의미없는 기호만 있는 줄 제거
        import re
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            line = line.strip()
            # 한글/영문/숫자가 2개 이상 포함된 줄만
            meaningful = re.findall(r'[가-힣a-zA-Z0-9]', line)
            if len(meaningful) >= 2:
                cleaned.append(line)
        return '\n'.join(cleaned)

    except Exception as e:
        logger.debug(f"OCR 실패: {e}")
        return ""


def ocr_image_to_blocks(image_data: bytes, lang: str = 'kor+eng') -> list:
    """
    이미지 → 텍스트 블록 목록 (위치 정보 포함)

    Returns:
        [{'text': str, 'confidence': float, 'bbox': (x,y,w,h)}, ...]
    """
    if not is_ocr_available():
        return []

    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(image_data))
        if img.mode != 'L':
            img = img.convert('L')

        data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)

        blocks = []
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])
            if text and conf > 30:  # 신뢰도 30% 이상만
                blocks.append({
                    'text': text,
                    'confidence': conf,
                    'bbox': (data['left'][i], data['top'][i],
                             data['width'][i], data['height'][i]),
                })

        return blocks

    except Exception as e:
        logger.debug(f"OCR 블록 추출 실패: {e}")
        return []
