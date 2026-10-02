"""Review regressions from synthetic MS-CFB headers and allocation tables."""
import pytest

from dochan import cfb
from test_cfb import END, FREE, change, compound, entry


def test_minifat_excess_tail_never_owns_regular_payload():
    raw, payload = compound()
    raw = change(raw, 1024 + 2 * 4, 4)
    with cfb.OleFileIO(raw) as ole:
        assert len(ole._minifat) == 128
        assert ole.openstream('Regular').read() == payload


def test_minifat_excess_tail_never_supplies_allocation_words():
    raw, _ = compound()
    raw += b'Z' * (17 * 512)
    for sid in range(12, 29):
        raw = change(raw, 1024 + sid * 4, sid + 1 if sid < 28 else END)
    raw = change(change(raw, 512 + 116, 12), 512 + 120, 17 * 512)
    raw = change(change(raw, 512 + 256 + 116, 128), 512 + 256 + 120, 1)
    raw = change(change(raw, 1024 + 2 * 4, 4), 5 * 512, END)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Folder/한글').read() == b''


def test_byte_order_constant_is_metadata_not_addressing():
    raw, payload = compound()
    raw = change(raw, 28, 0xff20, '<H')
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues == ['CFB invalid byte order marker']
        errors = []
        cfb.append_recovery_warnings(ole, errors)
        assert errors == []
    with pytest.raises(cfb.CFBError, match='byte order'):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)


def test_recovery_strict_mode_accepts_metadata_but_rejects_data_loss():
    raw, payload = compound()
    with cfb.OleFileIO(change(raw, 1024 + 4, FREE), strict_recovery=True) as ole:
        assert ole.openstream('Regular').read() == payload
    with pytest.raises(cfb.CFBError, match='directory entry omitted'):
        cfb.OleFileIO(change(raw, 512 + 256 + 64, 0, '<H'), strict_recovery=True)
    with cfb.OleFileIO(raw[:-20], strict_recovery=True) as ole:
        with pytest.raises(cfb.CFBError, match='truncated'):
            ole.openstream('Regular')


def test_duplicate_case_insensitive_name_omits_only_later_entry():
    raw, _ = compound()
    raw = raw[:896] + entry('fOlDeR', 2, 4, 4096) + raw[1024:]
    with cfb.OleFileIO(raw) as ole:
        assert ole.listdir() == [['Folder', '한글']]
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'
        errors = []
        cfb.append_recovery_warnings(ole, errors)
        assert len(errors) == 1 and 'duplicate directory name omitted' in errors[0]


def test_oversized_unused_root_does_not_hide_regular_stream():
    raw, payload = compound()
    raw = change(raw, 512 + 120, cfb.MAX_STREAM_SIZE + 1)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        with pytest.raises(cfb.CFBError, match='size limit'):
            ole.openstream('Folder/한글')


def test_fat_words_are_bounded_by_physical_sector_count():
    raw, payload = compound(extra_fat=240)
    with cfb.OleFileIO(raw) as ole:
        assert len(ole._fat) <= ole._sector_count
        assert ole.openstream('Regular').read() == payload


def test_warning_categories_are_deduplicated_bounded_and_ignore_metadata():
    raw, _ = compound()
    raw = change(raw, 512 + 256 + 64, 0, '<H')
    with cfb.OleFileIO(raw) as ole:
        ole._metadata_defect('CFB incorrect FAT/DIFAT sector marker')
        errors = ['existing']
        for _ in range(100):
            cfb.append_recovery_warnings(ole, errors, path='one')
            cfb.append_recovery_warnings(ole, errors, path='two')
        assert errors == [
            'existing',
            'WARN: OLE/CFB 컨테이너 손상 복구: invalid directory entry omitted (one)',
            'WARN: OLE/CFB 컨테이너 손상 복구: invalid directory entry omitted (two)',
        ]


def test_failed_optional_stream_retains_warning_with_stream_path():
    raw, _ = compound()
    raw = change(raw, 1536 + 2 * 4, 2)
    with cfb.OleFileIO(raw) as ole:
        with pytest.raises(cfb.CFBError, match='cyclic'):
            ole.openstream('Folder/한글')
        errors = []
        cfb.append_recovery_warnings(ole, errors)
        assert errors == [
            'WARN: OLE/CFB 컨테이너 손상 복구: stream read failed (Folder/한글)',
        ]


def test_absent_optional_stream_is_not_container_damage():
    raw, _ = compound()
    with cfb.OleFileIO(raw) as ole:
        with pytest.raises(cfb.CFBError, match='file not found'):
            ole.openstream('OptionalMissingStream')
        errors = []
        cfb.append_recovery_warnings(ole, errors)
        assert errors == []
