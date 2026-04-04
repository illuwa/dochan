"""
hwp/header.py — FileHeader 파싱
스펙 표 3 (256바이트 고정 크기)
"""
import struct
from dataclasses import dataclass


@dataclass
class FileHeader:
    signature: str = ""
    version: tuple = (0, 0, 0, 0)  # (rr, PP, nn, MM)
    is_compressed: bool = False     # bit 0
    is_encrypted: bool = False      # bit 1
    is_distribution: bool = False   # bit 2
    has_scripts: bool = False       # bit 3
    is_drm: bool = False            # bit 4
    has_xml_template: bool = False  # bit 5
    has_doc_history: bool = False   # bit 6
    has_digital_sign: bool = False  # bit 7
    has_cert_encrypt: bool = False  # bit 8
    has_cert_drm: bool = False      # bit 10
    is_ccl: bool = False            # bit 11
    is_mobile: bool = False         # bit 12
    is_privacy: bool = False        # bit 13
    is_track_change: bool = False   # bit 14
    is_kogl: bool = False           # bit 15
    has_video: bool = False         # bit 16

    @classmethod
    def parse(cls, data: bytes) -> 'FileHeader':
        if len(data) < 256:
            raise ValueError(f"FileHeader는 최소 256바이트, 현재 {len(data)}바이트")
        h = cls()
        h.signature = data[0:32].decode('latin-1').rstrip('\x00')

        # 버전: offset 32, 4바이트 (rr, PP, nn, MM 순서로 저장)
        h.version = struct.unpack_from("<BBBB", data, 32)

        # 속성: offset 36, DWORD
        props = struct.unpack_from("<I", data, 36)[0]
        h.is_compressed    = bool(props & (1 << 0))
        h.is_encrypted     = bool(props & (1 << 1))
        h.is_distribution  = bool(props & (1 << 2))
        h.has_scripts      = bool(props & (1 << 3))
        h.is_drm           = bool(props & (1 << 4))
        h.has_xml_template = bool(props & (1 << 5))
        h.has_doc_history  = bool(props & (1 << 6))
        h.has_digital_sign = bool(props & (1 << 7))
        h.has_cert_encrypt = bool(props & (1 << 8))
        h.has_cert_drm     = bool(props & (1 << 10))
        h.is_ccl           = bool(props & (1 << 11))
        h.is_mobile        = bool(props & (1 << 12))
        h.is_privacy       = bool(props & (1 << 13))
        h.is_track_change  = bool(props & (1 << 14))
        h.is_kogl          = bool(props & (1 << 15))
        h.has_video        = bool(props & (1 << 16))
        return h

    @property
    def major_version(self) -> int:
        return self.version[3]  # MM

    @property
    def body_storage(self) -> str:
        return "ViewText" if self.is_distribution else "BodyText"

    def validate(self) -> list:
        issues = []
        if "HWP Document File" not in self.signature:
            issues.append("ERR: HWP 서명 불일치")
        if self.major_version < 5:
            issues.append(f"ERR: v{self.major_version}.x 미지원")
        if self.is_encrypted:
            issues.append("WARN: 암호화 문서 → 전처리 필요")
        if self.is_drm:
            issues.append("WARN: DRM 문서 → 필터 서버 폴백")
        return issues
