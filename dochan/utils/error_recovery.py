"""
utils/error_recovery.py — 에러 복구 전략
파싱 실패 시 부분 결과 보존 + 복구 시도
"""

import logging
from typing import Optional, Any

logger = logging.getLogger('dochan')


class ParseError(Exception):
    """파싱 에러 (복구 가능 여부 포함)"""
    def __init__(self, message: str, recoverable: bool = True, context: str = ""):
        super().__init__(message)
        self.recoverable = recoverable
        self.context = context


class ErrorRecovery:
    """에러 복구 매니저"""

    def __init__(self, strict: bool = False):
        self.strict = strict  # True: 에러 시 즉시 중단
        self.errors = []
        self.warnings = []

    def record_error(self, message: str, context: str = ""):
        """에러 기록"""
        self.errors.append(f"[{context}] {message}" if context else message)
        logger.error(message)
        if self.strict:
            raise ParseError(message, context=context)

    def record_warning(self, message: str, context: str = ""):
        """경고 기록"""
        self.warnings.append(f"[{context}] {message}" if context else message)
        logger.warning(message)

    def safe_parse(self, func, *args, default=None, context: str = "", **kwargs) -> Any:
        """안전한 파싱 — 실패 시 기본값 반환"""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            self.record_error(f"{e}", context=context)
            return default

    @property
    def summary(self) -> dict:
        return {
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'errors': self.errors,
            'warnings': self.warnings,
        }
