"""
quality/batch_validate.py — 배치 3중 교차 검증 CLI

사용법:
  python3 -m dochan.quality.batch_validate --pairs-dir /path/to/pairs

pairs 디렉토리 구조:
  pairs/
    문서1.hwpx (또는 .hwp)
    문서1.pdf
    문서2.hwpx
    문서2.pdf
    ...

각 HWP+PDF 쌍에 대해:
  1. 우리 파서로 HWP/HWPX 추출
  2. pdfplumber로 PDF 추출
  3. Open Dataloader로 PDF → Markdown 추출
  4. 3중 비교 리포트 생성
"""

import os
import sys
import json
import argparse
import subprocess
import tempfile
from pathlib import Path
from dataclasses import asdict

from .cross_validator import CrossValidator, CrossValidationReport


def find_pairs(pairs_dir: str) -> list:
    """디렉토리에서 HWP+HWPX+PDF 세트 찾기 (macOS NFD 유니코드 대응)"""
    import unicodedata
    pairs = []
    files = os.listdir(pairs_dir)

    hwp_files = {}
    hwpx_files = {}
    pdf_files = {}

    for f in files:
        name, ext = os.path.splitext(f)
        ext = ext.lower()
        full = os.path.join(pairs_dir, f)
        key = unicodedata.normalize('NFC', name)
        if ext == '.hwp':
            hwp_files[key] = full
        elif ext == '.hwpx':
            hwpx_files[key] = full
        elif ext == '.pdf':
            pdf_files[key] = full

    # PDF가 있는 모든 이름에 대해 세트 구성
    all_names = set(pdf_files.keys())
    for name in sorted(all_names):
        entry = {'name': name, 'pdf': pdf_files[name]}
        if name in hwp_files:
            entry['hwp'] = hwp_files[name]
        if name in hwpx_files:
            entry['hwpx'] = hwpx_files[name]
        if 'hwp' in entry or 'hwpx' in entry:
            pairs.append(entry)

    return pairs


def run_odl(pdf_path: str, output_dir: str) -> str:
    """Open Dataloader로 PDF → Markdown 변환"""
    try:
        env = os.environ.copy()
        # Java 경로 설정 (macOS Homebrew)
        java_candidates = [
            '/opt/homebrew/opt/openjdk@17',
            '/opt/homebrew/opt/openjdk',
            '/usr/local/opt/openjdk@17',
            '/Library/Java/JavaVirtualMachines',
        ]
        for java_home in java_candidates:
            if os.path.exists(java_home):
                env['JAVA_HOME'] = java_home
                env['PATH'] = f"{java_home}/bin:{env.get('PATH', '')}"
                break

        # 이미 변환된 파일이 있으면 재사용
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        existing = os.path.join(output_dir, f"{base}.md")
        if os.path.exists(existing):
            return existing

        from opendataloader_pdf import convert
        convert(
            input_path=pdf_path,
            output_dir=output_dir,
            format='markdown',
            quiet=True,
        )

        # 출력 파일 찾기
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        md_path = os.path.join(output_dir, f"{base}.md")
        if os.path.exists(md_path):
            return md_path
    except ImportError:
        # ODL 미설치 — pdfplumber만으로 진행
        pass
    except Exception as e:
        print(f"  ODL 실패: {e}", file=sys.stderr)

    return ""


def validate_pair(pair: dict, odl_dir: str) -> list:
    """단일 세트 검증 — HWP와 HWPX 각각 별도 리포트"""
    reports = []

    # ODL 실행
    odl_path = run_odl(pair['pdf'], odl_dir)

    # HWP 바이너리 검증
    if 'hwp' in pair:
        validator = CrossValidator()
        report = validator.validate(
            hwpx_path=pair['hwp'],
            pdf_path=pair['pdf'],
            odl_output_path=odl_path if odl_path else None,
        )
        report.file_name = os.path.basename(pair['hwp'])
        reports.append(report)

    # HWPX 검증
    if 'hwpx' in pair:
        validator = CrossValidator()
        report = validator.validate(
            hwpx_path=pair['hwpx'],
            pdf_path=pair['pdf'],
            odl_output_path=odl_path if odl_path else None,
        )
        report.file_name = os.path.basename(pair['hwpx'])
        reports.append(report)

    return reports


def main():
    parser = argparse.ArgumentParser(description='3중 교차 검증')
    parser.add_argument('--pairs-dir', required=True, help='HWP+PDF 쌍이 있는 디렉토리')
    parser.add_argument('--output', default=None, help='JSON 리포트 출력 경로')
    parser.add_argument('--odl-dir', default=None, help='ODL 출력 디렉토리 (기본: 임시)')
    args = parser.parse_args()

    pairs = find_pairs(args.pairs_dir)
    if not pairs:
        print("HWP+PDF 쌍을 찾을 수 없습니다.")
        print("디렉토리에 같은 이름의 .hwpx/.hwp + .pdf 파일을 넣어주세요.")
        sys.exit(1)

    print(f"발견된 쌍: {len(pairs)}개")
    for p in pairs:
        print(f"  · {p['name']}")
    print()

    odl_dir = args.odl_dir or tempfile.mkdtemp(prefix='hwp_odl_')
    os.makedirs(odl_dir, exist_ok=True)

    reports = []
    total_score = 0

    for i, pair in enumerate(pairs, 1):
        print(f"[{i}/{len(pairs)}] {pair['name'][:50]}")
        try:
            pair_reports = validate_pair(pair, odl_dir)
            for report in pair_reports:
                reports.append(report)
                total_score += report.overall_score
                fmt = report.file_name[-5:].upper()
                print(f"  {fmt}: {report.overall_score:.1f}")
        except Exception as e:
            print(f"  에러: {e}")

    # 전체 요약
    if reports:
        avg = total_score / len(reports)
        print("=" * 60)
        print(f"전체 평균 점수: {avg:.1f}/100")
        print(f"검증 파일 수: {len(reports)}개")
        for r in reports:
            print(f"  {r.overall_score:5.1f} | {r.file_name}")
        print("=" * 60)

    # JSON 저장
    if args.output:
        data = []
        for r in reports:
            d = {
                'file_name': r.file_name,
                'overall_score': r.overall_score,
                'verdict': r.verdict,
                'sources': {k: {'char_count': v.char_count, 'table_count': v.table_count,
                                'image_count': v.image_count, 'error': v.error}
                           for k, v in r.sources.items()},
                'comparisons': [
                    {'a': c.source_a, 'b': c.source_b,
                     'similarity': c.bigram_similarity,
                     'coverage': c.sentence_coverage,
                     'word_coverage': getattr(c, 'word_coverage', 0),
                     'keywords': f"{c.keyword_matches}/{c.keyword_total}"}
                    for c in r.comparisons
                ],
                'missing_count': len(r.missing_in_hwp),
            }
            data.append(d)

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 리포트 저장: {args.output}")


if __name__ == '__main__':
    main()
