"""[MS-PPT] TextMasterStyleAtom character defaults, keyed by text type/level.

Main styles use implicit level indexes; special types 5..8 serialize the
level explicitly. Absent bits inherit, whereas a present zero disables a
property. No common document model or output syntax is introduced here.
"""
from .ppt_text import _Cursor, _character_properties, _paragraph_properties, _warn

PROPERTY_BITS = (1, 2, 4, 0x20000, 0x80000)
BASE_TYPES = {5: 1, 6: 0, 7: 1, 8: 1}


def read_master_styles(records, errors=None):
    result = {}
    for atom in records:
        if atom.header.rec_type == 4004:
            cursor = _Cursor(atom.data)
            try:
                mask = cursor.read('<I')
                values = _character_properties(cursor, mask)
                result.setdefault((-1, -1), {}).update(
                    {i: values[i] for i, bit in enumerate(PROPERTY_BITS) if mask & bit})
            except ValueError as exc:
                _warn(errors, 'default character ' + str(exc))
            continue
        if atom.header.rec_type != 4003:
            continue
        kind = atom.header.rec_instance
        if kind > 8:
            continue
        cursor = _Cursor(atom.data)
        previous = {}
        try:
            count = cursor.read('<H')
            if count > 5:
                raise ValueError('style level count limit exceeded')
            for index in range(count):
                level = cursor.read('<H') if kind >= 5 else index
                if level > 4:
                    raise ValueError('style level out of range')
                _paragraph_properties(cursor, cursor.read('<I'))
                mask = cursor.read('<I')
                values = _character_properties(cursor, mask)
                current = dict(previous)
                current.update({i: values[i] for i, bit in enumerate(PROPERTY_BITS) if mask & bit})
                result[(kind, level)] = current
                previous = current
        except ValueError as exc:
            _warn(errors, 'master ' + str(exc))
    return result


def merge_styles(*sources):
    result = {}
    for source in sources:
        for key, values in source.items():
            result.setdefault(key, {}).update(values)
    return result


def style_for(styles, kind, level):
    result = dict(styles.get((-1, -1), {}))
    # TextCharacterStyleAtom provides the common character default. A
    # TextMasterStyleAtom for Other (type 4), including one in Environment,
    # remains type-specific rather than becoming a body/title default.
    base = BASE_TYPES.get(kind, kind)
    result.update(styles.get((base, level), styles.get((base, 0), {})))
    if base != kind:
        result.update(styles.get((kind, level), styles.get((kind, 0), {})))
    return result
