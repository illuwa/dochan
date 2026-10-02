"""
utils/image_export.py — 문서에 들어 있는 이미지 바이너리를 파일로 저장한다

모든 형식이 같은 `Image.image_data` 를 채우므로 형식과 무관하게 동작한다. 파일 이름은 문서가 아니라
호출자가 준 이름(stem)과 순번으로만 만들어, 문서 속 경로가 출력 위치를 바꾸지 못하게 한다.
"""

import hashlib
import os
import re
import tempfile
from typing import List

# 바이트 서명이 형식 표기보다 믿을 만하다 — 확장자는 서명에서 먼저 정한다
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"II*\x00", "tif"),
    (b"MM\x00*", "tif"),
    (b"\x00\x00\x00\x0cjP  ", "jp2"),
    (b"\xd7\xcd\xc6\x9a", "wmf"),
)
_FORMAT_ALIASES = {"jpeg": "jpg", "tiff": "tif", "dib": "bmp"}
_SAFE_STEM = re.compile(r"[^\w.\-가-힣]+")


def image_extension(data: bytes, declared: str = "") -> str:
    for signature, ext in _SIGNATURES:
        if data.startswith(signature):
            return ext
    if len(data) >= 44 and data[40:44] == b" EMF":
        return "emf"
    declared = (declared or "").lower().lstrip(".")
    declared = _FORMAT_ALIASES.get(declared, declared)
    return declared if re.fullmatch(r"[a-z0-9]{1,5}", declared or "") else "bin"


def _safe_stem(stem: str) -> str:
    base = os.path.basename(stem.replace("\\", "/")) or "document"
    cleaned = _SAFE_STEM.sub("_", base).strip("._") or "document"
    return cleaned[:100]


def export_images(doc, out_dir: str, stem: str) -> List[str]:
    """문서 순서대로 서로 다른 이미지 바이트를 `<stem>-image-NNN.<ext>` 로 저장하고 경로를 돌려준다.

    같은 바이트가 여러 번 나오면 처음 한 번만 저장한다. 데이터 없는 참조는 건너뛴다.
    """
    if os.path.exists(out_dir) and not os.path.isdir(out_dir):
        raise NotADirectoryError(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    stem = _safe_stem(stem)
    written: List[str] = []
    seen = set()
    for image in doc.find_all("image"):
        data = getattr(image, "image_data", b"") or b""
        if not data:
            continue
        digest = hashlib.sha256(data).digest()
        if digest in seen:
            continue
        seen.add(digest)
        ext = image_extension(data, getattr(image, "image_format", ""))
        path = os.path.join(out_dir, f"{stem}-image-{len(written) + 1:03d}.{ext}")
        fd, tmp = tempfile.mkstemp(prefix=".dochan-image-", dir=out_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        written.append(path)
    return written
