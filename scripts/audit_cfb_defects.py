"""Public-corpus CFB defect evidence, independently decoded from MS-CFB fields.

The baseline IDs use compare_cfb_olefile.discover_ole ordering. This tool never
reads reference implementation source. Paths outside the public corpus families
are rejected; directory names and document contents are omitted from the output.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from scripts.compare_cfb_olefile import MAX_INPUT, discover_ole

FREE, END, FAT, DIF = 0xffffffff, 0xfffffffe, 0xfffffffd, 0xfffffffc
MAX_STEPS = 2000000
MAX_FINDINGS = 20000
PUBLIC_FAMILIES = {'poi-src', 'lo-src', 'tika-test-docs', 'hwp-public'}


def public_relative(path, corpus):
    relative = Path(path).resolve().relative_to(Path(corpus).resolve())
    if not relative.parts or relative.parts[0] not in PUBLIC_FAMILIES:
        raise ValueError('only public corpus families may be reported')
    return 'corpus/' + relative.as_posix()


def audit_bytes(data):
    """Return numeric raw-byte evidence; bounded even for malformed metadata."""
    findings = []
    result = {'bytes': len(data), 'findings': findings}

    def note(code, **fields):
        if len(findings) < MAX_FINDINGS:
            findings.append(dict(code=code, **fields))

    if len(data) < 512:
        note('header_truncated', actual=len(data), expected=512)
        return result
    version, byte_order, shift, mini_shift = struct.unpack_from('<4H', data, 26)
    fields = struct.unpack_from('<9I', data, 40)
    header = dict(zip(('directory_count', 'fat_count', 'first_directory', 'transaction',
                       'cutoff', 'first_minifat', 'minifat_count', 'first_difat', 'difat_count'), fields))
    header.update(version=version, byte_order=byte_order, sector_shift=shift, mini_shift=mini_shift)
    result['header'] = header
    for code, actual, expected in [('byte_order', byte_order, 65534),
                                   ('mini_shift', mini_shift, 6), ('cutoff', header['cutoff'], 4096)]:
        if actual != expected:
            note(code, actual=actual, expected=expected)
    if version not in (3, 4) or shift != {3: 9, 4: 12}.get(version):
        note('version_sector_shift', version=version, shift=shift)
    if shift not in (9, 12):
        return result
    sector_size = 1 << shift
    sector_count = max(0, (len(data) - 1) // sector_size)
    header.update(sector_count=sector_count, tail_bytes=len(data) % sector_size)
    if len(data) % sector_size:
        note('partial_last_sector', sector=sector_count - 1, bytes=len(data) % sector_size)
    owners, mini_owners = {}, {}
    budget = [MAX_STEPS]

    def sector(sid):
        if not 0 <= sid < sector_count:
            return b''
        return data[(sid + 1) * sector_size:(sid + 2) * sector_size]

    def words(raw):
        size = len(raw) // 4
        return list(struct.unpack_from('<%dI' % size, raw))

    def claim(sid, owner, mini=False, tail=False):
        allocation = mini_owners if mini else owners
        if sid in allocation and allocation[sid][0] != owner:
            previous, previous_tail = allocation[sid]
            if tail or previous_tail:
                note('allocation_unused_tail_crosslink', owner=owner, previous_owner=previous,
                     sector=sid, mini=mini, current_tail=tail, previous_tail=previous_tail)
            else:
                note('allocation_crosslink', owner=owner, previous_owner=previous, sector=sid, mini=mini)
            # A tail reservation must never hide an earlier live owner.
            if not previous_tail:
                return
        allocation[sid] = (owner, tail)

    def chain(start, table, owner, count=None, mini=False, bound=None):
        visited, ids = set(), []
        sid = start
        limit = sector_count if bound is None else bound
        while sid != END:
            budget[0] -= 1
            if budget[0] < 0:
                note('audit_step_limit', owner=owner)
                break
            if sid in visited:
                note('allocation_cycle', owner=owner, sector=sid, mini=mini, visited=len(ids))
                break
            if not 0 <= sid < min(limit, len(table)):
                note('allocation_outside', owner=owner, sector=sid, mini=mini,
                     sector_bound=limit, table_words=len(table), visited=len(ids))
                break
            visited.add(sid)
            ids.append(sid)
            claim(sid, owner, mini, tail=count is not None and len(ids) > count)
            if table[sid] is None:
                note('allocation_missing_word', owner=owner, sector=sid, mini=mini)
                break
            sid = table[sid]
        if count is not None and len(ids) != count:
            note('chain_length', owner=owner, expected=count, actual=len(ids), terminator=sid, mini=mini)
        return ids

    fat_ids = list(struct.unpack_from('<109I', data, 76))
    dif_ids, seen_dif = [], set()
    sid = header['first_difat']
    for _ in range(min(header['difat_count'], sector_count + 1)):
        if sid in seen_dif or not 0 <= sid < sector_count:
            note('difat_cycle_or_outside', sector=sid, visited=len(seen_dif))
            break
        seen_dif.add(sid)
        dif_ids.append(sid)
        claim(sid, 'DIFAT')
        block = words(sector(sid))
        if len(block) != sector_size // 4:
            note('difat_truncated', sector=sid, words=len(block))
            break
        fat_ids.extend(block[:-1])
        sid = block[-1]
    if header['difat_count'] and sid != END:
        note('difat_terminator', actual=sid, expected=END)
    declared = header['fat_count']
    slack = sum(sid != FREE for sid in fat_ids[declared:])
    if slack:
        note('difat_unused_slots', count=slack)
    if declared > len(fat_ids):
        note('difat_fat_count', declared=declared, available_slots=len(fat_ids))
    fat_ids = fat_ids[:min(declared, sector_count)]
    fat = []
    for slot, sid in enumerate(fat_ids):
        if sid == FREE:
            note('difat_missing_slot', slot=slot, sector=sid)
        if 0 <= sid < sector_count:
            if sid in owners and owners[sid][0] == 'FAT':
                note('fat_sector_duplicate', slot=slot, sector=sid)
            claim(sid, 'FAT')
        block = words(sector(sid))
        if len(block) != sector_size // 4:
            note('fat_sector_truncated_or_outside', sector=sid, words=len(block))
        # A missing FAT page/word occupies its original logical address range.
        # None denotes unknown data and is never interpreted as FREE or END.
        fat.extend(block + [None] * (sector_size // 4 - len(block)))
    for ids, marker in ((fat_ids, FAT), (dif_ids, DIF)):
        for sid in ids:
            actual = fat[sid] if 0 <= sid < len(fat) else None
            if actual != marker:
                note('allocation_marker', sector=sid, actual=actual, expected=marker)
    directory = chain(header['first_directory'], fat, 'directory')
    entries, entry_bytes = {}, {}
    for ordinal, sid in enumerate(directory):
        raw = sector(sid)
        for local in range(len(raw) // 128):
            index = ordinal * (sector_size // 128) + local
            if index >= 131072:
                break
            entry_bytes[index] = raw[local * 128:(local + 1) * 128]
            record = entry_bytes[index]
            length, kind, color, left, right, child = struct.unpack_from('<HBBIII', record, 64)
            start = struct.unpack_from('<I', record, 116)[0]
            size = struct.unpack_from('<I' if version == 3 else '<Q', record, 120)[0]
            entries[index] = dict(length=length, kind=kind, color=color, left=left,
                                  right=right, child=child, start=start, size=size)
    pending, reached = [0], set()
    while pending and budget[0] > 0:
        budget[0] -= 1
        index = pending.pop()
        if index == FREE:
            continue
        if index in reached:
            note('directory_cycle_or_crosslink', entry=index)
            continue
        if index not in entries:
            note('directory_outside', entry=index, entry_count=len(entries))
            continue
        reached.add(index)
        entry = entries[index]
        if entry['kind'] not in ((5,) if index == 0 else (1, 2)):
            note('directory_type', entry=index, actual=entry['kind'])
        if entry['color'] not in (0, 1):
            note('directory_color', entry=index, actual=entry['color'])
        length = entry['length']
        if not 2 <= length <= 64 or length % 2:
            note('directory_name_length', entry=index, actual=length)
        else:
            raw_name = entry_bytes[index][:length]
            if raw_name[-2:] != b'\0\0':
                note('directory_name_terminator', entry=index, actual=int.from_bytes(raw_name[-2:], 'little'))
            try:
                name = raw_name[:-2].decode('utf-16le')
                if '\0' in name or (not name and index != 0):
                    note('directory_name_empty_or_nul', entry=index)
            except UnicodeError:
                note('directory_name_utf16', entry=index)
        if index != 0:
            pending.extend((entry['right'], entry['left']))
        if entry['kind'] in (1, 5):
            pending.append(entry['child'])
        elif entry['child'] != FREE:
            note('stream_child_pointer', entry=index, child=entry['child'])
    result['reachable_entries'] = len(reached)
    result['orphan_live_entries'] = sum(i not in reached and e['kind'] in (1, 2, 5) for i, e in entries.items())
    if 0 not in entries:
        return result
    root = entries[0]
    result['root_size'] = root['size']
    root_chain = chain(root['start'], fat, 'root', (root['size'] + sector_size - 1) // sector_size) if root['size'] else []
    mini_chain = chain(header['first_minifat'], fat, 'MiniFAT', header['minifat_count']) if header['minifat_count'] else []
    minifat = []
    for sid in mini_chain:
        block = words(sector(sid))
        minifat.extend(block + [None] * (sector_size // 4 - len(block)))
    for index in sorted(reached - {0}):
        e = entries[index]
        if e['kind'] != 2 or not e['size']:
            continue
        mini = e['size'] < 4096
        unit = 64 if mini else sector_size
        ids = chain(e['start'], minifat if mini else fat, 'entry:%d' % index,
                    (e['size'] + unit - 1) // unit, mini,
                    (root['size'] + 63) // 64 if mini else None)
        if e['size'] > 256 * 1024 * 1024:
            note('native_stream_size_limit', entry=index, size=e['size'])
        remaining = e['size']
        for sid in ids:
            take = min(remaining, unit)
            if take <= 0:
                break
            if mini:
                root_sector, within = divmod(sid * 64, sector_size)
                if root_sector >= len(root_chain):
                    note('mini_payload_outside_root_chain', entry=index, sector=sid)
                    break
                offset = (root_chain[root_sector] + 1) * sector_size + within
            else:
                offset = (sid + 1) * sector_size
            if offset + take > len(data):
                note('payload_truncated', entry=index, sector=sid, offset=offset, requested=take,
                     available=max(0, len(data) - offset), mini=mini)
                break
            remaining -= take
    outside_unused = sum(value is not None and value < DIF and value >= sector_count and sid not in owners
                         for sid, value in enumerate(fat))
    if outside_unused:
        note('unused_fat_outside', count=outside_unused)
    return result


def inspect_native(path):
    from dochan import cfb
    result = {'accepted': False, 'stream_errors': []}
    try:
        with cfb.OleFileIO(path) as ole:
            result['accepted'] = True
            for stream_path in ole.listdir():
                index = ole._find(stream_path)
                try:
                    with ole.openstream(stream_path) as stream:
                        while stream.read(1024 * 1024):
                            pass
                except (OSError, ValueError) as exc:
                    result['stream_errors'].append({'entry': index, 'error': str(exc)})
            result['warnings'] = list(ole.parsing_issues)
    except (OSError, ValueError) as exc:
        result['error'] = str(exc)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='+', type=Path)
    parser.add_argument('--corpus', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--reference', action='store_true', help='also compare through optional olefile API')
    args = parser.parse_args(argv)
    paths = discover_ole(args.roots)
    baseline = json.loads(args.baseline.read_text())
    if len(paths) != baseline['discovered']:
        raise ValueError('corpus discovery count differs from baseline; file IDs are not reliable')
    records = []
    for row in baseline['records']:
        if row['status'] == 'equal':
            continue
        path = Path(paths[row['id']])
        name = public_relative(path, args.corpus)
        with path.open('rb') as source:
            data = source.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise ValueError('audit input size limit')
        record = dict(id=row['id'], path=name, baseline=row,
                      sha256=hashlib.sha256(data).hexdigest(), raw=audit_bytes(data), native=inspect_native(path))
        if args.reference:
            from scripts.compare_cfb_olefile import _cfb_compare
            try:
                record['comparison'] = _cfb_compare(str(path))
            except ModuleNotFoundError as exc:
                if exc.name != 'olefile':
                    raise
                record['comparison'] = {'skipped': 'optional_reference_olefile_not_installed'}
        records.append(record)
    output = {'discovered': len(paths), 'audited': len(records), 'records': records,
              'finding_counts': dict(Counter(f['code'] for r in records for f in r['raw']['findings']))}
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'audited': len(records), 'finding_counts': output['finding_counts']}))


if __name__ == '__main__':
    main()
