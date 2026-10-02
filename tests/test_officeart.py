"""OfficeArt 계약은 코퍼스 없이 조립한 레코드로 검증한다."""
import io
import struct
import zlib

import pytest

from dochan.office_binary.officeart import (
    Limits, decode_blip, parse_header, parse_records, read_bstore,
    read_shapes, walk_records,
)


def record(kind, payload=b"", version=0, instance=0):
    return struct.pack("<HHI", instance << 4 | version, kind, len(payload)) + payload


def blip(kind=0xF01E, instance=0x6E0, data=b"pixels", uids=1):
    return record(kind, b"u" * (16 * uids) + b"\xff" + data, instance=instance)


def bse(image=b"", delay=0xFFFFFFFF, name=b"", size=None):
    head = struct.pack("<BB16sHIIIBBBB", 6, 6, b"u" * 16, 255,
                       len(image) if size is None else size, 2, delay, 0, len(name), 0, 0)
    return record(0xF007, head + name + image, version=2, instance=6)


def test_header_tree_offsets_and_truncated_record_stop():
    atom = record(0xF00A, struct.pack("<II", 42, 5), version=2, instance=23)
    data = record(0xF002, record(0xF004, atom, version=15), version=15)
    h = parse_header(atom)
    assert (h.rec_ver, h.rec_instance, h.rec_type, h.rec_len) == (2, 23, 0xF00A, 8)
    assert parse_header(b"short") is None
    errors = []
    roots = parse_records(data + atom[:-1], errors=errors)
    assert [r.offset for r in walk_records(roots)] == [0, 8, 16]
    assert bytes(roots[0].children[0].children[0].data) == struct.pack("<II", 42, 5)
    assert any("truncated" in e for e in errors)


def test_global_depth_record_and_length_limits():
    atom = record(0xF00A)
    data = atom
    for _ in range(6):
        data = record(0xF002, data, version=15)
    for payload, limits, count in [
        (data, Limits(max_depth=2), 3),
        (atom * 10, Limits(max_records=3), 3),
        (record(1, b"0123456789"), Limits(max_record_bytes=9), 0),
        (atom * 10, Limits(max_stream_bytes=40), 0),
    ]:
        errors = []
        assert len(list(walk_records(parse_records(payload, limits=limits, errors=errors)))) == count
        assert errors


@pytest.mark.parametrize("kind,base,fmt,metafile", [
    (0xF01A, 0x3D4, "emf", True), (0xF01B, 0x216, "wmf", True),
    (0xF01C, 0x542, "pict", True), (0xF01D, 0x46A, "jpg", False),
    (0xF01D, 0x6E2, "jpg", False), (0xF01E, 0x6E0, "png", False),
    (0xF029, 0x6E4, "tiff", False), (0xF02A, 0x6E2, "jpg", False),
])
@pytest.mark.parametrize("uids", [1, 2])
def test_blip_instances_uid_tag_and_metafile_deflate(kind, base, fmt, metafile, uids):
    pixels = b"sample metafile or raster bytes" * 10
    prefix = b"u" * (16 * uids)
    if metafile:
        compressed = zlib.compress(pixels)
        header = struct.pack("<I4i2iIBB", len(pixels), 0, 0, 1, 1, 1, 1, len(compressed), 0, 254)
        payload = prefix + header + compressed
    else:
        payload = prefix + b"\xff" + pixels
    r = parse_records(record(kind, payload, instance=base + uids - 1))[0]
    assert decode_blip(r) == (fmt, pixels)


def test_metafile_uncompressed_bad_lengths_and_inflate_limit():
    pixels = b"x" * 10000
    compressed = zlib.compress(pixels)
    def make(size, saved, compression, data):
        header = struct.pack("<I4i2iIBB", size, 0, 0, 1, 1, 1, 1, saved, compression, 254)
        return parse_records(record(0xF01A, b"u" * 16 + header + data, instance=0x3D4))[0]
    assert decode_blip(make(3, 3, 254, b"abc")) == ("emf", b"abc")
    for r in [make(1, len(compressed), 0, compressed),
              make(10000, len(compressed), 0, compressed),
              make(3, 4, 254, b"abc"), make(3, 3, 99, b"abc"),
              make(3, 3, 0, b"bad")]:
        errors = []
        assert decode_blip(r, limits=Limits(max_image_bytes=100), errors=errors) is None
        assert errors
    assert decode_blip(parse_records(blip(instance=123))[0]) is None


def test_dib_to_bmp_is_readable_including_palette_and_bitfields():
    dib = struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 24, 0, 4, 0, 0, 0, 0) + b"\x00\x00\xff\x00"
    r = parse_records(blip(0xF01F, 0x7A8, dib))[0]
    fmt, bmp = decode_blip(r)
    assert fmt == "bmp" and bmp[:2] == b"BM"
    assert struct.unpack_from("<I", bmp, 10)[0] == 54
    # 24비트 BMP 픽셀은 BGR 순서로 오프셋 54 에서 시작한다 — 빨강 1픽셀(Pillow 없이 확인)
    assert bmp[54:57] == b"\x00\x00\xff"
    palette = struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 8, 0, 4, 0, 0, 2, 0) + b"\x00" * 12
    assert struct.unpack_from("<I", decode_blip(parse_records(blip(0xF01F, 0x7A8, palette))[0])[1], 10)[0] == 62
    fields = struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 16, 3, 4, 0, 0, 0, 0) + b"\x00" * 16
    assert struct.unpack_from("<I", decode_blip(parse_records(blip(0xF01F, 0x7A8, fields))[0])[1], 10)[0] == 66
    assert decode_blip(parse_records(blip(0xF01F, 0x7A8, b"bad"))[0]) is None


def test_bstore_embedded_delayed_names_and_index_preservation():
    image = blip(data=b"embedded")
    delayed = blip(data=b"delayed", instance=0x6E1, uids=2)
    data = record(0xF001, bse(image, name=b"n\x00") + bse(delay=4, size=len(delayed))
                  + bse(delay=999, size=100), version=15, instance=3)
    errors = []
    entries = read_bstore(parse_records(data), delayed_stream=b"pad!" + delayed, errors=errors)
    assert [e.index for e in entries] == [1, 2, 3]
    assert (entries[0].bt_win32, entries[0].bt_macos, entries[0].uid, entries[0].size,
            entries[0].c_ref, entries[0].fo_delay, entries[0].cb_name) == (6, 6, b"u" * 16, len(image), 2, 0xFFFFFFFF, 2)
    assert entries[0].name == b"n\x00"
    assert [e.image for e in entries] == [("png", b"embedded"), ("png", b"delayed"), None]
    assert errors
    # foDelay=0 is a valid record position, not an absent pointer.
    assert read_bstore(parse_records(record(0xF001, bse(delay=0, size=len(image)), version=15)),
                       delayed_stream=image)[0].image == ("png", b"embedded")


def test_bstore_truncated_entry_and_total_image_budget():
    image = blip(data=b"12345678")
    roots = parse_records(record(0xF001, record(0xF007, b"bad") + bse(image) + bse(image), version=15))
    errors = []
    entries = read_bstore(roots, limits=Limits(max_total_image_bytes=8), errors=errors)
    assert len(entries) == 3 and [e.image for e in entries] == [None, ("png", b"12345678"), None]
    assert len(errors) >= 2


def test_shape_tree_properties_flags_and_client_raw_bytes():
    name = "그림 1\x00".encode("utf-16le")
    alt = "설명\x00".encode("utf-16le")
    props = (struct.pack("<HI", 0x4104, 2) + struct.pack("<HI", 0x8380, len(name))
             + struct.pack("<HI", 0x8381, len(alt)) + struct.pack("<HI", 0x0080, 77)
             + struct.pack("<HI", 0x0382, 123) + name + alt)
    child = record(0xF004,
                   record(0xF00A, struct.pack("<II", 99, 2), version=2, instance=75)
                   + record(0xF00B, props, version=3, instance=5)
                   + record(0xF122, struct.pack("<HI", 0x0104, 3), version=3, instance=1)
                   + record(0xF121, struct.pack("<HI", 0x0181, 555), version=3, instance=1)
                   + record(0xF00F, struct.pack("<4i", -1, 2, 30, 40))
                   + record(0xF010, b"anchor") + record(0xF011, b"data")
                   + record(0xF00D, b"textbox"), version=15)
    group = record(0xF004, record(0xF00A, struct.pack("<II", 10, 5), version=2), version=15)
    root = record(0xF002, record(0xF003, group + child, version=15), version=15)
    shapes = read_shapes(parse_records(root))
    assert len(shapes) == 1 and shapes[0].spid == 10
    assert shapes[0].is_group and shapes[0].is_patriarch
    s = shapes[0].children[0]
    assert s.is_child and s.shape_type == 75
    assert (s.pib, s.name, s.description, s.textbox_id) == (3, "그림 1", "설명", 77)
    assert s.properties[0x0104].is_blip_id is False
    assert s.properties[0x0382].value == 123
    assert s.properties[0x0181].value == 555
    assert s.child_anchor == (-1, 2, 30, 40)
    assert (s.client_anchor, s.client_data, s.client_textbox) == (b"anchor", b"data", b"textbox")


def test_truncated_properties_do_not_shift_following_complex_values():
    props = struct.pack("<HIHI", 0x8380, 999, 0x8381, 4) + b"x\x00\x00\x00"
    shape = record(0xF004, record(0xF00A, struct.pack("<II", 1, 0))
                   + record(0xF00B, props, instance=2), version=15)
    errors = []
    s = read_shapes(parse_records(shape), errors=errors)[0]
    assert s.name == s.description == ""
    assert errors


def test_probe_adapters_join_biff_continuations_and_skip_nested_doc_records():
    from scripts.probe_officeart import _biff_drawing, _scan_doc
    image = blip(data=b"real pixels")
    store = record(0xF001, bse(image), version=15)
    def biff(kind, data):
        return struct.pack("<HH", kind, len(data)) + data
    stream = (biff(0x00EB, store[:19]) + biff(0x003C, store[19:])
              + biff(0x005D, b"object") + biff(0x003C, b"unrelated text"))
    assert _biff_drawing(stream, 0x00EB) == store
    roots = _scan_doc(b"host structures!" + store, [])
    assert len(roots) == 1 and roots[0].header.rec_type == 0xF001
    assert read_bstore(roots)[0].image == ("png", b"real pixels")


def test_offset_range_unknown_atoms_and_damage_inside_container_are_local():
    atom = record(0xFFFF, b"raw")
    broken_container = record(0xF002, atom + b"short", version=15)
    data = b"prefix" + broken_container + atom
    errors = []
    roots = parse_records(data, offset=6, errors=errors)
    assert len(roots) == 2 and len(roots[0].children) == 1
    assert bytes(roots[1].data) == b"raw"
    assert roots[0].offset == 6 and errors
    assert parse_records(data, offset=-1, errors=errors) == []
    assert parse_records(data, length=len(data) + 1, errors=errors) == []


def test_probe_missing_samples_report_per_file_failures(tmp_path, capsys):
    import json
    from scripts.probe_officeart import main
    output = tmp_path / "results.json"
    assert main([str(tmp_path), "--output", str(output)]) == 0
    rows = json.loads(output.read_text())
    assert len(rows) == 9 and all("error" in row for row in rows.values())
