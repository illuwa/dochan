"""
fallback/filter_server.py — 웹한글 기안기 필터 서버 연동
파싱 실패 시 폴백으로 사용하거나, GT(Ground Truth) 비교용

필터 서버 API:
  POST /convert — HWP → HTML/PDF 변환 요청
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger('dochan')


@dataclass
class FilterServerConfig:
    """필터 서버 연결 설정"""
    base_url: str = "http://localhost:8080"
    timeout: int = 30
    api_key: str = ""


class FilterServerClient:
    """웹한글 기안기 필터 서버 클라이언트"""

    def __init__(self, config: Optional[FilterServerConfig] = None):
        self.config = config or FilterServerConfig()
        self._available = None

    def is_available(self) -> bool:
        """필터 서버 접속 가능 여부"""
        if self._available is not None:
            return self._available

        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.config.base_url}/health",
                method='GET',
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self._available = resp.status == 200
        except Exception:
            self._available = False

        return self._available

    def convert_to_html(self, hwp_path: str) -> Optional[str]:
        """HWP → HTML 변환 (필터 서버 사용)"""
        if not self.is_available():
            logger.warning("필터 서버 사용 불가")
            return None

        try:
            import urllib.request

            with open(hwp_path, 'rb') as f:
                file_data = f.read()

            # multipart/form-data 전송
            boundary = '----HWPParserBoundary'
            filename = hwp_path.split('/')[-1]

            body = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f'Content-Type: application/octet-stream\r\n\r\n'
            ).encode('utf-8') + file_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')

            req = urllib.request.Request(
                f"{self.config.base_url}/convert",
                data=body,
                headers={
                    'Content-Type': f'multipart/form-data; boundary={boundary}',
                },
                method='POST',
            )

            if self.config.api_key:
                req.add_header('Authorization', f'Bearer {self.config.api_key}')

            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                return resp.read().decode('utf-8')

        except Exception as e:
            logger.error(f"필터 서버 변환 실패: {e}")
            return None

    def convert_as_fallback(self, hwp_path: str, original_errors: list) -> Optional[str]:
        """파싱 실패 시 폴백 변환"""
        logger.info(f"자체 파싱 실패 ({len(original_errors)}건 에러) → 필터 서버 폴백 시도")
        return self.convert_to_html(hwp_path)
