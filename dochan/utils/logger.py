"""
utils/logger.py — 로깅 설정
"""

import logging
import sys


def setup_logger(
    name: str = 'dochan',
    level: int = logging.INFO,
    log_file: str = None,
) -> logging.Logger:
    """dochan 로거 설정"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 핸들러 중복 방지
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # 콘솔 핸들러
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # 파일 핸들러 (선택)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
