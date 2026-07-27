"""레거시 오피스(DOC/XLS/PPT) 견고성 회귀 테스트.

기형·손상·암호화 파일이 파서를 죽이거나 폭주시키던 문제들을 잠근다.
실제 문서 파일은 쓰지 않는다 — BIFF 레코드는 struct.pack 으로 조립하고
OLE 컨테이너는 FakeOle 로 흉내낸다.
"""

import struct
import time

from dochan.office_binary import doc as doc_module
from dochan.office_binary import xls as xls_module
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.ppt import PPTReader
from dochan.office_binary.xls import XLSReader, parse_biff_workbook

# 폭주 방지 장치가 없으면 아래 테스트들은 수십 초~수 분을 소모한다.
# 고쳐진 파서에서는 모두 1초 미만이므로 넉넉하게 잡아도 판별력이 있다.
RUNAWAY_TIME_LIMIT_SECONDS = 5.0


def _record(record_type, data=b""):
    return struct.pack("<HH", record_type, len(data)) + data


def _bof():
    return _record(0x0809, b"\x00" * 8)


def _eof():
    return _record(0x000A)


def _boundsheet(offset, name):
    return _record(0x0085, struct.pack("<IBBBB", offset, 0, 0, len(name), 0) + name.encode("latin1"))


def _label(row, col, text):
    encoded = text.encode("latin1")
    return _record(0x0204, struct.pack("<HHH", row, col, 0) + struct.pack("<H", len(encoded)) + encoded)


def _number(row, col, value):
    return _record(0x0203, struct.pack("<HHHd", row, col, 0, value))


def _styled_number(row, col, xf_index, value):
    return _record(0x0203, struct.pack("<HHHd", row, col, xf_index, value))


def _blank(row, col):
    return _record(0x0201, struct.pack("<HHH", row, col, 0))


def _row_record(row):
    return _record(0x0208, struct.pack("<HHHHHH", row, 0, 0, 0, 0, 0) + b"\x00" * 4)


def _colinfo(first_col, last_col):
    return _record(0x007D, struct.pack("<HHHHH", first_col, last_col, 0, 0, 0) + b"\x00\x00")


def _format_record(index, text):
    encoded = text.encode("latin1")
    return _record(0x041E, struct.pack("<H", index) + struct.pack("<HB", len(encoded), 0) + encoded)


def _xf(format_index):
    return _record(0x00E0, struct.pack("<HH", 0, format_index) + b"\x00" * 16)


def _merged_cells(ranges):
    body = struct.pack("<H", len(ranges))
    for first_row, last_row, first_col, last_col in ranges:
        body += struct.pack("<HHHH", first_row, last_row, first_col, last_col)
    return _record(0x00E5, body)


def _hlink(first_row, last_row, first_col, last_col, url):
    return _record(
        0x01B8,
        struct.pack("<HHHH", first_row, last_row, first_col, last_col)
        + b"\x00" * 24
        + url.encode("utf-16-le")
        + b"\x00\x00",
    )


def _filepass(key=b"\x00\x00\x00\x00\x00\x00"):
    return _record(0x002F, key)


def _dimension_biff8(first_row, last_row_exclusive, first_col, last_col_exclusive):
    """BIFF5+ DIMENSION — 행 인덱스가 UINT32 인 14바이트 형식."""
    return _record(
        0x0200,
        struct.pack("<IIHHH", first_row, last_row_exclusive, first_col, last_col_exclusive, 0),
    )


def _dimension_biff2(first_row, last_row_exclusive, first_col, last_col_exclusive):
    """BIFF2 DIMENSION — 행 인덱스가 UINT16 인 8바이트 형식."""
    return _record(
        0x0200,
        struct.pack("<HHHH", first_row, last_row_exclusive, first_col, last_col_exclusive),
    )


def _dimension_biff4(first_row, last_row_exclusive, first_col, last_col_exclusive):
    """BIFF3/4/5 DIMENSION — 예약 필드가 붙은 10바이트 형식."""
    return _record(
        0x0200,
        struct.pack("<HHHHH", first_row, last_row_exclusive, first_col, last_col_exclusive, 0),
    )


def _ppt_text_stream(text):
    """PPT TextCharsAtom(4000) 하나만 담은 최소 PowerPoint Document 스트림."""
    encoded = text.encode("utf-16-le")
    return struct.pack("<HHI", 0, 4000, len(encoded)) + encoded


def _workbook(sheet_name, sheet_body, globals_body=b""):
    globals_part = _bof() + globals_body
    worksheet = _bof() + sheet_body + _eof()
    offset = len(globals_part) + len(_boundsheet(0, sheet_name))
    return globals_part + _boundsheet(offset, sheet_name) + worksheet


def _first_table(section):
    for element in section.elements:
        if hasattr(element, "rows"):
            return element
    return None


def _cell_count(table):
    return table.row_count * table.col_count


def _timed_parse(workbook):
    started = time.monotonic()
    doc = parse_biff_workbook(workbook)
    return doc, time.monotonic() - started


def _write_fake_ole(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"\xd0\xcf\x11\xe0fake")
    return str(path)


class _StreamStub:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


def _stream_ole_factory(streams):
    """주어진 이름의 스트림만 가진 OLE 컨테이너 대역을 만든다."""

    class StreamOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name in streams

        def openstream(self, name):
            if name not in streams:
                raise KeyError(name)
            return _StreamStub(streams[name])

        def close(self):
            pass

    return StreamOle


# --- 1. max() 기본값: 셀 없이 행/열 인덱스만 있는 시트 ------------------------


def test_sheet_with_only_row_or_column_indices_does_not_raise_value_error():
    """ROW/COLINFO 만 있고 셀이 하나도 없으면 max() 가 빈 시퀀스를 받는다.

    고치기 전에는 ValueError 가 그대로 올라와 워크북 전체를 잃었다(코퍼스 24건).
    """
    rows_only = parse_biff_workbook(_workbook("RowsOnly", _row_record(3)))
    cols_only = parse_biff_workbook(_workbook("ColsOnly", _colinfo(0, 4)))

    assert rows_only.sections[0].provenance.sheet == "RowsOnly"
    assert cols_only.sections[0].provenance.sheet == "ColsOnly"
    assert _first_table(rows_only.sections[0]) is None
    assert _first_table(cols_only.sections[0]) is None


def test_xls_reader_keeps_document_when_sheet_has_only_row_indices(monkeypatch, tmp_path):
    """리더 경로에서도 같은 시트가 문서를 통째로 잃게 만들지 않아야 한다."""
    workbook = _workbook("RowsOnly", _row_record(3))
    monkeypatch.setattr(
        "dochan.office_binary.xls.olefile.OleFileIO",
        _stream_ole_factory({"Workbook": workbook}),
    )

    doc = XLSReader().read(_write_fake_ole(tmp_path, "rows-only.xls"))

    assert doc.errors == []
    assert doc.sections[0].provenance.path == "Workbook#RowsOnly"


# --- 2·3. DIMENSION 선언값 폭주와 실제 데이터 보존 ----------------------------


def test_dimension_claiming_whole_sheet_does_not_materialize_declared_grid():
    """DIMENSION 이 65536행 x 256열을 주장해도 실제 셀 범위만 만든다.

    고치기 전에는 선언값을 range() 로 풀어 1677만 셀을 실체화했다.
    """
    body = _dimension_biff8(0, 65536, 0, 256) + _label(0, 0, "A") + _number(0, 1, 1)

    doc, elapsed = _timed_parse(_workbook("Inflated", body))
    table = _first_table(doc.sections[0])

    assert table.row_count == 1
    assert table.col_count == 2
    assert _cell_count(table) <= xls_module.MAX_SHEET_CELLS
    assert [cell.text for cell in table.rows[0]] == ["A", "1"]
    assert elapsed < RUNAWAY_TIME_LIMIT_SECONDS


def test_dense_large_sheet_is_not_truncated():
    """실제 셀이 빽빽한 큰 표는 상한 때문에 잘리면 안 된다(7만 셀).

    폭주 방지 상한이 실제 데이터를 자르는 회귀를 막는 보호 테스트다.
    """
    body = b"".join(_number(row, col, row * 100 + col) for row in range(700) for col in range(100))

    doc = parse_biff_workbook(_workbook("Dense", body))
    table = _first_table(doc.sections[0])

    assert table.row_count == 700
    assert table.col_count == 100
    assert table.rows[0][0].text == "0"
    assert table.rows[699][99].text == "69999"


def test_inflated_dimension_keeps_dense_cells_and_drops_phantom_grid():
    """선언 격자는 실제 셀 범위로 되돌리되, 그 실제 셀은 한 칸도 잃지 않는다."""
    body = _dimension_biff8(0, 65536, 0, 256) + b"".join(
        _number(row, col, row * 100 + col) for row in range(700) for col in range(100)
    )

    doc, elapsed = _timed_parse(_workbook("DenseInflated", body))
    table = _first_table(doc.sections[0])

    assert table.row_count == 700
    assert table.col_count == 100
    assert table.rows[699][99].text == "69999"
    assert elapsed < RUNAWAY_TIME_LIMIT_SECONDS


def test_scattered_cells_across_whole_sheet_are_capped():
    """실제 셀이 시트 양 끝에 흩어져 있어도 절대 상한을 넘지 않는다."""
    body = _label(0, 0, "First") + _number(65535, 255, 1)

    doc = parse_biff_workbook(_workbook("Scattered", body))
    table = _first_table(doc.sections[0])

    assert _cell_count(table) <= xls_module.MAX_SHEET_CELLS
    assert table.col_count <= xls_module.MAX_SHEET_COLS
    assert table.row_count > 1  # 통째로 버리지는 않는다
    assert table.rows[0][0].text == "First"


# --- 4. MERGEDCELLS/HLINK 가 선언한 범위 채우기 ------------------------------


def test_merged_range_claiming_whole_sheet_does_not_explode_but_keeps_span():
    """MERGEDCELLS 가 0~65535행 x 0~255열을 주장해도 격자를 채우지 않는다.

    앵커 셀의 내용은 보존하되, span 은 실제로 만들어진 표 범위를 넘지 않아야 한다.
    표 밖을 가리키는 span 을 그대로 내보내면 소비자가 없는 좌표를 인덱싱하게 된다.
    """
    body = _label(0, 0, "Merged") + _merged_cells([(0, 65535, 0, 255)])

    doc, elapsed = _timed_parse(_workbook("MergedRunaway", body))
    table = _first_table(doc.sections[0])

    assert _cell_count(table) <= xls_module.MAX_SHEET_CELLS
    assert table.rows[0][0].text == "Merged"
    assert table.rows[0][0].row_span <= table.row_count
    assert table.rows[0][0].col_span <= table.col_count
    assert elapsed < RUNAWAY_TIME_LIMIT_SECONDS


def test_small_merged_range_still_fills_declared_cells():
    """예산 안의 병합 범위는 예전처럼 좌표를 그대로 채운다.

    병합만으로 존재하는 열(B~D)이 사라지면 안 된다 — 예산 도입의 과잉 교정 방지.
    """
    body = _label(0, 0, "Title") + _number(1, 0, 10) + _merged_cells([(0, 0, 0, 3)])

    doc = parse_biff_workbook(_workbook("MergedSmall", body))
    table = _first_table(doc.sections[0])

    assert table.row_count == 2
    assert table.col_count == 4
    assert table.rows[0][0].col_span == 4
    assert table.rows[0][3].is_merged_away


def test_hyperlink_range_claiming_whole_sheet_fills_only_anchor():
    """HLINK 가 시트 전체를 주장하면 앵커 한 칸에만 링크를 붙인다."""
    body = _label(0, 0, "Site") + _hlink(0, 65535, 0, 255, "https://example.com/report")

    doc, elapsed = _timed_parse(_workbook("LinkRunaway", body))
    table = _first_table(doc.sections[0])

    assert _cell_count(table) <= xls_module.MAX_SHEET_CELLS
    assert table.rows[0][0].text == "Site <https://example.com/report>"
    assert elapsed < RUNAWAY_TIME_LIMIT_SECONDS


# --- 5. BIFF2/3/4 의 짧은 DIMENSION 레코드 -----------------------------------


def test_biff2_eight_byte_dimension_is_applied():
    """8바이트 DIMENSION(BIFF2)도 사용 범위로 인정한다.

    고치기 전에는 12바이트 형식만 가정해 이 레코드를 통째로 무시했다.
    """
    body = _dimension_biff2(0, 4, 0, 3) + _label(0, 0, "X")

    doc = parse_biff_workbook(_workbook("Biff2Dim", body))
    table = _first_table(doc.sections[0])

    assert table.row_count == 4
    assert table.col_count == 3
    assert table.rows[0][0].text == "X"


def test_biff4_ten_byte_dimension_does_not_raise_struct_error():
    """10바이트 DIMENSION(BIFF3/4/5)에서 struct.error 가 나면 안 된다.

    고치기 전에는 길이 검사(>=10)를 통과한 뒤 12바이트를 요구해 예외가 났다.
    """
    body = _dimension_biff4(0, 4, 0, 3) + _label(0, 0, "X")

    doc = parse_biff_workbook(_workbook("Biff4Dim", body))
    table = _first_table(doc.sections[0])

    assert table.row_count == 4
    assert table.col_count == 3
    assert table.rows[0][0].text == "X"


# --- 6. 날짜 서식 셀의 비정상 숫자 -------------------------------------------


def test_date_formatted_nan_and_infinite_values_fall_back_to_numbers():
    """NaN/무한대/거대 일련번호는 예외 없이 숫자 문자열로 떨어져야 한다.

    고치기 전에는 int(nan) 의 ValueError, timedelta 의 OverflowError 가 났다.
    """
    globals_body = _format_record(200, "m/d/yy") + _xf(0) + _xf(200)
    body = (
        _styled_number(0, 0, 1, float("nan"))
        + _styled_number(0, 1, 1, float("inf"))
        + _styled_number(0, 2, 1, 1e18)
        + _styled_number(1, 0, 1, 45292)
    )

    doc = parse_biff_workbook(_workbook("Dates", body, globals_body=globals_body))
    table = _first_table(doc.sections[0])

    assert table.rows[0][0].text == "nan"
    assert table.rows[0][1].text == "inf"
    assert table.rows[0][2].text == "1000000000000000000"
    assert table.rows[1][0].text == "2024-01-01"  # 정상 값은 그대로 날짜로


# --- 7. FILEPASS(암호 보호 워크북) -------------------------------------------


def test_has_filepass_record_detects_only_real_filepass():
    workbook_with_filepass = _bof() + _filepass() + _label(0, 0, "A")
    clean_workbook = _workbook("Clean", _label(0, 0, "A"))

    assert xls_module.has_filepass_record(workbook_with_filepass) is True
    assert xls_module.has_filepass_record(clean_workbook) is False


def test_xls_reader_reports_filepass_protected_workbook(monkeypatch, tmp_path):
    """FILEPASS 가 있으면 파싱을 시도하지 않고 암호 보호로 보고한다.

    고치기 전에는 암호화된 레코드를 좌표로 해석해 격자를 만들려다 폭주했다.
    """
    workbook = _workbook("Protected", _label(0, 0, "A"), globals_body=_filepass())
    monkeypatch.setattr(
        "dochan.office_binary.xls.olefile.OleFileIO",
        _stream_ole_factory({"Workbook": workbook}),
    )

    doc = XLSReader().read(_write_fake_ole(tmp_path, "protected.xls"))

    assert doc.sections == []
    assert doc.errors == ["ERR: XLS Workbook 은 암호로 보호되어 있습니다 (FILEPASS)"]


# --- 8. 내용 없는 큰 격자 ----------------------------------------------------


def test_empty_large_grid_produces_no_table_but_small_empty_grid_is_kept():
    """탭만 수천 개인 표는 만들지 않되, 작은 빈 격자는 기존대로 보존한다."""
    large_body = _blank(0, 0) + _row_record(199) + _colinfo(0, 19)
    small_body = _blank(0, 0) + _blank(0, 2)

    large_doc = parse_biff_workbook(_workbook("EmptyLarge", large_body))
    small_doc = parse_biff_workbook(_workbook("EmptySmall", small_body))
    small_table = _first_table(small_doc.sections[0])

    assert _first_table(large_doc.sections[0]) is None
    assert small_table is not None
    assert [cell.text for cell in small_table.rows[0]] == ["", "", ""]


def test_large_grid_with_any_content_is_still_rendered():
    """내용이 한 칸이라도 있으면 큰 격자(2만 셀)를 버리지도 자르지도 않는다."""
    body = _label(0, 0, "Only value") + _row_record(999) + _colinfo(0, 19)

    doc = parse_biff_workbook(_workbook("SparseButUsed", body))
    table = _first_table(doc.sections[0])

    assert table.row_count == 1000
    assert table.col_count == 20
    assert table.rows[0][0].text == "Only value"
    assert table.rows[999][19].text == ""


# --- 9·10. DOC 후보 스트림 파싱 실패와 빈 본문 진단 --------------------------


def _doc_ole_factory(word_data, table_data=b"\x00" * 8, table_name="0Table"):
    return _stream_ole_factory({"WordDocument": word_data, table_name: table_data})


def test_doc_reader_survives_table_stream_parse_failure(monkeypatch, tmp_path):
    """후보 테이블 스트림의 파싱이 터져도 폴백으로 본문을 살려야 한다.

    고치기 전에는 이 예외가 read() 전체를 빠져나가 문서를 통째로 잃었다.
    """
    word_data = "Legacy Word\n본문 텍스트".encode("utf-16-le")
    monkeypatch.setattr(
        "dochan.office_binary.doc.olefile.OleFileIO",
        _doc_ole_factory(word_data),
    )
    real_parse = doc_module.parse_doc_word_stream

    def exploding_parse(data, table_data=None):
        if table_data is not None:
            raise ValueError("piece table exploded")
        return real_parse(data)

    monkeypatch.setattr(doc_module, "parse_doc_word_stream", exploding_parse)

    doc = DOCReader().read(_write_fake_ole(tmp_path, "exploding-table.doc"))

    assert [element.text for element in doc.sections[0].elements] == ["Legacy Word", "본문 텍스트"]
    assert doc.errors == ["ERR: DOC 0Table stream 파싱 실패: piece table exploded"]


def test_doc_reader_keeps_stream_read_failure_message_distinct(monkeypatch, tmp_path):
    """스트림 read 실패 메시지는 기존 계약(read 실패)을 그대로 유지한다."""
    word_data = "Legacy Word".encode("utf-16-le")
    streams = {"WordDocument": word_data, "0Table": b"\x00" * 8}

    class FailingTableOle:
        def __init__(self, path):
            self.path = path

        def exists(self, name):
            return name in streams

        def openstream(self, name):
            if name == "0Table":
                raise IOError("corrupt table stream")
            if name not in streams:
                raise KeyError(name)
            return _StreamStub(streams[name])

        def close(self):
            pass

    monkeypatch.setattr("dochan.office_binary.doc.olefile.OleFileIO", FailingTableOle)

    doc = DOCReader().read(_write_fake_ole(tmp_path, "unreadable-table.doc"))

    assert doc.errors == ["ERR: DOC 0Table stream read 실패: corrupt table stream"]
    assert [element.text for element in doc.sections[0].elements] == ["Legacy Word"]


def test_doc_reader_warns_when_no_body_text_extracted(monkeypatch, tmp_path):
    """본문을 한 줄도 못 뽑았으면 조용히 빈 문서를 돌려주지 않고 경고를 남긴다."""
    monkeypatch.setattr(
        "dochan.office_binary.doc.olefile.OleFileIO",
        _doc_ole_factory(b"\x00" * 512),
    )

    doc = DOCReader().read(_write_fake_ole(tmp_path, "silent-empty.doc"))

    assert not any(section.elements for section in doc.sections)
    assert doc.errors == [
        "WARN: DOC 본문 텍스트가 비어 있습니다"
    ]


def test_doc_reader_does_not_warn_when_body_text_exists(monkeypatch, tmp_path):
    """정상 문서에는 경고를 붙이지 않는다."""
    monkeypatch.setattr(
        "dochan.office_binary.doc.olefile.OleFileIO",
        _doc_ole_factory("Legacy Word".encode("utf-16-le")),
    )

    doc = DOCReader().read(_write_fake_ole(tmp_path, "normal.doc"))

    assert doc.errors == []
    assert doc.sections[0].elements[0].text == "Legacy Word"


# --- 11. 암호화된 OLE 컨테이너 ----------------------------------------------


def test_doc_reader_reports_encrypted_container(monkeypatch, tmp_path):
    """EncryptedPackage 가 있으면 '스트림 없음' 이 아니라 암호 보호로 보고한다."""
    monkeypatch.setattr(
        "dochan.office_binary.doc.olefile.OleFileIO",
        _stream_ole_factory({"EncryptedPackage": b"\x00" * 16, "EncryptionInfo": b"\x00" * 8}),
    )

    doc = DOCReader().read(_write_fake_ole(tmp_path, "encrypted.doc"))

    assert doc.sections == []
    assert doc.errors == ["ERR: DOC 암호로 보호된 문서입니다"]


def test_xls_reader_reports_encrypted_container(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "dochan.office_binary.xls.olefile.OleFileIO",
        _stream_ole_factory({"EncryptionInfo": b"\x00" * 8}),
    )

    doc = XLSReader().read(_write_fake_ole(tmp_path, "encrypted.xls"))

    assert doc.sections == []
    assert doc.errors == ["ERR: XLS 암호로 보호된 문서입니다"]


def test_ppt_reader_reports_encrypted_container(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "dochan.office_binary.ppt.olefile.OleFileIO",
        _stream_ole_factory({"EncryptedPackage": b"\x00" * 16}),
    )

    doc = PPTReader().read(_write_fake_ole(tmp_path, "encrypted.ppt"))

    assert doc.sections == []
    assert doc.errors == ["ERR: PPT 암호로 보호된 문서입니다"]


def test_readers_do_not_flag_plain_documents_as_encrypted(monkeypatch, tmp_path):
    """평범한 문서를 암호 보호로 오인하지 않아야 한다."""
    monkeypatch.setattr(
        "dochan.office_binary.ppt.olefile.OleFileIO",
        _stream_ole_factory({"PowerPoint Document": _ppt_text_stream("Title Slide")}),
    )

    doc = PPTReader().read(_write_fake_ole(tmp_path, "plain.ppt"))

    assert doc.errors == []
    assert doc.sections[0].elements[0].text == "Title Slide"
