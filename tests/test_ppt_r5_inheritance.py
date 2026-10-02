"""PowerPoint 실측에서 확인한 Other 상속과 CF 속성별 유효성 경계."""
import struct

import pytest

from dochan.office_binary.officeart import parse_records
from dochan.office_binary.ppt import parse_ppt_document_stream
from dochan.office_binary.ppt_styles import read_master_styles
from dochan.office_binary.ppt_text import render_text
from test_ppt_legacy_styles import master
from test_ppt_structure import presentation, record, sheet, slide_list
from test_ppt_text import block, cf, pf


@pytest.mark.parametrize('mask,flags,size,expected', [
    # bug45124.ppt: Environment Other is bold/italic; local CF only disables
    # italic and enables underline. PowerPoint measures bold=True, italic=False.
    (6, 5, 36, (True, False, True, 36)),
    # 45776.ppt: pp9rt does not make the bold bit valid. The 11pt bold
    # Environment Other default must survive the unrelated master Other.
    (0xC00, 0xC01, None, (True, True, False, 11)),
    (1, 0, None, (False, True, False, 11)),
])
def test_r5_other_uses_environment_not_main_master(mask, flags, size, expected):
    environment = record(1010, master(4, [(0, 0x20003, struct.pack('<HH', 3, 11))]),
                         container=True)
    main = record(1016, master(4, [(0, 0x20007, struct.pack('<HH', 0, 18))]),
                  container=True)
    props = struct.pack('<H', flags)
    if size is not None:
        mask |= 0x20000
        props += struct.pack('<H', size)
    outline = (record(3999, struct.pack('<I', 4)) + record(4008, b'Other')
               + record(4001, pf(6) + cf(6, mask, props)))
    data, current = presentation([(2, sheet(master=900)), (3, main)],
                                 [environment, slide_list([(2, 256, outline)]),
                                  slide_list([(3, 900, b'')], 1)])
    doc = parse_ppt_document_stream(data, current_user=current)
    run = doc.find_all('paragraph')[0].runs[0]
    assert (run.bold, run.italic, run.underline, run.font_size_pt) == expected
    assert not doc.errors


@pytest.mark.parametrize('source', ['slide', 'master', 'environment'])
@pytest.mark.parametrize('bit,index', [(1, 0), (2, 1), (4, 2)])
@pytest.mark.parametrize('enabled', [False, True])
def test_r5_cf_mask_changes_only_selected_property(source, bit, index, enabled):
    # Invert all unselected raw flag bits: they must neither disable inherited
    # properties nor enable absent ones, even though fontStyle is present.
    flags = bit if enabled else 7 ^ bit
    if source == 'slide':
        styles = {(1, 0): {0: True, 1: True, 2: True}}
        text = block('X', pf(2) + cf(2, bit, struct.pack('<H', flags)))
    else:
        data = record(4004, struct.pack('<IH', 7, 7))
        data += (master(1, [(0, bit, struct.pack('<H', flags))]) if source == 'master'
                 else record(4004, struct.pack('<IH', bit, flags)))
        styles = read_master_styles(parse_records(data))
        text = block('X')
    run = render_text(text, None, default_styles=styles)[0].runs[0]
    expected = [True, True, True]
    expected[index] = enabled
    assert [run.bold, run.italic, run.underline] == expected
