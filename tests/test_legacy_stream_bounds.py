import zlib

import pytest

from dochan import Dochan
from dochan.hwp.bin_data import extract_bin_data
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.ppt import PPTReader
from dochan.office_binary.xls import XLSReader
from dochan.utils.bounded_io import (
    ByteBudget,
    ResourceLimitError,
    read_bounded,
    read_ole_stream,
)


class _TrackingStream:
    def __init__(self, data):
        self.data = data
        self.requests = []

    def read(self, size):
        self.requests.append(size)
        return self.data[:size]


class _SizedOle:
    def __init__(self, data):
        self.data = data
        self.opened = []
        self.stream = _TrackingStream(data)

    def get_size(self, name):
        return len(self.data)

    def openstream(self, name):
        self.opened.append(name)
        return self.stream


def test_ole_stream_accepts_exact_limit_and_requests_only_limit_plus_one():
    ole = _SizedOle(b"1234")

    assert read_ole_stream(ole, "Data", max_bytes=4) == b"1234"
    assert ole.stream.requests == [5]


def test_ole_stream_rejects_declared_limit_plus_one_before_opening():
    ole = _SizedOle(b"12345")

    with pytest.raises(ResourceLimitError, match="per-stream limit"):
        read_ole_stream(ole, "Data", max_bytes=4)

    assert ole.opened == []


def test_unsized_stream_rejects_actual_limit_plus_one_with_bounded_read():
    stream = _TrackingStream(b"12345")

    with pytest.raises(ResourceLimitError, match="read limit"):
        read_bounded(stream, 4, label="Data")

    assert stream.requests == [5]


def test_size_aware_reader_type_error_never_retries_with_unbounded_read():
    class BrokenStream:
        def __init__(self):
            self.requests = []

        def read(self, size=-1):
            self.requests.append(size)
            if size == -1:
                raise AssertionError("must not retry as an unbounded read")
            raise TypeError("bounded read failed")

    stream = BrokenStream()

    with pytest.raises(TypeError, match="bounded read failed"):
        read_bounded(stream, 4)

    assert stream.requests == [5]


@pytest.mark.parametrize("payload", [b"1234", bytearray(b"1234"), memoryview(b"1234")])
def test_bounded_read_accepts_bytes_like_test_doubles(payload):
    assert read_bounded(payload, 4) == b"1234"


def test_ole_stream_budget_rejects_aggregate_before_second_open():
    class Ole:
        def __init__(self):
            self.opened = []

        def get_size(self, name):
            return 3

        def openstream(self, name):
            self.opened.append(name)
            return b"abc"

    ole = Ole()
    budget = ByteBudget(5)

    assert read_ole_stream(ole, "First", max_bytes=4, budget=budget) == b"abc"
    with pytest.raises(ResourceLimitError, match="document stream budget"):
        read_ole_stream(ole, "Second", max_bytes=4, budget=budget)

    assert ole.opened == ["First"]


@pytest.mark.parametrize(
    ("ole_target", "limit_target", "reader_type", "stream_name", "format_name"),
    [
        (
            "dochan.office_binary.doc.olefile.OleFileIO",
            "dochan.office_binary.doc.MAX_OLE_STREAM_SIZE",
            DOCReader,
            "WordDocument",
            "DOC",
        ),
        (
            "dochan.office_binary.ppt.olefile.OleFileIO",
            "dochan.office_binary.ppt.MAX_OLE_STREAM_SIZE",
            PPTReader,
            "PowerPoint Document",
            "PPT",
        ),
        (
            "dochan.office_binary.xls.olefile.OleFileIO",
            "dochan.office_binary.xls.MAX_OLE_STREAM_SIZE",
            XLSReader,
            "Workbook",
            "XLS",
        ),
    ],
)
def test_legacy_readers_fail_closed_on_oversized_declared_stream(
    monkeypatch,
    tmp_path,
    ole_target,
    limit_target,
    reader_type,
    stream_name,
    format_name,
):
    class OversizedOle:
        opened = False

        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name == stream_name

        def get_size(self, name):
            return 9

        def openstream(self, name):
            type(self).opened = True
            raise AssertionError("oversized stream must not be opened")

        def close(self):
            pass

    monkeypatch.setattr(ole_target, OversizedOle)
    monkeypatch.setattr(limit_target, 8)
    path = tmp_path / f"oversized.{format_name.lower()}"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    document = reader_type().read(str(path))

    assert document.sections == []
    assert document.source_format == format_name.lower()
    assert document.errors == [
        f"ERR: {format_name} stream validation failed: "
        f"{stream_name} exceeds per-stream limit: 9 > 8 bytes"
    ]
    assert OversizedOle.opened is False


@pytest.mark.parametrize(
    ("reader_type", "format_name"),
    [(DOCReader, "doc"), (PPTReader, "ppt"), (XLSReader, "xls")],
)
def test_legacy_reader_missing_path_remains_a_document_error(
    tmp_path, reader_type, format_name
):
    document = reader_type().read(str(tmp_path / f"missing.{format_name}"))

    assert document.source_format == format_name
    assert document.sections == []
    assert len(document.errors) == 1
    assert "OLE 파일 열기 실패" in document.errors[0]


def _valid_hwp_header():
    header = bytearray(256)
    signature = b"HWP Document File"
    header[:len(signature)] = signature
    header[35] = 5
    return bytes(header)


class _NoArgumentStream:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


def test_hwp_accepts_exact_256_byte_header_with_no_argument_fake(monkeypatch, tmp_path):
    header = _valid_hwp_header()

    class HwpOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name in {"FileHeader", "DocInfo"}

        def get_size(self, name):
            return len(header) if name == "FileHeader" else 0

        def openstream(self, name):
            return _NoArgumentStream(header if name == "FileHeader" else b"")

        def listdir(self, *args, **kwargs):
            return []

        def close(self):
            pass

    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", HwpOle)
    path = tmp_path / "exact-header.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    document = Dochan(str(path)).doc

    assert document.source_format == "hwp"
    assert document.file_header is not None
    assert document.errors == []


def test_hwp_rejects_non_exact_file_header_before_opening(monkeypatch, tmp_path):
    class OversizedHeaderOle:
        opened = False

        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name in {"FileHeader", "DocInfo"}

        def get_size(self, name):
            return 257

        def openstream(self, name):
            type(self).opened = True
            raise AssertionError("invalid FileHeader must not be opened")

        def close(self):
            pass

    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", OversizedHeaderOle)
    path = tmp_path / "oversized-header.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    document = Dochan(str(path)).doc

    assert document.sections == []
    assert document.file_header is None
    assert document.errors == [
        "ERR: HWP stream validation failed: "
        "FileHeader size mismatch: declared=257, expected=256 bytes"
    ]
    assert OversizedHeaderOle.opened is False


def test_hwp_section_over_limit_discards_previously_parsed_state(
    monkeypatch, tmp_path
):
    header = _valid_hwp_header()

    class OversizedSectionOle:
        section_opened = False

        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name in {"FileHeader", "DocInfo", "BodyText/Section0"}

        def get_size(self, name):
            return {
                "FileHeader": 256,
                "DocInfo": 0,
                "BodyText/Section0": 9,
            }[name]

        def openstream(self, name):
            if name == "BodyText/Section0":
                type(self).section_opened = True
                raise AssertionError("oversized section must not be opened")
            return _NoArgumentStream(header if name == "FileHeader" else b"")

        def listdir(self, *args, **kwargs):
            return [["BodyText", "Section0"]]

        def close(self):
            pass

    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", OversizedSectionOle)
    monkeypatch.setattr("dochan.reader.MAX_OLE_STREAM_SIZE", 8)
    path = tmp_path / "oversized-section.hwp"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    document = Dochan(str(path)).doc

    assert document.sections == []
    assert document.file_header is None
    assert document.errors == [
        "ERR: HWP stream validation failed: "
        "BodyText/Section0 exceeds per-stream limit: 9 > 8 bytes"
    ]
    assert OversizedSectionOle.section_opened is False


def test_hwp_bindata_aggregate_limit_rejects_before_second_payload_open():
    class BinDataOle:
        def __init__(self):
            self.opened = []

        def listdir(self):
            return [
                ["BinData", "BIN0001.png"],
                ["BinData", "BIN0002.png"],
            ]

        def get_size(self, name):
            return 3

        def openstream(self, name):
            self.opened.append(name)
            return b"png"

    ole = BinDataOle()

    with pytest.raises(ResourceLimitError, match="document stream budget"):
        extract_bin_data(
            ole,
            False,
            max_item_size=4,
            max_total_size=5,
        )

    assert ole.opened == ["BinData/BIN0001.png"]


def test_hwp_bindata_accepts_exact_aggregate_limit():
    class BinDataOle:
        def listdir(self):
            return [
                ["BinData", "BIN0001.png"],
                ["BinData", "BIN0002.jpg"],
            ]

        def get_size(self, name):
            return 3

        def openstream(self, name):
            return b"img"

    items = extract_bin_data(
        BinDataOle(),
        False,
        max_item_size=3,
        max_total_size=6,
    )

    assert items[1].data == b"img"
    assert items[2].data == b"img"


def test_hwp_bindata_decompressed_bytes_obey_aggregate_limit():
    compressor = zlib.compressobj(wbits=-15)
    compressed = compressor.compress(b"123456") + compressor.flush()

    class BinDataOle:
        def listdir(self):
            return [["BinData", "BIN0001.png"]]

        def get_size(self, name):
            return len(compressed)

        def openstream(self, name):
            return compressed

    with pytest.raises(ResourceLimitError, match="extracted BinData budget"):
        extract_bin_data(
            BinDataOle(),
            True,
            stream_budget=ByteBudget(64),
            max_item_size=64,
            max_total_size=5,
        )


def test_extensionless_ole_routes_from_workbook_stream(monkeypatch, tmp_path):
    class WorkbookOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name == "Workbook"

        def get_size(self, name):
            return 0

        def openstream(self, name):
            return b""

        def close(self):
            pass

    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", WorkbookOle)
    monkeypatch.setattr("dochan.office_binary.xls.olefile.OleFileIO", WorkbookOle)
    path = tmp_path / "extensionless"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    document = Dochan(str(path)).doc

    assert document.source_format == "xls"
    assert not any("HWP" in error for error in document.errors)


def test_extensionless_ambiguous_ole_fails_closed(monkeypatch, tmp_path):
    class AmbiguousOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name in {"WordDocument", "Workbook"}

        def close(self):
            pass

    monkeypatch.setattr("dochan.reader.olefile.OleFileIO", AmbiguousOle)
    path = tmp_path / "ambiguous"
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")

    document = Dochan(str(path)).doc

    assert document.sections == []
    assert document.source_format == ""
    assert document.errors == ["ERR: 모호한 OLE 파일 형식: doc, xls"]
