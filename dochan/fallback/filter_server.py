"""
fallback/filter_server.py — 웹한글 기안기 필터 서버 연동
파싱 실패 시 폴백으로 사용하거나, GT(Ground Truth) 비교용

필터 서버 API:
  POST /convert — HWP → HTML/PDF 변환 요청
"""

import logging
from pathlib import Path
import secrets
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

logger = logging.getLogger('dochan')


@dataclass
class FilterServerConfig:
    """필터 서버 연결 설정"""
    base_url: str = "http://localhost:8080"
    timeout: int = 30
    api_key: str = ""
    health_cache_seconds: float = 5.0
    max_upload_bytes: int = 200 * 1024 * 1024
    max_response_bytes: int = 50 * 1024 * 1024


class FilterServerClient:
    """웹한글 기안기 필터 서버 클라이언트"""

    def __init__(self, config: Optional[FilterServerConfig] = None):
        self.config = config or FilterServerConfig()
        self._available = None
        self._available_checked_at = 0.0

    def _endpoint(self, path: str) -> str:
        base_url = self.config.base_url.rstrip('/')
        parsed = urlsplit(base_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            raise ValueError("filter server base_url must be an HTTP(S) URL")
        return f"{base_url}/{path.lstrip('/')}"

    @staticmethod
    def _open_http(request, timeout):
        """Open a request whose URL has already passed `_endpoint` validation."""
        import urllib.request

        parsed = urlsplit(request.full_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            raise ValueError("filter server request must use HTTP(S)")
        # The request URL is constrained above to HTTP(S) with a hostname.
        return urllib.request.urlopen(  # nosemgrep: dynamic-urllib-use-detected
            request,
            timeout=timeout,
        )

    def is_available(self) -> bool:
        """필터 서버 접속 가능 여부"""
        cache_age = time.monotonic() - self._available_checked_at
        if (
            self._available is True
            and cache_age < max(float(self.config.health_cache_seconds), 0.0)
        ):
            return True

        try:
            import urllib.request
            req = urllib.request.Request(
                self._endpoint('/health'),
                method='GET',
            )
            health_timeout = min(max(float(self.config.timeout), 0.1), 5.0)
            with self._open_http(req, timeout=health_timeout) as resp:
                self._available = resp.status == 200
        except Exception:
            self._available = False

        self._available_checked_at = time.monotonic()

        return self._available

    def convert_to_html(self, hwp_path: str) -> Optional[str]:
        """HWP → HTML 변환 (필터 서버 사용)"""
        if not self.is_available():
            logger.warning("필터 서버 사용 불가")
            return None

        try:
            import urllib.request

            with open(hwp_path, 'rb') as f:
                file_data = f.read(self.config.max_upload_bytes + 1)
            if len(file_data) > self.config.max_upload_bytes:
                logger.error("필터 서버 업로드 크기 제한 초과")
                return None

            # multipart/form-data 전송
            boundary = f"----DochanBoundary{secrets.token_hex(16)}"
            filename = Path(hwp_path).name.replace('\r', '_').replace('\n', '_').replace('"', '_')

            body = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f'Content-Type: application/octet-stream\r\n\r\n'
            ).encode('utf-8') + file_data + f'\r\n--{boundary}--\r\n'.encode('utf-8')

            req = urllib.request.Request(
                self._endpoint('/convert'),
                data=body,
                headers={
                    'Content-Type': f'multipart/form-data; boundary={boundary}',
                },
                method='POST',
            )

            if self.config.api_key:
                if '\r' in self.config.api_key or '\n' in self.config.api_key:
                    raise ValueError("filter server api_key contains invalid header characters")
                req.add_header('Authorization', f'Bearer {self.config.api_key}')

            with self._open_http(req, timeout=self.config.timeout) as resp:
                response_data = resp.read(self.config.max_response_bytes + 1)
                if len(response_data) > self.config.max_response_bytes:
                    raise ValueError("filter server response exceeds size limit")
                return response_data.decode('utf-8')

        except Exception as e:
            self._available = False
            self._available_checked_at = 0.0
            logger.error(f"필터 서버 변환 실패: {e}")
            return None

    def convert_as_fallback(self, hwp_path: str, original_errors: list) -> Optional[str]:
        """파싱 실패 시 폴백 변환"""
        logger.info(f"자체 파싱 실패 ({len(original_errors)}건 에러) → 필터 서버 폴백 시도")
        return self.convert_to_html(hwp_path)
