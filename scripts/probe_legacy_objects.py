"""Read-only public POI/LibreOffice embedded-object checks and inventory.

Run: /usr/bin/python3 -m scripts.probe_legacy_objects CORPUS_ROOT --output FILE
Expected equations were transcribed from native CHAR/TMPL bytes, not inferred
from the new converter. Chart values below are decoded independently from raw
Graph Number/Label or BIFF SIIndex/Number records. No sample files are copied.
"""
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import struct

from dochan import cfb

from dochan.office_binary.doc import DOCReader
from dochan.office_binary.mtef import parse_equation_native
from dochan.office_binary.ole_objects import decompress_ppt_storage
from dochan.office_binary.ppt import PPTReader
from dochan.office_binary.ppt_structure import resolve_presentation


def records(data):
    offset = 0
    while offset + 4 <= len(data):
        sid, size = struct.unpack_from('<HH', data, offset)
        if not sid and not size:
            return
        end = offset + 4 + size
        if end > len(data):
            raise ValueError('truncated record')
        yield offset, sid, data[offset + 4:end]
        offset = end


def ppt_storages(path):
    with cfb.OleFileIO(str(path)) as ole:
        errors = []
        result = resolve_presentation(ole.openstream('PowerPoint Document').read(),
                                      ole.openstream('Current User').read(), errors)
        if result is None:
            raise ValueError('presentation unavailable')
        return result.embedded


def embedded_stream(storage, name):
    raw = decompress_ppt_storage(storage.data, storage.header.rec_instance)
    with cfb.OleFileIO(io.BytesIO(raw)) as ole:
        return ole.openstream(name).read()


def graph_cells(data):
    cells = {}
    for _, sid, value in records(data):
        if sid in (3, 4):
            key = struct.unpack_from('<HH', value)
            if sid == 3:
                cells[key] = struct.unpack_from('<d', value, 7)[0]
            else:
                count = struct.unpack_from('<H', value, 7)[0]
                cells[key] = value[9:9 + count].decode('ascii')
    return cells


def display(value):
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    return value


def inventory(root):
    counts = Counter()
    found = []
    objects = []
    failures = []
    for base in (root / 'poi-src/test-data/document', root / 'lo-src/sw/qa/extras'):
        for path in sorted(base.rglob('*.doc')):
            counts['doc_files'] += 1
            try:
                with cfb.OleFileIO(str(path)) as ole:
                    entries = ole.listdir()
                    roots = sorted({tuple(e[:-1]) for e in entries
                                    if len(e) == 3 and e[0] == 'ObjectPool'})
                    for object_root in roots:
                        names = [e[-1] for e in entries if tuple(e[:-1]) == object_root]
                        if 'Equation Native' in names:
                            counts['doc_equation_objects'] += 1
                        comp_path = list(object_root) + ['\x01CompObj']
                        comp = ole.openstream(comp_path).read() if ole.exists(comp_path) else b''
                        graph = b'MSGraph' in comp or any('graph' in n.lower() for n in names)
                        if graph:
                            counts['doc_msgraph_objects'] += 1
                        chart_streams = []
                        for name in names:
                            if name not in ('Workbook', 'Book') and 'graph' not in name.lower():
                                continue
                            data = ole.openstream(list(object_root) + [name]).read()
                            if name in ('Workbook', 'Book'):
                                counts['doc_workbook_streams'] += 1
                            try:
                                chart = any(sid == 0x809 and len(v) >= 4
                                            and struct.unpack_from('<H', v, 2)[0] in (0x20, 0x8000)
                                            for _, sid, v in records(data))
                            except ValueError:
                                chart = False
                            if chart:
                                chart_streams.append(name)
                        workbook = any(n in names for n in ('Workbook', 'Book'))
                        if workbook:
                            counts['doc_workbook_objects'] += 1
                        if chart_streams:
                            counts['doc_chart_objects'] += 1
                            found.append(str(path.relative_to(root)))
                        if workbook or graph:
                            objects.append(dict(file=str(path.relative_to(root)), object='/'.join(object_root),
                                                streams=names, msgraph=graph, chart_streams=chart_streams))
            except Exception as exc:
                counts['doc_inventory_errors'] += 1
                failures.append(dict(file=str(path.relative_to(root)), error=str(exc)))
    # Zero counts are explicit: an absent key must not imply an unperformed scan.
    for key in ('doc_msgraph_objects', 'doc_workbook_objects', 'doc_chart_objects', 'doc_inventory_errors'):
        counts.setdefault(key, 0)
    return {'counts': dict(counts), 'doc_chart_files': found,
            'doc_chart_candidates': objects, 'failures': failures}


def equation_inventory(root):
    """Measure all public native equation objects, independent of selected checks.

    Conversion coverage is not semantic correctness. Each successful object keeps
    its LaTeX for audit, while the checks in probe() compare independently read
    byte expectations. Unsupported objects stay in every denominator.
    """
    result = {}
    for fmt, extension, bases, reader in (
        ('DOC', 'doc', (root / 'poi-src/test-data/document', root / 'lo-src/sw/qa/extras'), DOCReader),
        ('PPT', 'ppt', (root / 'poi-src/test-data/slideshow',), PPTReader),
        ('PPT_LO', 'ppt', (root / 'lo-src',), PPTReader),
    ):
        objects = []
        documents = []
        inventory_errors = []
        inspected = 0
        for base in bases:
            for path in sorted(base.rglob('*.' + extension)):
                inspected += 1
                native = []
                try:
                    if fmt == 'DOC':
                        with cfb.OleFileIO(str(path)) as ole:
                            for entry in ole.listdir():
                                if len(entry) == 3 and entry[0] == 'ObjectPool' and entry[-1] == 'Equation Native':
                                    native.append(('/'.join(entry[:-1]), ole.openstream(entry).read()))
                    else:
                        for object_id, storage in ppt_storages(path).items():
                            try:
                                raw = decompress_ppt_storage(storage.data, storage.header.rec_instance)
                                with cfb.OleFileIO(io.BytesIO(raw)) as ole:
                                    if ole.exists('Equation Native'):
                                        native.append(('#ole%d' % object_id, ole.openstream('Equation Native').read()))
                            except Exception as exc:
                                inventory_errors.append(dict(file=path.name, object='#ole%d' % object_id,
                                                             error=str(exc)))
                except Exception as exc:
                    inventory_errors.append(dict(file=path.name, error=str(exc)))
                for object_id, data in native:
                    item = dict(file=path.name, object=object_id, version=data[28] if len(data) > 28 else None)
                    try:
                        item['latex'] = parse_equation_native(data)
                        item['converted'] = True
                    except ValueError as exc:
                        item.update(converted=False, error=str(exc))
                    objects.append(item)
                # PPT warnings are collected across the complete public corpus,
                # including files with only unsupported/non-target OLE objects.
                if native or extension == 'ppt':
                    try:
                        doc = reader().read(str(path))
                        documents.append(dict(file=path.name, native_objects=len(native),
                                              rendered_placements=len(doc.find_all('equation')),
                                              warnings=doc.errors))
                    except Exception as exc:
                        documents.append(dict(file=path.name, native_objects=len(native), read_error=str(exc)))
        failures = Counter(o['error'] for o in objects if not o['converted'])
        warnings = Counter(w for d in documents for w in d.get('warnings', []))
        count = len(objects)
        converted = sum(o['converted'] for o in objects)
        result[fmt] = dict(inspected_files=inspected, equation_files=len({o['file'] for o in objects}),
                           native_objects=count, converted=converted,
                           conversion_rate=converted / count if count else None,
                           failures=dict(failures), versions=dict(Counter(str(o['version']) for o in objects)),
                           warnings=dict(warnings), objects=objects, documents=documents,
                           inventory_errors=inventory_errors)
    return result


def probe(root):
    poi = root / 'poi-src/test-data'
    checks = []
    coverage = []

    def check(file, feature, target, expected, actual, basis):
        checks.append(dict(file=file, feature=feature, target=target, expected=expected,
                           actual=actual, passed=expected == actual, basis=basis))

    equations = {
        'Bug61268.doc': {
            '_1393240891': r'P=\alpha G+kG', '_1393240981': r'\left[1,n-1\right]',
            '_1393241074': r'Q_{CA}=cG', '_1393241175': r'IC_{A}=\left(ID_{A},P\right)',
        },
        'Bug50936_1.doc': {
            # These CHAR records explicitly use fnTEXT (typeface 0x81).
            '_1006857411': r'\overline{\text{x}}', '_1006945863': r'\text{s}_{\text{unexp}}^{\text{2}}',
            '_1017816140': r's^{\text{2}}(y)', '_1024144909': r'\text{s}_{\text{unexp,ln}_{\text{i}}}^{2}',
            # MTCode EB04 is kept as an explicit semantic space; no font width
            # claim is made by this normalized expectation.
            '_1018191669': r'var{\ }\left(\overline{x}(y)\right){\ }={\ }\frac{s^{2}\text{(}y\text{)}}{n(y)}',
        },
        'tdf79553_lineNumbers.doc': {
            '_1082196845': r'x=Asin\theta', '_1082196850': r'y=Acos\theta',
            '_1082196875': r'\left(1-x\right)^{n}=1-nx+\frac{n(n-1)}{2}x^{2}-\frac{n(n-1)(n-2)}{3\cdot 2}x^{3}+\ldots',
        },
    }
    for name, expected in equations.items():
        path = (root / 'lo-src/sw/qa/extras/ww8export/data' if name.startswith('tdf') else poi / 'document') / name
        doc = DOCReader().read(str(path))
        rendered = [e.latex for e in doc.find_all('equation')]
        failures = Counter()
        converted_values = {}
        total = converted = 0
        with cfb.OleFileIO(str(path)) as ole:
            for entry in ole.listdir():
                if entry[-1] != 'Equation Native':
                    continue
                total += 1
                try:
                    actual = parse_equation_native(ole.openstream(entry).read())
                    converted += 1
                    converted_values[entry[-2]] = actual
                except ValueError as exc:
                    failures[str(exc)] += 1
        # A missing or newly unsupported expected object must fail, not disappear
        # from the denominator and make the remaining checks look successful.
        for object_id, wanted in expected.items():
            actual = converted_values.get(object_id)
            check(name, 'DOC 수식', 'ObjectPool/' + object_id, wanted, actual, '원시 MTEF CHAR/TMPL 바이트 전사')
            check(name, 'DOC 수식 위치', object_id, True, wanted in rendered, 'ObjectPool ID와 EMBED 필드 연결')
        coverage.append(dict(file=name, native_objects=total, converted=converted,
                             rendered_placements=len(rendered), unsupported=dict(failures), warnings=doc.errors))
    excluded = DOCReader().read(str(poi / 'document/equation.doc'))
    check('equation.doc', '판정 제외', 'Equation.3 elements', 0, len(excluded.find_all('equation')),
          'ObjectPool에 Equation Native가 없고 package_stream이 있음')

    docs = {}
    for name in ('42520.ppt', 'bug61881.ppt', '37625.ppt', 'bug60345_suba.ppt', 'npe.ppt',
                 '23884_defense_FINAL_OOimport_edit.ppt'):
        path = poi / 'slideshow' / name
        docs[name] = (PPTReader().read(str(path)), ppt_storages(path))
    for name, object_id, slide, by_rows, axes, points, extra, title, kind in [
        ('42520.ppt', 57, 16, True, [1], range(1, 15), [], None, 'line'),
        ('bug61881.ppt', 1, 27, True, [1, 2], range(1, 6), [], None, 'column'),
        ('37625.ppt', 80, 13, False, [1], range(1, 5), [], None, 'pie'),
        ('37625.ppt', 521, 4, False, [1], range(1, 14), [], '… large share of old vehicles', 'line'),
    ]:
        doc, storages = docs[name]
        raw = embedded_stream(storages[object_id], 'Workbook')
        cells = graph_cells(raw)
        def cell(axis, point):
            return display(cells.get((axis, point) if by_rows else (point, axis), ''))
        names = [cell(axis, 0) for axis in axes]
        if name == '42520.ppt':
            names = ['Line 1']  # Saved SeriesText; datasheet has no label for this series.
        expected = [['Category'] + names + extra]
        expected += [[cell(0, point)] + [cell(axis, point) for axis in axes] + [''] * len(extra) for point in points]
        path_suffix = '#ole%d' % object_id
        tables = [t for t in doc.find_all('table') if t.rows and t.rows[0][0].provenance
                  and t.rows[0][0].provenance.path.endswith(path_suffix)]
        actual = [[c.text for c in row] for row in tables[0].rows] if len(tables) == 1 else []
        check(name, 'PPT 차트 데이터', 'slide%d/ole%d' % (slide, object_id), expected, actual,
              '원시 Graph Number(0x0003)/Label(0x0004) 행·열·값')
        if tables:
            check(name, 'PPT 차트 위치', path_suffix, slide, tables[0].rows[0][0].provenance.slide,
                  '슬라이드 ExObjRefAtom → 최신 ExOleObjStg')
            check(name, 'PPT 차트 종류', path_suffix, 'Chart type: ' + kind,
                  tables[0].caption[0].text.split(';', 1)[0], '원시 Line/Bar/Pie 차트 레코드')
        if title:
            actual_titles = [p.text for p in doc.find_all('paragraph') if p.heading_level == 3 and p.provenance
                             and p.provenance.path.endswith(path_suffix)]
            check(name, 'PPT 차트 제목', path_suffix, [title], actual_titles, 'SeriesText와 ObjectLink=1의 원시 문자열')
    doc, _ = docs['42520.ppt']
    check('42520.ppt', 'PPT 수식', 'slide16/ole61', [r'y=0.317+(-.008\bullet DSO)'],
          [e.latex for e in doc.sections[15].elements if type(e).__name__ == 'Equation'],
          'MTEF CHAR의 y=0.317+(-.008 U+2022 DSO)와 ExObjRefAtom=61')

    # MTEF2 characters are one byte, including Symbol C7/C4; MTEF5
    # definitions precede the real LINE and CHAR records in both examples.
    ppt_equations = {
        'npe.ppt': {
            63: r'O\left(T\left[\frac{D}{F}\right](2^{F}-1)\right)',
            64: r'\cap', 65: r'\cap', 66: r'\cap', 67: r'\cap', 68: r'\otimes',
        },
        '37625.ppt': {
            37: r'(Vehicle\_kms)\times \left(\frac{Emissions}{km}\right)',
            201: r'(Vehicles)\times \left(Utilisation\right)',
        },
        '23884_defense_FINAL_OOimport_edit.ppt': {
            55: r'\Delta {\ }t_{1}', 61: r'\Delta {\ }t_{N}',
            68: r'\Delta {\ }t_{N}-\Delta {\ }t_{1}',
        },
    }
    # Raw ExObjRefAtom(3009) records locate these object IDs in SlideContainer.
    equation_slides = {'npe.ppt': {63: 29, 64: 27, 65: 27, 66: 27, 67: 27, 68: 27},
                       '37625.ppt': {37: 24, 201: 24},
                       '23884_defense_FINAL_OOimport_edit.ppt': {55: 26, 61: 26, 68: 26}}
    for name, expected in ppt_equations.items():
        doc, storages = docs[name]
        for object_id, wanted in expected.items():
            try:
                actual = parse_equation_native(embedded_stream(storages[object_id], 'Equation Native'))
            except ValueError:
                actual = None
            check(name, 'PPT 수식', '#ole%d' % object_id, wanted, actual,
                  '원시 MTEF CHAR/TMPL 바이트 전사. v2 Symbol C7=교집합/C4=텐서곱, v5 MTCode와 분수·괄호 슬롯. EB02는 폭을 단정하지 않는 명시적 공백')
        for wanted in sorted(set(expected.values())):
            expected_slides = sorted(equation_slides[name][oid] for oid, value in expected.items() if value == wanted)
            actual_slides = [index for index, section in enumerate(doc.sections, 1)
                             for element in section.elements
                             if type(element).__name__ == 'Equation' and element.latex == wanted]
            check(name, 'PPT 수식 위치', wanted, expected_slides, actual_slides,
                  'ExObjRefAtom(3009)의 object ID와 SlideContainer 순번. 같은 수식의 반복 개수도 대조함')

    doc, storages = docs['bug60345_suba.ppt']
    for object_id, title in [(104, 'PBMC proliferative responses to BmA and PHA by different groups'), (85, 'IgG3')]:
        check('bug60345_suba.ppt', 'PPT Excel 차트 제목', '#ole%d' % object_id, [title],
              [p.text for p in doc.find_all('paragraph') if p.heading_level == 3 and p.provenance
               and p.provenance.path.endswith('#ole%d' % object_id)], '원시 SeriesText와 ObjectLink=1')
    # The selected primary-series counts are fixed by the raw Series records;
    # never derive expected dimensions from the implementation's output table.
    for object_id, series_count in [(104, 7), (105, 11), (106, 5), (85, 7)]:
        tables = [t for t in doc.find_all('table') if t.rows and t.rows[0][0].provenance
                  and t.rows[0][0].provenance.path.endswith('#ole%d' % object_id)]
        raw = embedded_stream(storages[object_id], 'Workbook')
        active = 0
        offsets = []
        for _, sid, value in records(raw):
            if sid == 0x85:
                offsets.append(struct.unpack_from('<I', value)[0])
            elif sid == 0x3d:
                active = struct.unpack_from('<H', value, 10)[0]
            elif sid == 10:
                break
        start = offsets[active]
        end = min((off for off in offsets if off > start), default=len(raw))
        role = 0
        cached = {}
        for _, sid, value in records(raw[start:end]):
            if sid == 0x1065:
                role = struct.unpack_from('<H', value)[0]
            elif sid == 0x203 and role == 1:
                row, col = struct.unpack_from('<HH', value)
                cached[(row, col)] = struct.unpack_from('<d', value, 6)[0]
        expected = [[display(cached.get((0, col), '')) for col in range(series_count)]]
        actual = [[c.text for c in row[1:]] for row in tables[0].rows[1:]] if len(tables) == 1 else []
        check('bug60345_suba.ppt', 'PPT Excel 차트 캐시', '#ole%d' % object_id, expected, actual,
              'Window1.itabCur + SIIndex=1 아래 Number 레코드. 보조 오차 막대 계열은 제외함')
    return dict(inventory=inventory(root), equation_inventory=equation_inventory(root), coverage=coverage, checks=checks,
                passed=sum(c['passed'] for c in checks), total=len(checks),
                ppt_warnings={name: doc.errors for name, (doc, _) in docs.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe(args.corpus)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
        print(json.dumps({key: result[key] for key in ('inventory', 'passed', 'total')}, ensure_ascii=False))
    else:
        print(rendered)
    return 0 if result['passed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
