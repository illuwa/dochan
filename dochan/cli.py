"""dochan CLI — HWP/HWPX 문서를 터미널에서 변환

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


def main():
    parser = argparse.ArgumentParser(
        prog='dochan',
        description='dochan — 독한 HWP/HWPX 파서, AI/LLM 최적 Markdown 변환',
    )
    subparsers = parser.add_subparsers(dest='command', help='명령')

    # convert
    conv = subparsers.add_parser('convert', help='HWP/HWPX → Markdown/JSON/Text 변환')
    conv.add_argument('file', help='HWP 또는 HWPX 파일 경로')
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
    bat.add_argument('-w', '--workers', type=int, default=4, help='병렬 워커 수')

    # info
    inf = subparsers.add_parser('info', help='문서 메타데이터 출력')
    inf.add_argument('file', help='HWP 또는 HWPX 파일 경로')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == 'convert':
        _cmd_convert(args)
    elif args.command == 'batch':
        _cmd_batch(args)
    elif args.command == 'info':
        _cmd_info(args)


def _cmd_convert(args):
    from .reader import Dochan

    if not os.path.exists(args.file):
        print(f"에러: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
        sys.exit(1)

    doc = Dochan(args.file, ocr=args.ocr)

    if args.format == 'json':
        content = doc.to_json()
    elif args.format == 'text':
        content = doc.to_plain_text()
    else:
        content = doc.to_markdown()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"저장 완료: {args.output}", file=sys.stderr)
    else:
        print(content)

    if doc.errors:
        for err in doc.errors:
            print(f"경고: {err}", file=sys.stderr)


def _cmd_batch(args):
    from .batch import batch_convert

    if not os.path.isdir(args.input_dir):
        print(f"에러: 디렉토리를 찾을 수 없습니다: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    summary = batch_convert(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        output_format=args.format,
        max_workers=args.workers,
    )
    print(f"\n완료: {summary.success}/{summary.total} 성공 ({summary.success_rate:.1f}%)")


def _cmd_info(args):
    from .reader import Dochan
    import json

    if not os.path.exists(args.file):
        print(f"에러: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
        sys.exit(1)

    doc = Dochan(args.file)
    info = doc.metadata
    info['file'] = args.file
    info['format'] = 'hwpx' if args.file.lower().endswith('.hwpx') else 'hwp'
    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
