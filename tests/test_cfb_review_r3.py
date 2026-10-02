"""Declared extents and actionable, bounded recovery diagnostics."""
import struct
import zlib
from types import SimpleNamespace

import pytest

from dochan import cfb
from dochan.office_binary.ole_objects import PptObjects
from test_cfb import END, FREE, change, compound
from test_ole_objects import chart, compound as chart_container


@pytest.mark.parametrize('tail', [FREE, 9999, 4, 11, 1])
def test_regular_unused_tail_is_metadata_without_work_or_loss(tail):
    raw, payload = compound()
    raw = change(raw, 1024 + 11 * 4, tail)
    with cfb.OleFileIO(raw, strict_recovery=True) as ole:
        before = ole._chain_steps
        assert ole.openstream('Regular').read() == payload
        assert ole._chain_steps - before == 8
        assert ole.recovery_issues == []


@pytest.mark.parametrize('tail', [FREE, 9999, 0, 2])
def test_mini_unused_tail_keeps_declared_bytes(tail):
    raw, _ = compound()
    raw = change(raw, 1536, tail)
    with cfb.OleFileIO(raw, strict_recovery=True) as ole:
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'
        assert ole.recovery_issues == []


@pytest.mark.parametrize('tail', [FREE, 9999, 2, 4])
def test_minifat_unused_tail_never_rejects_container(tail):
    raw, payload = compound()
    raw = change(raw, 1024 + 2 * 4, tail)
    with cfb.OleFileIO(raw, strict_recovery=True) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'
        assert len(ole._minifat) == 128
        assert ole.recovery_issues == []


def test_unused_tail_cannot_exhaust_later_stream_work_budget(monkeypatch):
    raw, payload = compound()
    raw += b'x' * (100 * 512)
    raw = change(raw, 1024 + 11 * 4, 12)
    for sid in range(12, 112):
        raw = change(raw, 1024 + sid * 4, sid + 1 if sid < 111 else END)
    # directory + MiniFAT + 8 payload sectors + root + 2 mini sectors.
    monkeypatch.setattr(cfb, 'MAX_CHAIN_STEPS', 13)
    with cfb.OleFileIO(raw) as ole:
        assert ole.openstream('Regular').read() == payload
        assert ole.openstream('Folder/한글').read() == b'a' * 64 + b'ending'
        assert ole._chain_steps == 13


@pytest.mark.parametrize('incomplete', [False, True])
@pytest.mark.parametrize('tail', [FREE, 9999, 2])
def test_ppt_embedded_chart_survives_unused_tail(tail, incomplete):
    raw = change(chart_container('Workbook', chart()), 1024 + 9 * 4, tail)
    packed = zlib.compress(raw)
    record = SimpleNamespace(header=SimpleNamespace(rec_instance=1),
                             data=struct.pack('<I', len(raw)) + (packed[:-4] if incomplete else packed))
    errors = []
    out = PptObjects({7: record}, errors).at(7, None)
    assert [getattr(item, 'text', type(item).__name__) for item in out] == ['Annual', 'Table']
    assert not any('컨테이너 손상' in message for message in errors)


def test_outer_and_embedded_loss_keep_their_own_paths():
    raw = chart_container('Workbook', chart())[:-20]
    record = SimpleNamespace(header=SimpleNamespace(rec_instance=0), data=raw)
    errors = []
    assert PptObjects({7: record}, errors).at(7, None) == []
    outer, _ = compound()
    with cfb.OleFileIO(outer[:-20]) as ole:
        ole.openstream('Regular').read()
        cfb.append_recovery_warnings(ole, errors)
    assert any('embedded OLE/CFB' in msg and 'ole7/Workbook' in msg for msg in errors)
    assert any(msg.startswith('WARN: OLE/CFB ') and '(Regular)' in msg for msg in errors)


def test_truncation_derivatives_fold_to_one_warning_per_stream():
    raw, _ = compound()
    raw = change(raw, 512 + 384 + 120, 100000)
    raw = change(raw, 1024 + 4 * 4, 9999)
    with cfb.OleFileIO(raw) as ole:
        assert len(ole.openstream('Regular').read()) == 512
        errors = []
        cfb.append_recovery_warnings(ole, errors)
        assert len(errors) == 1
        assert '(Regular)' in errors[0]


@pytest.mark.parametrize('limit', ['size', 'chain'])
def test_resource_limit_warning_is_not_damage(monkeypatch, limit):
    raw, _ = compound()
    with cfb.OleFileIO(raw) as ole:
        monkeypatch.setattr(cfb, 'MAX_STREAM_SIZE' if limit == 'size' else 'MAX_CHAIN_STEPS', 1)
        with pytest.raises(cfb.CFBError, match='limit exceeded'):
            ole.openstream('Regular')
        errors = []
        cfb.append_recovery_warnings(ole, errors)
        assert len(errors) == 1 and '자원 제한' in errors[0]
        assert '손상 복구' not in errors[0]


def test_warning_budget_counts_paths_and_preserves_multiple_assets():
    raw, _ = compound()
    with cfb.OleFileIO(raw) as ole:
        for index in range(100):
            ole._issue_path = 'BinData/BIN%04d' % index
            ole._record_recovery('stream read failed')
        errors = []
        cfb.append_recovery_warnings(ole, errors)
        cfb.append_recovery_warnings(ole, errors)
        assert len(ole.recovery_issues) == cfb.MAX_RECOVERY_WARNINGS
        assert len(errors) == cfb.MAX_RECOVERY_WARNINGS
        assert 'BIN0000' in errors[0] and 'BIN0015' in errors[-1]


def test_embedded_warning_budget_does_not_hide_outer_loss():
    errors = []
    issue = SimpleNamespace(recovery_issues=[('truncated stream payload', 'Workbook')])
    for index in range(40):
        cfb.append_recovery_warnings(issue, errors, scope='embedded', path='ole%d' % index)
    cfb.append_recovery_warnings(issue, errors)
    assert len(errors) == cfb.MAX_RECOVERY_WARNINGS + 1
    assert errors[-1].startswith('WARN: OLE/CFB ')
