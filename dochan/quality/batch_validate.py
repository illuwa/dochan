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
import hashlib
import tempfile
from contextlib import contextmanager

from ..batch import _atomic_write_text
from .cross_validator import (
    MAX_REFERENCE_PDF_BYTES,
    CrossValidationReport,
    CrossValidator,
    SourceResult,
)


_HASH_CHUNK_SIZE = 1024 * 1024


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        while chunk := source.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _report_to_dict(report) -> dict:
    return {
        'file_name': report.file_name,
        'overall_score': report.overall_score,
        'verdict': report.verdict,
        'validation_available': report.validation_available,
        'sources': {
            name: {
                'char_count': source.char_count,
                'table_count': source.table_count,
                'image_count': source.image_count,
                'error': source.error,
                'warnings': list(source.warnings),
            }
            for name, source in report.sources.items()
        },
        'comparisons': [
            {
                'a': comparison.source_a,
                'b': comparison.source_b,
                'similarity': comparison.bigram_similarity,
                'coverage': comparison.sentence_coverage,
                'word_coverage': comparison.word_coverage,
                'length_ratio': comparison.length_ratio,
                'available_metrics': list(comparison.available_metrics),
                'keyword_matches': comparison.keyword_matches,
                'keyword_total': comparison.keyword_total,
                'keywords': f"{comparison.keyword_matches}/{comparison.keyword_total}",
            }
            for comparison in report.comparisons
        ],
        'missing_count': len(report.missing_in_hwp),
        'missing_in_hwp': list(report.missing_in_hwp),
    }


def _score_summary(reports) -> dict:
    """Aggregate only reports backed by a valid dochan/reference comparison."""
    available = [report for report in reports if report.validation_available]
    return {
        'available': len(available),
        'total': len(reports),
        'average': (
            sum(report.overall_score for report in available) / len(available)
            if available
            else None
        ),
    }


def find_pairs(pairs_dir: str) -> list:
    """디렉토리에서 HWP+HWPX+PDF 세트 찾기 (macOS NFD 유니코드 대응)"""
    import unicodedata
    pairs = []
    files = os.listdir(pairs_dir)

    hwp_files = {}
    hwpx_files = {}
    pdf_files = {}

    def add_file(collection, key, full_path):
        if key in collection and collection[key] != full_path:
            raise ValueError(
                "Unicode-normalized filename collision: "
                f"{collection[key]} and {full_path}"
            )
        collection[key] = full_path

    for f in files:
        name, ext = os.path.splitext(f)
        ext = ext.lower()
        full = os.path.join(pairs_dir, f)
        key = unicodedata.normalize('NFC', name)
        if ext == '.hwp':
            add_file(hwp_files, key, full)
        elif ext == '.hwpx':
            add_file(hwpx_files, key, full)
        elif ext == '.pdf':
            add_file(pdf_files, key, full)

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


@contextmanager
def _temporary_environment(updates: dict):
    previous = {name: os.environ.get(name) for name in updates}
    os.environ.update(updates)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def run_odl(pdf_path: str, output_dir: str) -> str:
    """Open Dataloader로 PDF → Markdown 변환"""
    try:
        input_size = os.path.getsize(pdf_path)
        if input_size > MAX_REFERENCE_PDF_BYTES:
            raise ValueError(
                "PDF input exceeds the "
                f"{MAX_REFERENCE_PDF_BYTES}-byte limit"
            )
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

        base = os.path.splitext(os.path.basename(pdf_path))[0]
        source_digest = _file_sha256(pdf_path)[:16]
        os.makedirs(output_dir, exist_ok=True)
        run_output_dir = tempfile.mkdtemp(
            prefix=f"{base}-{source_digest}-",
            dir=output_dir,
        )

        from opendataloader_pdf import convert
        environment = {}
        if env.get('JAVA_HOME') != os.environ.get('JAVA_HOME'):
            environment['JAVA_HOME'] = env['JAVA_HOME']
        if env.get('PATH') != os.environ.get('PATH'):
            environment['PATH'] = env['PATH']
        with _temporary_environment(environment):
            convert(
                input_path=pdf_path,
                output_dir=run_output_dir,
                format='markdown',
                quiet=True,
            )

        # 출력 파일 찾기
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        md_path = os.path.join(run_output_dir, f"{base}.md")
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

    for source_key in ('hwp', 'hwpx'):
        source_path = pair.get(source_key)
        if not source_path:
            continue

        try:
            report = CrossValidator().validate(
                hwpx_path=source_path,
                pdf_path=pair['pdf'],
                odl_output_path=odl_path if odl_path else None,
            )
            report.file_name = os.path.basename(source_path)
        except Exception as exc:
            # Preserve one report per requested document so callers can count
            # failures without losing a successful sibling HWP/HWPX result.
            report = CrossValidationReport(
                file_name=os.path.basename(source_path),
                sources={
                    'dochan': SourceResult(
                        name='dochan',
                        error=str(exc),
                    ),
                },
                verdict="검증 불가 — 검증 중 예외 발생",
                validation_available=False,
            )
        reports.append(report)

    return reports


def _collect_reports(pairs: list, odl_dir: str) -> tuple:
    reports = []
    failure_count = 0

    for i, pair in enumerate(pairs, 1):
        print(f"[{i}/{len(pairs)}] {pair['name'][:50]}")
        expected_count = sum(key in pair for key in ('hwp', 'hwpx'))
        try:
            pair_reports = validate_pair(pair, odl_dir)
        except Exception as exc:
            # A pair-level failure means none of its requested validations can
            # be trusted. Continue so later pairs still produce evidence.
            failure_count += max(expected_count, 1)
            print(f"  에러: {exc}")
            continue

        reports.extend(pair_reports)
        failure_count += max(expected_count - len(pair_reports), 0)
        for report in pair_reports:
            fmt = report.file_name[-5:].upper()
            if report.validation_available:
                print(f"  {fmt}: {report.overall_score:.1f}")
            else:
                failure_count += 1
                print(f"  {fmt}: 검증 불가")

    return reports, failure_count


def _write_json_report(
    output_path: str,
    data: list,
    protected_paths=(),
) -> None:
    """Serialize fully before atomically publishing within the output directory."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    absolute_output = os.path.abspath(output_path)
    allowed_root = os.path.dirname(absolute_output)
    _atomic_write_text(
        absolute_output,
        payload,
        allowed_root=allowed_root,
        protected_paths=protected_paths,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='3중 교차 검증')
    parser.add_argument('--pairs-dir', required=True, help='HWP+PDF 쌍이 있는 디렉토리')
    parser.add_argument('--output', default=None, help='JSON 리포트 출력 경로')
    parser.add_argument('--odl-dir', default=None, help='ODL 출력 디렉토리 (기본: 임시)')
    args = parser.parse_args(argv)

    try:
        pairs = find_pairs(args.pairs_dir)
    except (OSError, ValueError) as exc:
        print(f"입력 쌍 탐색 실패: {exc}", file=sys.stderr)
        return 1
    if not pairs:
        print("HWP+PDF 쌍을 찾을 수 없습니다.")
        print("디렉토리에 같은 이름의 .hwpx/.hwp + .pdf 파일을 넣어주세요.")
        return 1

    print(f"발견된 쌍: {len(pairs)}개")
    for p in pairs:
        print(f"  · {p['name']}")
    print()

    if args.odl_dir:
        os.makedirs(args.odl_dir, exist_ok=True)
        reports, failure_count = _collect_reports(pairs, args.odl_dir)
    else:
        with tempfile.TemporaryDirectory(prefix='hwp_odl_') as odl_dir:
            reports, failure_count = _collect_reports(pairs, odl_dir)

    # 전체 요약
    if reports:
        scores = _score_summary(reports)
        print("=" * 60)
        if scores['average'] is None:
            print("전체 평균 점수: 검증 불가")
        else:
            print(f"전체 평균 점수: {scores['average']:.1f}/100")
        print(f"검증 가능 파일 수: {scores['available']}/{scores['total']}개")
        for r in reports:
            score = f"{r.overall_score:5.1f}" if r.validation_available else "검증 불가"
            print(f"  {score} | {r.file_name}")
        print("=" * 60)
    print(f"검증 실패 파일 수: {failure_count}개")

    # JSON 저장
    if args.output:
        data = [_report_to_dict(report) for report in reports]
        protected_paths = [
            path
            for pair in pairs
            for key, path in pair.items()
            if key in {'hwp', 'hwpx', 'pdf'}
        ]
        try:
            _write_json_report(
                args.output,
                data,
                protected_paths=protected_paths,
            )
        except Exception as exc:
            print(f"JSON 리포트 저장 실패: {exc}", file=sys.stderr)
            return 1
        print(f"\nJSON 리포트 저장: {args.output}")

    return 1 if failure_count else 0


if __name__ == '__main__':
    raise SystemExit(main())
