"""dochan — HWP/HWPX 문서 파서, AI/LLM 최적 Markdown 변환"""
__version__ = "1.0.0"

from .reader import Dochan

# 하위 호환 별칭
HWPReader = Dochan

__all__ = ['Dochan', 'HWPReader']
