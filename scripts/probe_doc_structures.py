"""공개 DOC 코퍼스의 전수 회귀 및 기능별 실물 기대값을 측정한다.

예: /usr/bin/python3 -m scripts.probe_doc_structures CORPUS --output result.json
코퍼스는 읽기만 하며 원본 파일이나 이미지 바이트를 결과에 복사하지 않는다.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from dochan.model.table import Table
from dochan.office_binary.doc import DOCReader
from dochan.output.markdown import to_markdown


def snapshot(path):
    doc = DOCReader().read(str(path))
    markdown = to_markdown(doc)
    tables = doc.find_all('table')
    return doc, {
        'file': path.name, 'tokens': len(markdown.split()), 'chars': len(markdown),
        'errors': doc.errors,
        'tables': [{'rows': t.row_count, 'cols': t.col_count,
                    'spans': [[c.row, c.col, c.row_span, c.col_span]
                              for row in t.rows for c in row
                              if not c.is_merged_away and (c.row_span > 1 or c.col_span > 1)]}
                   for t in tables],
        'images': [{'format': i.image_format, 'bytes': len(i.image_data),
                    'sha256': hashlib.sha256(i.image_data).hexdigest(), 'alt_text': i.alt_text}
                   for i in doc.find_all('image')],
        'notes': {kind: len(doc.find_all(kind))
                  for kind in ('header', 'footer', 'footnote', 'endnote', 'comment')},
    }


def verify_features(docs):
    checks = []

    def check(name, feature, source, expected, get_actual):
        if name not in docs:
            return
        try:
            actual = get_actual(docs[name])
            passed = actual == expected
        except (IndexError, KeyError, AttributeError) as exc:
            actual, passed = str(exc), False
        checks.append(dict(file=name, feature=feature, source=source,
                           expected=expected, actual=actual, passed=passed))

    check('simple-table.doc', '표 구조', '문서 본문 선언과 원시 TAP',
          [['Cell 1,1', 'Cell 1,2', 'Cell 1,3'], ['Cell 2,1', 'Cell 2,2', 'Cell 2,3']],
          lambda d: [[c.text for c in row] for row in d.find_all('table')[0].rows])
    check('innertable.doc', '중첩 표', 'TestTableRow.java:42-64', [[3, 3], [2, 2]],
          lambda d: [[t.row_count, t.col_count] for t in d.find_all('table')])
    check('innertable.doc', '중첩 읽기 순서', '원시 itap 및 CP 순서', ['E', 'TABLE', 'F'],
          lambda d: ['TABLE' if isinstance(e, Table) else e.text.strip()
                     for e in d.find_all('table')[0].rows[1][1].paragraphs])
    check('table-merges.doc', '가로 병합', 'TestWordToHtmlConverter.java:86-88', [3, 2],
          lambda d: [c.col_span for c in d.find_all('table')[0].rows[0] if not c.is_merged_away])
    check('Bug47958.doc', '세로 병합', 'CP55 TC 0x6e0 시작, CP80-277 TC 0x6a0 계속',
          [9, [0] * 8], lambda d: [d.find_all('table')[0].rows[0][4].row_span,
                                   [row[4].row_span for row in d.find_all('table')[0].rows[1:]]])
    check('58804.doc', '빈 행과 열 좌표', '원시 PAPX의 8행 3열; 첫째 행의 빈 셀',
          [8, 3, [[0, 0, ''], [0, 1, ''], [0, 2, '']]],
          lambda d: [d.find_all('table')[0].row_count, d.find_all('table')[0].col_count,
                     [[c.row, c.col, c.text] for c in d.find_all('table')[0].rows[0]]])
    check('Bug48065.doc', '빈 행·열 전체 보존', '원시 CP35-63의 4행 TAP, 셀 수4',
          [['', 'asa', '', ''], ['', 'as', '', ''], ['asa', '', '', ''], ['', '', '', '']],
          lambda d: [[c.text for c in row] for row in d.find_all('table')[0].rows])
    for kind, expected, line in [('footnote', 'TestFootnote', 234), ('endnote', 'TestEndnote', 248),
                                 ('comment', 'TestComment', 260)]:
        check('footnote.doc', kind, 'TestWordExtractor.java:%d' % line, [expected],
              lambda d, kind=kind: [n.text.strip() for n in d.find_all(kind)])
    check('footnote.doc', '주석 작성자', 'ATRDPre10/GrpXstAtnOwners 원시 바이트',
          'Maxim Valyanskiy', lambda d: d.find_all('comment')[0].author)
    check('HeaderFooterUnicode.doc', '머리글 Unicode', 'TestWordExtractor.java:199',
          ['This is a simple header, with a € euro symbol in it.'],
          lambda d: [h.text.strip() for h in d.find_all('header') if h.text.strip()])
    check('HeaderFooterUnicode.doc', '바닥글 Unicode', 'TestWordExtractor.java:223',
          ['The footer, with Molière, has Unicode in it.'],
          lambda d: [h.text.strip() for h in d.find_all('footer') if h.text.strip()])
    check('HeaderFooterUnicode.doc', '스타일 상속', 'STSH Heading1 bold 및 OOXML styles.xml',
          True, lambda d: any(p.text.strip() == 'Molière' and p.runs[0].bold
                              for p in d.find_all('paragraph')))
    check('two_images.doc', '이미지 참조', 'TestPictures.java:73-86', ['jpg', 'png'],
          lambda d: [i.image_format for i in d.find_all('image')])
    check('pictures_escher.doc', '떠 있는 이미지', '원시 PlcfSpa SPID 1027/1026 및 BStore', 2,
          lambda d: len(d.find_all('image')))
    check('Picture_Alternative_Text.doc', '대체 텍스트', 'TestPictures.java:362',
          ['This is the alternative text for the picture.'],
          lambda d: [i.alt_text for i in d.find_all('image')])
    check('hyperlink.doc', '외부 URL', '원시 HYPERLINK 필드', True,
          lambda d: '<http://testuri.org/>' in to_markdown(d))
    check('Bug51686.doc', '내부 링크', '원시 HYPERLINK 및 북마크 PLC', True,
          lambda d: all(s in to_markdown(d) for s in ('<#OnMainHeading>', '<#OnLevel3>')))
    check('Bug51686.doc', '북마크', 'SttbfBkmk/PlcfBkf/PlcfBkl 원시 바이트', True,
          lambda d: all(s in to_markdown(d) for s in ('[bookmark: OnMainHeading]', '[bookmark: OnLevel3]')))
    check('MarkAuthorsTable.doc', '변경 추적 삽입', 'CHPX CP 1612-1653의 삽입·굵게·밑줄', True,
          lambda d: any('Adding something here for tracked changes' in r.text and r.bold and r.underline
                        for p in d.find_all('paragraph') for r in p.runs))
    check('MarkAuthorsTable.doc', '변경 추적 삭제', 'CHPX CP434-487의 sprmCFRMarkDel', False,
          lambda d: 'The two top level models making up the framework are:' in to_markdown(d))
    check('Bug52583.doc', '드롭다운 컨트롤', 'TestWordToHtmlConverter.java:60', True,
          lambda d: 'riri' in to_markdown(d) and 'FORMDROPDOWN' not in to_markdown(d))
    check('FloatingPictures.doc', '그림 캡션', 'SEQ Figure CP4662/4685/4687 캐시 결과1', True,
          lambda d: any(p.text == 'Figure 1  Spacewalk' for p in d.find_all('paragraph')))
    check('FloatingPictures.doc', '혼합 요소 읽기 순서', 'CP4625 설명, CP4653 그림, CP4655 캡션',
          ['This picture has a caption:', 'Image', 'Figure 1  Spacewalk'],
          lambda d: [getattr(e, 'text', type(e).__name__) for e in d.sections[0].elements[83:86]])
    check('Bug51890.doc', '깊이 1→3 중첩 표', 'PAPX CP1551-1631 깊이와 셀 경계',
          [8, 1, 1, 2, [[1, 1], [1, 1]]],
          lambda d: [d.find_all('table')[0].row_count, d.find_all('table')[0].col_count,
                     d.find_all('table')[0].rows[2][0].paragraphs[0].row_count,
                     d.find_all('table')[0].rows[2][0].paragraphs[0].col_count,
                     [[c.paragraphs[0].row_count, c.paragraphs[0].col_count]
                      for c in d.find_all('table')[0].rows[2][0].paragraphs[0].rows[0]]])
    check('53446.doc', '삭제된 표 골격 제거', 'CHPX 삭제 행 끝 16개 및 PAPX',
          [[13, 5], [13, 5], [13, 4], [13, 4]],
          lambda d: [[t.row_count, t.col_count] for t in d.find_all('table')])
    check('53446.doc', '삭제 표 앞의 정상 본문 보존', 'CP12511-13392의 본문과 삭제 CR/표 경계', True,
          lambda d: 'This proposal contemplates that Lakeland would authorize' in to_markdown(d))
    check('tdf106799.doc', '깊이 0→2 중첩 표', 'LO ww8import.cxx:107-126',
          [1, 1, 3, 4, 4],
          lambda d: [d.find_all('table')[0].row_count, d.find_all('table')[0].col_count,
                     d.find_all('table')[0].rows[0][0].paragraphs[0].row_count,
                     d.find_all('table')[0].rows[0][0].paragraphs[0].col_count,
                     d.find_all('table')[0].rows[0][0].paragraphs[0].rows[0][0].col_span])
    check('fdo53985.doc', '페이지 경계와 중첩 표', 'LO ww8export3.cxx:369-374',
          [[2, 1], [1, 1], [2, 1], [1, 1], [1, 1]],
          lambda d: [[t.row_count, t.col_count] for t in d.find_all('table')])
    check('n750255.doc', '페이지 경계 텍스트', '원시 CP의 one/0x0c/two', ['one', 'two'],
          lambda d: [p.text for p in d.find_all('paragraph')])
    check('msobrightnesscontrast.doc', '떠 있는 이미지 대체 텍스트',
          'PlcfSpa CP0 SPID1027, OfficeArt wzDescription', ['MSlogo (2)'],
          lambda d: [i.alt_text for i in d.find_all('image')])
    check('tdf124601.doc', '떠 있는 이미지 대체 텍스트',
          'PlcfSpa CP4/SPID1027 및 CP9/SPID1026, wzDescription',
          ['Title: audit und emas  - Description: Die Logos von audit familiengerechte hochschule und emas Umweltmanagement',
           'Title: Zufahrt Rollstuhlfahrer - Description: Icon Rollstuhlfahrer'],
          lambda d: [i.alt_text for i in d.find_all('image')])
    check('tdf81705_outlineLevel.doc', '내부 하이퍼링크', '원시 필드 CP42/73/106', True,
          lambda d: '<#_Toc68096040>' in to_markdown(d))
    check('tdf56738.doc', '내부 하이퍼링크', '원시 HYPERLINK 캐시 필드53개', 53,
          lambda d: to_markdown(d).count('<#__RefHeading__'))
    check('bnc636128.doc', '내부 북마크', 'SttbfBkmk/PlcfBkf/PlcfBkl 원시 바이트', True,
          lambda d: '[bookmark: Text2]' in to_markdown(d))
    check('bordercolours.doc', '내부 북마크', 'SttbfBkmk의 공개 이름5개 및 PLC',
          ['ParagraphBorder', 'BetwixtParagraphBorder', 'CharBorder', 'CharShadowBorder', 'PictureBorder'],
          lambda d: re.findall(r'\[bookmark: ([^]]+)\]', to_markdown(d)))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--lo-corpus', type=Path, help='LibreOffice source root')
    args = parser.parse_args()
    baseline = {}
    if args.baseline:
        before = json.loads(args.baseline.read_text(encoding='utf-8'))
        baseline = {r['file']: r for r in (before['documents'] if isinstance(before, dict) else before)}
    rows, docs, exceptions = [], {}, []
    for path in sorted(args.corpus.iterdir()):
        if not path.is_file() or path.suffix.lower() != '.doc':
            continue
        try:
            doc, row = snapshot(path)
            docs[path.name] = doc
            if path.name in baseline:
                old = baseline[path.name]
                row['before_tokens'] = old['tokens']
                row['token_ratio'] = row['tokens'] / old['tokens'] if old['tokens'] else None
                row['new_fatal_error'] = (any(e.startswith('ERR:') for e in row['errors'])
                                          and not any(e.startswith('ERR:') for e in old['errors']))
            rows.append(row)
        except Exception as exc:
            exceptions.append({'file': path.name, 'error': str(exc)})
    lo_rows = []
    if args.lo_corpus:
        samples = {'ww8export': ['fdo53985.doc', 'n750255.doc', 'msobrightnesscontrast.doc',
                                'tdf81705_outlineLevel.doc', 'tdf56738.doc',
                                'bnc636128.doc', 'bordercolours.doc'],
                   'ww8import': ['tdf106799.doc', 'tdf124601.doc']}
        for group, names in samples.items():
            for name in names:
                path = args.lo_corpus / 'sw/qa/extras' / group / 'data' / name
                try:
                    doc, row = snapshot(path)
                    docs[name] = doc
                    row['corpus'] = group
                    lo_rows.append(row)
                except Exception as exc:
                    exceptions.append({'file': name, 'error': str(exc)})
    checks = verify_features(docs)
    result = {'summary': {'documents': len(rows), 'uncaught_exceptions': len(exceptions),
                          'fatal_documents': sum(any(e.startswith('ERR:') for e in r['errors']) for r in rows),
                          'new_fatal_documents': sum(r.get('new_fatal_error', False) for r in rows),
                          'lo_feature_documents': len(lo_rows),
                          'checks_passed': sum(c['passed'] for c in checks), 'checks': len(checks)},
              'checks': checks, 'documents': rows, 'lo_documents': lo_rows, 'exceptions': exceptions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False))
    for check in checks:
        if not check['passed']:
            print('FAIL %s %s: %r' % (check['file'], check['feature'], check['actual']))
    return 1 if exceptions or any(not c['passed'] for c in checks) else 0


if __name__ == '__main__':
    raise SystemExit(main())
