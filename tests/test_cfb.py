"""Synthetic fixtures assembled from [MS-CFB] section 2, never corpus copies."""
import io
import struct

import pytest

from dochan import cfb


FREE, END, FAT, DIF = 0xffffffff, 0xfffffffe, 0xfffffffd, 0xfffffffc


def entry(name, kind, start=END, size=0, left=FREE, right=FREE, child=FREE):
    out = bytearray(128)
    encoded = (name + '\0').encode('utf-16le')
    out[:len(encoded)] = encoded
    struct.pack_into('<HBBIII', out, 64, len(encoded), kind, 1, left, right, child)
    struct.pack_into('<IQ', out, 116, start, size)
    return out


def compound(version=3, extra_fat=0):
    """Nested storage, two fragmented mini sectors, and an exact-cutoff stream.

    Layout: directory=0, FAT=1, MiniFAT=2, mini stream=3, data=4..,
    optional extra FAT sectors and DIFAT sector chain after payload.
    """
    sector = 512 if version == 3 else 4096
    payload = bytes(range(256)) * 16
    count = len(payload) // sector
    dif_count = (max(0, 1 + extra_fat - 109) + sector // 4 - 2) // (sector // 4 - 1)
    sectors = [bytearray(sector) for _ in range(4 + count + extra_fat + dif_count)]
    header = bytearray(sector)
    header[:8] = bytes.fromhex('d0cf11e0a1b11ae1')
    struct.pack_into('<5H', header, 24, 0x3e, version, 0xfffe, 9 if version == 3 else 12, 6)
    fat_ids = [1] + list(range(4 + count, 4 + count + extra_fat))
    dif_id = 4 + count + extra_fat if dif_count else END
    struct.pack_into('<9I', header, 40, 1 if version == 4 else 0,
                     len(fat_ids), 0, 0, 4096, 2, 1, dif_id, dif_count)
    struct.pack_into('<109I', header, 76, *(fat_ids[:109] + [FREE] * (109 - min(109, len(fat_ids)))))
    records = [entry('Root Entry', 5, 3, 192, child=1),
               entry('Folder', 1, right=3, child=2),
               entry('한글', 2, 2, 70), entry('Regular', 2, 4, len(payload))]
    sectors[0][:512] = b''.join(records)
    links = [END, FAT, END, END] + list(range(5, 4 + count)) + [END]
    links += [FAT] * extra_fat + [DIF] * dif_count
    links += [FREE] * (len(fat_ids) * (sector // 4) - len(links))
    for index, sid in enumerate(fat_ids):
        struct.pack_into('<%dI' % (sector // 4), sectors[sid], 0,
                         *links[index * (sector // 4):(index + 1) * (sector // 4)])
    mini = [END, FREE, 0] + [FREE] * (sector // 4 - 3)
    struct.pack_into('<%dI' % len(mini), sectors[2], 0, *mini)
    sectors[3][128:192] = b'a' * 64
    sectors[3][:6] = b'ending'
    for i in range(count):
        sectors[4 + i][:] = payload[i * sector:(i + 1) * sector]
    for i in range(dif_count):
        capacity = sector // 4 - 1
        remaining = fat_ids[109 + i * capacity:109 + (i + 1) * capacity]
        next_sid = dif_id + i + 1 if i + 1 < dif_count else END
        values = remaining + [FREE] * (capacity - len(remaining)) + [next_sid]
        struct.pack_into('<%dI' % len(values), sectors[dif_id + i], 0, *values)
    return bytes(header) + b''.join(sectors), payload


def change(raw, offset, value, fmt='<I'):
    out = bytearray(raw)
    struct.pack_into(fmt, out, offset, value)
    return bytes(out)


@pytest.mark.parametrize('version', [3, 4])
def test_regular_mini_storage_paths_and_stream_io(version, tmp_path):
    raw, payload = compound(version)
    path = tmp_path / 'synthetic.ole'
    path.write_bytes(raw)
    for source in (path, str(path), raw, io.BytesIO(raw)):
        with cfb.OleFileIO(source) as ole:
            assert ole.listdir() == [['Folder', '한글'], ['Regular']]
            assert ole.listdir(streams=False, storages=True) == [['Folder']]
            assert ole.listdir(streams=True, storages=True) == [['Folder'], ['Folder', '한글'], ['Regular']]
            assert ole.exists('folder/한글')
            assert ole.exists(['REGULAR'])
            assert not ole.exists('missing')
            assert ole.get_type('Folder') == cfb.STGTY_STORAGE
            assert ole.get_type('missing') is False
            assert ole.get_size('Folder/한글') == 70
            with ole.openstream(['Folder', '한글']) as stream:
                assert stream.read(65) == b'a' * 64 + b'e'
                assert stream.tell() == 65
                assert stream.seek(-6, 2) == 64
                assert stream.read() == b'ending'
                assert stream.read() == b''
                assert stream.seek(0) == 0
                buf = bytearray(3)
                assert stream.readinto(buf) == 3 and buf == b'aaa'
            assert ole.openstream('Regular').read() == payload
            assert ole.openstream('Regular').read(5) == payload[:5]
            with pytest.raises(OSError):
                ole.openstream('Folder')
            with pytest.raises(OSError):
                ole.get_size('missing')


@pytest.mark.parametrize('version,extra_fat', [(3, 110), (3, 240), (4, 110)])
def test_difat_beyond_header(version, extra_fat):
    raw, payload = compound(version, extra_fat=extra_fat)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload


def test_v3_ignores_high_size_bits():
    raw, payload = compound()
    raw = change(raw, 512 + 3 * 128 + 124, 0x12345678)
    with cfb.OleFileIO(raw) as ole:
        assert ole.get_size('Regular') == 4096
        assert ole.openstream('Regular').read() == payload


def test_v4_keeps_high_size_bits_and_limits():
    raw, _ = compound(4)
    raw = change(raw, 4096 + 3 * 128 + 124, 1)
    with pytest.raises(cfb.CFBError, match='size|limit'):
        with cfb.OleFileIO(raw) as ole:
            ole.openstream('Regular')


@pytest.mark.parametrize('offset,value,fmt', [
    (0, 0, '<Q'), (26, 2, '<H'), (28, 0xfeff, '<H'),
    (30, 12, '<H'), (32, 5, '<H'), (56, 2048, '<I'),
    (44, 0xffffffff, '<I'), (48, 9999, '<I'),
    (76, 9999, '<I'), (512 + 66, 4, '<B'),
    (512 + 64, 65, '<H'), (512 + 76, 9999, '<I'),
    (512 + 128 + 68, 1, '<I'),
    (512 + 128 + 72, 2, '<I'),
])
def test_invalid_headers_and_directory_graph(offset, value, fmt):
    raw, _ = compound()
    with pytest.raises(cfb.CFBError):
        with cfb.OleFileIO(change(raw, offset, value, fmt), raise_defects=cfb.DEFECT_INCORRECT) as ole:
            for name in ole.listdir():
                ole.openstream(name).read()


@pytest.mark.parametrize('offset,value,name', [
    (1024, 0, 'Regular'),                 # directory FAT cycle
    (1024 + 4 * 4, 4, 'Regular'),         # stream FAT cycle
    (1024 + 4 * 4, 9999, 'Regular'),      # stream FAT out of range
    (1024 + 4 * 4, END, 'Regular'),       # early terminator
    (1024 + 11 * 4, 4, 'Regular'),        # cycle after declared end
    (1536 + 2 * 4, 2, 'Folder/한글'),     # mini FAT cycle
    (1536 + 2 * 4, 8, 'Folder/한글'),     # outside root mini stream
    (512 + 3 * 128 + 116, 1, 'Regular'), # stream aliases FAT
])
def test_invalid_allocation_chains(offset, value, name):
    raw, _ = compound()
    with pytest.raises(cfb.CFBError):
        with cfb.OleFileIO(change(raw, offset, value), raise_defects=cfb.DEFECT_INCORRECT) as ole:
            ole.openstream(name).read()


def test_difat_cycle_and_duplicate_fat():
    raw, _ = compound(extra_fat=110)
    for broken in (change(raw, len(raw) - 4, len(raw) // 512 - 2),
                   change(raw, 80, 1)):
        with pytest.raises(cfb.CFBError):
            cfb.OleFileIO(broken)


def test_empty_stream_and_signature_probe():
    raw, _ = compound()
    raw = change(change(raw, 512 + 3 * 128 + 116, END), 512 + 3 * 128 + 120, 0, '<Q')
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == b''
    source = io.BytesIO(raw)
    source.seek(7)
    assert cfb.isOleFile(source)
    assert source.tell() == 7
    assert cfb.isOleFile(data=raw)
    assert not cfb.isOleFile(data=b'not cfb')
    with cfb.OleFileIO(source):
        pass
    assert not source.closed


def test_payload_is_lazy_and_streams_have_independent_positions():
    raw, payload = compound()

    class Tracking(io.BytesIO):
        payload_bytes = 0

        def read(self, size=-1):
            if self.tell() >= 512 * 5:
                self.payload_bytes += max(0, size)
            return super().read(size)

    source = Tracking(raw)
    with cfb.OleFileIO(source) as ole:
        a = ole.openstream('Regular')
        b = ole.openstream('Regular')
        assert source.payload_bytes == 0
        assert a.read(3) == payload[:3]
        assert b.read(2) == payload[:2]
        assert a.read(2) == payload[3:5]
        assert source.payload_bytes == 7


def test_truncated_sector_is_clear_error():
    raw, _ = compound()
    with pytest.raises(cfb.CFBError):
        with cfb.OleFileIO(raw[:-20], raise_defects=cfb.DEFECT_INCORRECT) as ole:
            ole.openstream('Regular').read()


def test_path_index_has_cumulative_budget(monkeypatch):
    raw, _ = compound()
    monkeypatch.setattr(cfb, 'MAX_PATH_COMPONENTS', 3, raising=False)
    with pytest.raises(cfb.CFBError, match='path.*limit'):
        cfb.OleFileIO(raw)


def test_allocation_limits_before_payload_read(monkeypatch):
    raw, _ = compound()
    monkeypatch.setattr(cfb, 'MAX_FILE_SIZE', len(raw) - 1)
    with pytest.raises(cfb.CFBError, match='file size limit'):
        cfb.OleFileIO(io.BytesIO(raw))


@pytest.mark.parametrize('mini', [False, True])
def test_crosslinked_streams_rejected_and_reopen_is_independent(mini):
    raw, payload = compound()
    offset = 512 + (3 if mini else 2) * 128
    raw = change(change(raw, offset + 116, 2 if mini else 4), offset + 120, 70 if mini else 4096, '<Q')
    with cfb.OleFileIO(raw) as ole:
        first = 'Folder/한글' if mini else 'Regular'
        second = 'Regular' if mini else 'Folder/한글'
        assert ole.openstream(first).read()
        assert ole.openstream(first).read()
        with pytest.raises(cfb.CFBError, match='duplicate'):
            ole.openstream(second)


def test_nonessential_root_label_is_not_a_lookup_name():
    raw, payload = compound()
    # Public POI numbers.ppt has a root name length of 2 but an 'R' code unit.
    raw = change(raw, 512 + 64, 2, '<H')
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)


def test_fat_marker_deviation_still_reserves_metadata_sectors():
    raw, payload = compound()
    # Some public Office samples mark actual FAT sectors as FREESECT.
    raw = change(raw, 1024 + 4, FREE)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)
    raw = change(raw, 512 + 3 * 128 + 116, 1)
    with pytest.raises(cfb.CFBError, match='duplicate'):
        with cfb.OleFileIO(raw) as ole:
            ole.openstream('Regular')


def test_short_input_retains_ole_error_context():
    with pytest.raises(cfb.CFBError, match='OLE'):
        cfb.OleFileIO(cfb.MAGIC + b'\0' * 64)


def test_free_difat_terminator_is_bounded_by_declared_count():
    raw, payload = compound(extra_fat=110)
    raw = change(raw, len(raw) - 4, FREE)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)


def test_root_overallocated_chain_is_fully_checked_but_payload_is_sized():
    raw, _ = compound()
    raw += b'\0' * 512
    raw = change(change(raw, 1024 + 3 * 4, 12), 1024 + 12 * 4, END)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(change(raw, 1024 + 12 * 4, 3))
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)


def test_partial_last_sector_with_complete_declared_payload():
    raw, payload = compound()
    raw += b'x'
    raw = change(change(raw, 1024 + 11 * 4, 12), 1024 + 12 * 4, END)
    raw = change(raw, 512 + 3 * 128 + 120, 4097, '<Q')
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload + b'x'
    # Strict mode rejects missing payload; default mode exposes only its prefix.
    with pytest.raises(cfb.CFBError):
        with cfb.OleFileIO(raw[:-1], raise_defects=cfb.DEFECT_INCORRECT) as ole:
            ole.openstream('Regular').read()


def test_unused_absent_minifat_count_does_not_hide_regular_stream():
    raw, payload = compound()
    raw = change(raw, 60, END)
    raw = change(raw, 512 + 120, 0, '<Q')
    raw = change(raw, 512 + 2 * 128 + 120, 0, '<Q')
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)
    # An actually needed mini FAT may not be ignored.
    with pytest.raises(cfb.CFBError):
        with cfb.OleFileIO(change(raw, 512 + 2 * 128 + 120, 70, '<Q'),
                           raise_defects=cfb.DEFECT_INCORRECT) as ole:
            ole.openstream('Folder/한글')


@pytest.mark.parametrize('slot,value', [(1, 9999), (1, 1), (108, 0)])
def test_unused_difat_slots_do_not_address_sectors(slot, value):
    raw, payload = compound()
    raw = change(raw, 76 + slot * 4, value)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)


def test_unused_extended_difat_slots_do_not_address_sectors():
    raw, payload = compound(extra_fat=110)
    raw = change(raw, len(raw) - 12, 999999)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues


def test_directory_color_and_stream_child_are_not_addresses():
    raw, payload = compound()
    raw = change(raw, 512 + 3 * 128 + 67, 255, '<B')
    raw = change(raw, 512 + 3 * 128 + 76, 99999)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert len(ole.parsing_issues) == 2


def test_orphan_directory_slots_are_not_live_objects():
    raw, payload = compound(4)
    raw = change(raw, 4096 + 4 * 128 + 66, 255, '<B')
    with cfb.OleFileIO(raw) as ole:
        assert ole.listdir() == [['Folder', '한글'], ['Regular']]
        assert ole.openstream('Regular').read() == payload


def test_regular_excess_chain_keeps_declared_extent_and_checks_cycles():
    raw, payload = compound()
    raw += b'x' * 512
    raw = change(change(raw, 1024 + 11 * 4, 12), 1024 + 12 * 4, END)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        with cfb.OleFileIO(change(raw, 1024 + 12 * 4, 4)) as ole:
            ole.openstream('Regular')


def test_partial_minifat_sector_requires_only_referenced_words():
    raw, _ = compound()
    # Relocate MiniFAT after the complete data and keep three actual words.
    raw += raw[1536:1548]
    raw = change(change(raw, 60, 12), 1024 + 12 * 4, END)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'
        assert ole.parsing_issues


@pytest.mark.parametrize('damage', ['physical', 'early_end', 'outside_tail', 'oversized_count'])
def test_truncated_stream_returns_only_addressable_prefix(damage):
    raw, payload = compound()
    expected = payload
    if damage == 'physical':
        raw, expected = raw[:-20], payload[:-20]
    elif damage == 'early_end':
        raw, expected = change(raw, 1024 + 4 * 4, END), payload[:512]
    elif damage == 'outside_tail':
        raw, expected = change(raw, 1024 + 4 * 4, 9999), payload[:512]
    else:
        raw = change(raw, 512 + 3 * 128 + 120, 100000)
    with cfb.OleFileIO(raw) as ole:
        assert ole.get_size('Regular') == (100000 if damage == 'oversized_count' else 4096)
        stream = ole.openstream('Regular')
        assert stream.read() == expected
        assert stream.seek(0, 2) == len(expected)
        assert ole.parsing_issues
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'
    with pytest.raises(cfb.CFBError):
        with cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT) as ole:
            ole.openstream('Regular').read()


def test_failed_chain_releases_claims_for_other_streams():
    raw, _ = compound()
    # First attempt walks a real sector then cycles. Repeated errors must be
    # stable and unrelated streams must remain readable.
    raw = change(raw, 1024 + 4 * 4, 4)
    with cfb.OleFileIO(raw) as ole:
        for _ in range(2):
            with pytest.raises(cfb.CFBError, match='cyclic'):
                ole.openstream('Regular')
            assert ole._owners[4] == -1
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'


def test_crosslinked_tail_after_declared_extent_is_not_payload():
    raw, payload = compound()
    raw = change(raw, 1024 + 11 * 4, 0)  # Directory, beyond stream extent.
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues


@pytest.mark.parametrize('damage', ['missing', 'unused', 'name'])
def test_local_directory_damage_preserves_other_branches(damage):
    raw, payload = compound()
    if damage == 'missing':
        raw = change(raw, 512 + 128 + 76, 9999)
    elif damage == 'unused':
        raw = change(raw, 512 + 2 * 128 + 66, 0, '<B')
    else:
        raw = change(raw, 512 + 2 * 128 + 64, 0, '<H')
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert not ole.exists('Folder/한글')
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)


def test_huge_unused_minifat_count_does_not_allocate():
    raw, payload = compound()
    raw = change(change(raw, 60, END), 64, 0x30303030)
    raw = change(raw, 512 + 120, 0, '<Q')
    raw = change(raw, 512 + 2 * 128 + 120, 0, '<Q')
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues


def test_missing_unused_fat_suffix_keeps_available_allocation_words():
    raw, payload = compound()
    raw = change(raw, 44, 5)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)


def test_partial_directory_chain_preserves_complete_entries():
    raw, payload = compound()
    raw = change(raw, 1024, 9999)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues


def test_minifat_chain_count_is_bounded_by_physical_chain():
    raw, payload = compound()
    raw = change(raw, 64, 10)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'
        assert ole.parsing_issues


def test_unused_tail_does_not_claim_another_stream_payload():
    raw, payload = compound()
    raw += payload
    for sid in range(12, 20):
        raw = change(raw, 1024 + sid * 4, sid + 1 if sid < 19 else END)
    raw = change(raw, 1024 + 11 * 4, 12)
    raw = change(change(raw, 512 + 2 * 128 + 116, 12), 512 + 2 * 128 + 120, 4096)
    for first, second in [('Regular', 'Folder/한글'), ('Folder/한글', 'Regular')]:
        with cfb.OleFileIO(raw) as ole:
            assert ole.openstream(first).read() == payload
            assert ole.openstream(second).read() == payload


def test_chain_traversal_has_cumulative_work_budget(monkeypatch):
    raw, _ = compound()
    monkeypatch.setattr(cfb, 'MAX_CHAIN_STEPS', 5, raising=False)
    with pytest.raises(cfb.CFBError, match='work limit'):
        with cfb.OleFileIO(raw) as ole:
            ole.openstream('Regular')


@pytest.mark.parametrize('offset', [60, 512 + 116])
def test_missing_mini_allocator_does_not_hide_regular_stream(offset):
    raw, payload = compound()
    raw = change(raw, offset, 9999)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
        assert ole.openstream('Folder/한글').read() == b''


def test_invalid_root_label_does_not_change_root_addresses():
    raw, payload = compound()
    raw = change(raw, 512 + 64, 0, '<H')
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.parsing_issues
    with pytest.raises(cfb.CFBError):
        cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT)



def test_missing_first_sector_is_empty_prefix_and_keeps_size_contract():
    from dochan.utils.bounded_io import read_ole_stream, StreamSizeError
    raw, _ = compound()
    raw = change(raw, 512 + 3 * 128 + 116, 9999)
    with cfb.OleFileIO(raw) as ole:
        assert ole.get_size('Regular') == 4096
        assert ole.openstream('Regular').read() == b''
        assert ole.parsing_issues
        with pytest.raises(StreamSizeError, match='declared=4096, read=0'):
            read_ole_stream(ole, 'Regular')
    with pytest.raises(cfb.CFBError):
        with cfb.OleFileIO(raw, raise_defects=cfb.DEFECT_INCORRECT) as ole:
            ole.openstream('Regular')



@pytest.mark.parametrize('method', ['get_size', 'openstream'])
def test_nonstream_api_error_preserves_existing_diagnostic(method):
    raw, _ = compound()
    with cfb.OleFileIO(raw) as ole:
        with pytest.raises(OSError, match='^this file is not a stream$'):
            getattr(ole, method)('Folder')
