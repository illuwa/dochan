"""dochan CLI — 문서를 터미널에서 변환

사용법:
  dochan convert 문서.hwp                    # → stdout에 Markdown
  dochan convert 문서.hwp -o output.md       # → 파일로 저장
  dochan convert 문서.hwp --format json      # → JSON 출력
  dochan convert 문서.hwpx --format text     # → Plain text
  dochan batch input_dir/ output_dir/        # → 디렉토리 일괄 변환
  dochan info 문서.hwp                       # → 문서 메타데이터
"""

import argparse
import sys
import os


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("must be a positive integer")
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='dochan',
        description='dochan — 독한 native 문서 파서, AI/LLM 최적 Markdown 변환',
    )
    subparsers = parser.add_subparsers(dest='command', help='명령')

    # convert
    conv = subparsers.add_parser('convert', help='문서 → Markdown/JSON/Text 변환')
    conv.add_argument('file', help='문서 파일 경로')
    conv.add_argument('-o', '--output', default=None, help='출력 파일 경로 (기본: stdout)')
    conv.add_argument('-f', '--format', choices=['markdown', 'json', 'text'],
                      default='markdown', help='출력 형식 (기본: markdown)')
    conv.add_argument('--ocr', action='store_true', help='이미지 OCR 활성화')

    # batch
    bat = subparsers.add_parser('batch', help='디렉토리 일괄 변환')
    bat.add_argument('input_dir', help='입력 디렉토리')
    bat.add_argument('output_dir', help='출력 디렉토리')
    bat.add_argument('-f', '--format', choices=['markdown', 'json', 'text'],
                     default='markdown', help='출력 형식')
    bat.add_argument('-w', '--workers', type=_positive_int, default=4, help='병렬 워커 수')

    # info
    inf = subparsers.add_parser('info', help='문서 메타데이터 출력')
    inf.add_argument('file', help='문서 파일 경로')

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == 'convert':
        return _cmd_convert(args)
    if args.command == 'batch':
        return _cmd_batch(args)
    if args.command == 'info':
        return _cmd_info(args)
    return 2


def _cmd_convert(args):
    from .batch import _atomic_write_text, _is_fatal_parser_error
    from .reader import Dochan

    if not os.path.exists(args.file):
        print(f"에러: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
        return 1

    try:
        doc = Dochan(args.file, ocr=args.ocr)

        if args.format == 'json':
            content = doc.to_json()
        elif args.format == 'text':
            content = doc.to_plain_text()
        else:
            content = doc.to_markdown()
    except Exception as exc:
        print(f"에러: 변환 실패: {exc}", file=sys.stderr)
        return 1

    fatal_errors = [
        error for error in doc.errors if _is_fatal_parser_error(error)
    ]
    if fatal_errors:
        for error in doc.errors:
            label = '에러' if _is_fatal_parser_error(error) else '경고'
            print(f"{label}: {error}", file=sys.stderr)
        return 1

    if args.output:
        try:
            _atomic_write_text(
                args.output,
                content,
                protected_paths=(args.file,),
            )
        except Exception as exc:
            print(f"에러: 출력 게시 실패: {exc}", file=sys.stderr)
            return 1
        print(f"저장 완료: {args.output}", file=sys.stderr)
    else:
        print(content)

    if doc.errors:
        for err in doc.errors:
            print(f"경고: {err}", file=sys.stderr)
    return 0


def _cmd_batch(args):
    from .batch import batch_convert

    if not os.path.isdir(args.input_dir):
        print(f"에러: 디렉토리를 찾을 수 없습니다: {args.input_dir}", file=sys.stderr)
        return 1

    try:
        summary = batch_convert(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            output_format=args.format,
            max_workers=args.workers,
        )
    except Exception as exc:
        print(f"에러: 배치 변환 실패: {exc}", file=sys.stderr)
        return 1
    print(f"\n완료: {summary.success}/{summary.total} 성공 ({summary.success_rate:.1f}%)")
    for result in summary.results:
        if result.success and result.errors:
            for warning in result.errors:
                print(f"경고: {result.file_path}: {warning}", file=sys.stderr)
    return 1 if summary.failed else 0


def _cmd_info(args):
    from .batch import _is_fatal_parser_error
    from .reader import Dochan
    import json

    if not os.path.exists(args.file):
        print(f"에러: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
        return 1

    doc = Dochan(args.file)
    info = doc.metadata
    info['file'] = args.file
    extension_format = os.path.splitext(args.file)[1].lower().lstrip('.')
    supported_formats = {
        'hwp', 'hwpx', 'doc', 'ppt', 'xls', 'docx', 'pptx', 'xlsx',
    }
    info['format'] = info.get('source_format') or (
        extension_format if extension_format in supported_formats else 'unknown'
    )
    print(json.dumps(info, ensure_ascii=False, indent=2))
    fatal_errors = [error for error in doc.errors if _is_fatal_parser_error(error)]
    if fatal_errors:
        for error in fatal_errors:
            print(f"에러: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
