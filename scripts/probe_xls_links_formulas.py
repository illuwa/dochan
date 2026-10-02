"""Probe public POI samples without copying them into the repository."""
import argparse
import json
from pathlib import Path

from dochan.office_binary.xls import XLSReader
from dochan.ooxml.xlsx import XLSXReader


def cells(document):
    return {
        (cell.provenance.sheet, cell.provenance.cell): cell.text
        for section in document.sections
        for element in section.elements
        for row in getattr(element, 'rows', [])
        for cell in row
        if cell.provenance is not None
    }


def probe(root):
    checks = []
    expected = [
        ('HyperlinksOnManySheets.xls', 'internal_link', 'Internal', 'A5',
         'Link To First Sheet <#WebLinks!A1>'),
        ('SimpleWithFormula.xls', 'formula', 'Sheet1', 'A3',
         'replacemereplaceme (=CONCATENATE(A1,A2))'),
        ('StringFormulas.xls', 'formula', 'Sheet1', 'A1', 'XYZ (=UPPER("xyz"))'),
    ]
    for filename, feature, sheet, cell, text in expected:
        document = XLSReader().read(str(root / filename))
        actual = cells(document).get((sheet, cell))
        checks.append(dict(file=filename, feature=feature, sheet=sheet, cell=cell,
                           expected=text, actual=actual, passed=actual == text,
                           errors=document.errors))
    legacy = XLSReader().read(str(root / 'FormulaSheetRange.xls'))
    modern = XLSXReader().read(str(root / 'FormulaSheetRange.xlsx'))
    modern_cells, legacy_cells = cells(modern), cells(legacy)
    for coordinate in [('test', 'D11'), ('test', 'D12')]:
        expected_text, actual = modern_cells[coordinate], legacy_cells.get(coordinate)
        checks.append(dict(file='FormulaSheetRange.xls', feature='formula',
                           sheet=coordinate[0], cell=coordinate[1], expected=expected_text,
                           actual=actual, passed=actual == expected_text,
                           errors=legacy.errors))
    legacy = XLSReader().read(str(root / 'shared_formulas.xls'))
    modern = XLSXReader().read(str(root / 'shared_formulas.xlsx'))
    modern_cells, legacy_cells = cells(modern), cells(legacy)
    for coordinate, expected_text in modern_cells.items():
        if ' (=' not in expected_text:
            continue
        actual = legacy_cells.get(coordinate)
        checks.append(dict(file='shared_formulas.xls', feature='shared_formula',
                           sheet=coordinate[0], cell=coordinate[1], expected=expected_text,
                           actual=actual, passed=actual == expected_text,
                           errors=legacy.errors))
    # Public Office-authored file containing named text marks rather than cell refs.
    filename = 'com.aida-tour.www_SPO_files_maldives%20august%20october.xls'
    document = XLSReader().read(str(root / filename))
    target = '#Отель__BANYAN_TREE_VABBINFARU_MALDIVES_5___Мале'
    actual = next((text for (_, ref), text in cells(document).items()
                   if ref == 'B8' and target in text), None)
    checks.append(dict(file=filename, feature='internal_text_mark', cell='B8',
                       expected_fragment=target, actual=actual,
                       passed=actual is not None, errors=document.errors))
    return dict(checks=checks, total=len(checks), passed=sum(check['passed'] for check in checks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path, help='Public POI test-data/spreadsheet directory')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe(args.corpus)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + '\n', encoding='utf-8')
    else:
        print(rendered)
    return 0 if result['passed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
