import struct

import pytest

from test_cfb import compound


def test_tail_probe_changes_only_terminal_allocation_word():
    from scripts.probe_cfb_tail_review import replace_terminal
    raw, _ = compound()
    for value in (0xffffffff, 'cycle'):
        changed, evidence = replace_terminal(raw, 'Regular', value)
        offset = evidence['fat_word_offset']
        assert raw[:offset] == changed[:offset]
        assert raw[offset + 4:] == changed[offset + 4:]
        assert evidence['declared_bytes'] == 4096
        assert evidence['sectors'] == 8
        assert struct.unpack_from('<I', changed, offset)[0] == (
            4 if value == 'cycle' else value)


def test_tail_probe_rejects_nonregular_or_missing_stream():
    from scripts.probe_cfb_tail_review import replace_terminal
    raw, _ = compound()
    for name in ('한글', 'absent'):
        with pytest.raises(ValueError):
            replace_terminal(raw, name, 0xffffffff)
