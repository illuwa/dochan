"""Raw evidence is independent of parser acceptance and reference packages."""
import struct

from scripts.audit_cfb_defects import audit_bytes, public_relative


FREE, END = 0xffffffff, 0xfffffffe


def fixture():
    raw = bytearray(512 * 11)
    raw[:8] = bytes.fromhex('d0cf11e0a1b11ae1')
    struct.pack_into('<5H', raw, 24, 62, 3, 65534, 9, 6)
    struct.pack_into('<9I', raw, 40, 0, 1, 0, 0, 4096, END, 0, END, 0)
    struct.pack_into('<109I', raw, 76, 1, *([FREE] * 108))
    for i, (name, kind, start, size, child) in enumerate([
        ('Root Entry', 5, END, 0, 1), ('Stream', 2, 2, 4096, FREE)
    ]):
        at = 512 + i * 128
        text = (name + '\0').encode('utf-16le')
        raw[at:at + len(text)] = text
        struct.pack_into('<HBBIII', raw, at + 64, len(text), kind, 1, FREE, FREE, child)
        struct.pack_into('<IQ', raw, at + 116, start, size)
    struct.pack_into('<128I', raw, 1024, END, 0xfffffffd, *range(3, 10), END, *([FREE] * 118))
    return raw


def test_valid_raw_allocation_has_no_findings():
    report = audit_bytes(fixture())
    assert report['findings'] == []
    assert report['header']['sector_count'] == 10
    assert report['reachable_entries'] == 2


def test_live_cycle_reports_repeated_sector_and_owner():
    raw = fixture()
    struct.pack_into('<I', raw, 1024 + 9 * 4, 2)
    findings = audit_bytes(raw)['findings']
    assert {'code': 'allocation_cycle', 'owner': 'entry:1', 'sector': 2,
            'mini': False, 'visited': 8} in findings


def test_stream_claiming_fat_reports_crosslink():
    raw = fixture()
    struct.pack_into('<I', raw, 512 + 128 + 116, 1)
    findings = audit_bytes(raw)['findings']
    assert any(x['code'] == 'allocation_crosslink' and x['previous_owner'] == 'FAT'
               and x['sector'] == 1 for x in findings)


def test_crosslink_after_declared_stream_extent_is_separate():
    raw = fixture()
    struct.pack_into('<I', raw, 1024 + 9 * 4, 0)
    findings = audit_bytes(raw)['findings']
    assert any(x['code'] == 'allocation_unused_tail_crosslink'
               and x['owner'] == 'entry:1' and x['previous_owner'] == 'directory'
               and x['sector'] == 0 and x['current_tail'] for x in findings)
    assert not any(x['code'] == 'allocation_crosslink' for x in findings)


def test_missing_fat_slot_never_shifts_later_table_words():
    raw = fixture()
    struct.pack_into('<I', raw, 44, 2)
    struct.pack_into('<2I', raw, 76, FREE, 1)
    findings = audit_bytes(raw)['findings']
    assert {'code': 'difat_missing_slot', 'slot': 0, 'sector': FREE} in findings
    assert {'code': 'allocation_missing_word', 'owner': 'directory', 'sector': 0,
            'mini': False} in findings


def test_header_and_directory_defects_are_numeric():
    raw = fixture()
    struct.pack_into('<H', raw, 28, 0)
    struct.pack_into('<H', raw, 512 + 128 + 64, 65)
    findings = audit_bytes(raw)['findings']
    assert {'code': 'byte_order', 'actual': 0, 'expected': 65534} in findings
    assert {'code': 'directory_name_length', 'entry': 1, 'actual': 65} in findings


def test_internal_or_external_paths_never_enter_report(tmp_path):
    import pytest
    assert public_relative(tmp_path / 'poi-src' / 'sample.doc', tmp_path) == 'corpus/poi-src/sample.doc'
    for path in (tmp_path / 'local-samples' / 'private.doc', tmp_path.parent / 'private.doc'):
        with pytest.raises(ValueError):
            public_relative(path, tmp_path)


def test_optional_reference_missing_still_writes_native_audit(tmp_path, monkeypatch):
    import json
    import sys
    from scripts.audit_cfb_defects import main
    root = tmp_path / 'poi-src'
    root.mkdir()
    (root / 'sample.doc').write_bytes(fixture())
    baseline = tmp_path / 'baseline.json'
    baseline.write_text(json.dumps({'discovered': 1, 'records': [{'id': 0, 'status': 'different'}]}))
    output = tmp_path / 'output.json'
    monkeypatch.setitem(sys.modules, 'olefile', None)
    main([str(root), '--corpus', str(tmp_path), '--baseline', str(baseline),
          '--output', str(output), '--reference'])
    record = json.loads(output.read_text())['records'][0]
    assert record['native']['accepted']
    assert record['comparison'] == {'skipped': 'optional_reference_olefile_not_installed'}


def test_residual_probe_optional_reference_missing_is_explicit(tmp_path, monkeypatch):
    import json
    import sys
    from scripts.probe_cfb_residuals import main
    output = tmp_path / 'output.json'
    monkeypatch.setitem(sys.modules, 'olefile', None)
    assert main(['--corpus', str(tmp_path), '--compare', str(tmp_path / 'unused.json'),
                 '--convert', str(tmp_path / 'unused.json'), '--output', str(output)]) == 0
    assert json.loads(output.read_text()) == {
        'conversions': [], 'containers': [], 'skipped': 'optional_reference_olefile_not_installed'}
