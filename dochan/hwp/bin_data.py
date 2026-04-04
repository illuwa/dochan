"""
hwp/bin_data.py — BinData 이미지 연결
OLE 스토리지의 BinData/ 하위에 저장된 바이너리 데이터를 추출
"""

import logging
import struct
import olefile
from dataclasses import dataclass
from typing import Dict, Optional

from ..utils.safe_decompress import safe_zlib_decompress

logger = logging.getLogger(__name__)


@dataclass
class BinDataItem:
    """추출된 바이너리 데이터"""
    storage_id: int = 0
    data: bytes = b""
    extension: str = ""

    @property
    def filename(self) -> str:
        return f"BIN{self.storage_id:04X}.{self.extension}" if self.extension else f"BIN{self.storage_id:04X}"


def extract_bin_data(ole: olefile.OleFileIO, is_compressed: bool) -> Dict[int, BinDataItem]:
    """
    OLE 스토리지에서 BinData/ 하위의 모든 바이너리 데이터 추출

    반환: {storage_id: BinDataItem} 딕셔너리
    """
    result = {}

    for entry in ole.listdir():
        if len(entry) >= 2 and entry[0] == 'BinData':
            storage_name = entry[1]  # 예: "BIN0001.bmp"

            try:
                # 스토리지 ID 추출 (BIN 접두어 제거, 16진수)
                base_name = storage_name.split('.')[0]
                if base_name.upper().startswith('BIN'):
                    storage_id = int(base_name[3:], 16)
                else:
                    continue

                # 확장자
                ext = storage_name.split('.')[-1] if '.' in storage_name else ""

                # 데이터 읽기
                raw_data = ole.openstream('/'.join(entry)).read()

                # 압축 해제 (문서가 압축 설정인 경우)
                if is_compressed:
                    try:
                        raw_data = safe_zlib_decompress(raw_data)
                    except (ValueError, Exception) as e:
                        logger.debug("BinData 압축 해제 실패 (비압축 데이터일 수 있음): %s", e)

                result[storage_id] = BinDataItem(
                    storage_id=storage_id,
                    data=raw_data,
                    extension=ext.lower(),
                )

            except (ValueError, struct.error, UnicodeDecodeError, OSError) as e:
                logger.warning("BinData 항목 '%s' 파싱 실패: %s", storage_name, e)
                continue

    return result


def link_images_to_bin_data(doc, bin_data_items: Dict[int, BinDataItem],
                            bin_data_entries: list):
    """
    Document 내 Image 객체에 실제 바이너리 데이터 연결

    bin_data_entries: DocInfo에서 파싱한 BinDataEntry 목록
    bin_data_items: OLE에서 추출한 BinDataItem 딕셔너리
    """
    from ..model.image import Image

    for section in doc.sections:
        for elem in section.elements:
            if isinstance(elem, Image) and elem.bin_id >= 0:
                # bin_id는 DocInfo의 BinDataEntry 인덱스 (0-based)
                if elem.bin_id < len(bin_data_entries):
                    entry = bin_data_entries[elem.bin_id]
                    storage_id = entry.bin_data_id

                    if storage_id in bin_data_items:
                        item = bin_data_items[storage_id]
                        elem.image_data = item.data
                        elem.filename = item.filename
