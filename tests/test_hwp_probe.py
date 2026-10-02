"""실물 검증기가 불완전한 투영을 성공으로 보고하지 않는지 검증한다."""
import io
import struct
from types import SimpleNamespace

from scripts.probe_hwp_features import _final_projection_body


def _record(tag, data, level=0):
    return struct.pack('<I', tag | level << 10 | len(data) << 20) + data


class ProbeOle:
    def __init__(self, body='same', view='same', doc_info=b''):
        def section(text):
            return (_record(66, bytes(22))
                    + _record(67, (text + '\r').encode('utf-16-le'), 1))
        self.streams = {'DocInfo': doc_info,
                        'BodyText/Section0': section(body),
                        'ViewText/Section0': section(view)}

    def listdir(self):
        return [key.split('/') for key in self.streams]

    def openstream(self, path):
        if isinstance(path, list):
            path = '/'.join(path)
        return io.BytesIO(self.streams[path])

    def get_size(self, path):
        if isinstance(path, list):
            path = '/'.join(path)
        return len(self.streams[path])


def test_final_projection_probe_checks_body_and_not_only_hwpx_pair():
    header = SimpleNamespace(is_compressed=False)
    assert _final_projection_body(ProbeOle(), header)['passed']
    assert not _final_projection_body(ProbeOle(body='different'), header)['passed']


def test_final_projection_probe_rejects_equal_truncated_prefixes(monkeypatch):
    monkeypatch.setattr('dochan.hwp.section.MAX_HWP_RECORDS', 1)
    result = _final_projection_body(ProbeOle(), SimpleNamespace(is_compressed=False))
    assert result['exact']
    assert result['ViewText']['record_limit']
    assert not result['passed']


def test_final_projection_probe_does_not_hide_broken_doc_info():
    broken = struct.pack('<I', 96 | 26 << 20) + b'x'
    result = _final_projection_body(ProbeOle(doc_info=broken), SimpleNamespace(is_compressed=False))
    assert result['exact']
    assert not result['passed']
