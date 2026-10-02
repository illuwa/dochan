"""dochan CLI — 문서를 터미널에서 변환

사용법:
  dochan convert 문서.hwp                    # → stdout에 Markdown
  dochan convert 문서.hwp -o output.md       # → 파일로 저장
  dochan convert 문서.hwp --format json      # → JSON 출력
  dochan convert 문서.hwpx --format text     # → Plain text
  dochan convert 문서.pdf --format text      # → PDF 텍스트 추출
  dochan batch input_dir/ output_dir/        # → 디렉토리 일괄 변환
  dochan info 문서.hwp                       # → 문서 메타데이터
"""

import argparse
import sys
import os
import re
import getpass


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse embeds positional values in quotes, even when an unknown
        # option precedes the subcommand. Never echo those values.
        if getattr(self, '_password_argument_present', False) or '--pass' in message:
            message = '암호는 --password-stdin 또는 DOCHAN_PASSWORD로 제공해야 합니다.'
        elif message.startswith('unrecognized arguments:'):
            options = re.findall(r'(?<!\S)--?[A-Za-z][A-Za-z-]*', message)
            message = 'unrecognized arguments: ' + (' '.join(options) or '[입력값 생략]')
        else:
            message = re.sub(r"'[^']*'|\"[^\"]*\"", '[입력값 생략]', message)
        super().error(message)


def _add_password_option(parser):
    parser.add_argument('--password-stdin', action='store_true',
                        help='표준 입력 첫 줄을 암호로 사용 (DOCHAN_PASSWORD 환경 변수보다 우선)')


def _password_options(args):
    password = os.environ.get('DOCHAN_PASSWORD') or None
    if getattr(args, 'password_stdin', False):
        try:
            if sys.stdin.isatty():
                password = getpass.getpass('문서 암호: ')
                if len(password) > 4096:
                    raise ValueError('암호 길이가 지원 범위를 벗어남')
                return {'password': password}
            line = sys.stdin.readline(4099)
        except Exception:
            raise ValueError('암호 표준 입력을 읽을 수 없음') from None
        if not line:
            raise ValueError('암호 표준 입력이 비어 있음')
        password = line[:-1] if line.endswith('\n') else line
        if password.endswith('\r'):
            password = password[:-1]
    if password is not None and len(password) > 4096:
        raise ValueError('암호 길이가 지원 범위를 벗어남')
    return {} if password is None else {'password': password}


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("must be a positive integer")
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _add_hwpx_options(parser):
    parser.add_argument(
        '--no-assets', action='store_true',
        help='HWPX 이미지 바이너리 로딩 생략 (참조·캡션 보존, OCR 병용 불가)',
    )
    parser.add_argument(
        '--revision-mode', choices=['preserve', 'final', 'original'],
        default='preserve',
        help='HWP·HWPX 변경 추적: preserve=모두 보존(기본), final=삭제 제외, original=삽입 제외',
    )


def _hwpx_options(args):
    # 기본 호출에는 새 키워드를 추가하지 않아 기존 리더 호출과 호환된다.
    options = {}
    if args.no_assets:
        options['include_assets'] = False
    if args.revision_mode != 'preserve':
        options['revision_mode'] = args.revision_mode
    return options


def main(argv=None):
    parser = _ArgumentParser(
        prog='dochan',
        description='dochan — 독한 native 문서 파서, AI/LLM 최적 Markdown 변환',
    )
    subparsers = parser.add_subparsers(dest='command', help='명령')

    # convert
    conv = subparsers.add_parser('convert', help='문서 → Markdown/JSON/Text 변환', allow_abbrev=False)
    conv.add_argument('file', help='문서 파일 경로')
    conv.add_argument('-o', '--output', default=None, help='출력 파일 경로 (기본: stdout)')
    conv.add_argument('-f', '--format', choices=['markdown', 'json', 'text'],
                      default='markdown', help='출력 형식 (기본: markdown)')
    conv.add_argument('--ocr', action='store_true', help='이미지 OCR 활성화')
    conv.add_argument('--pdf-text-tables', action='store_true', help='PDF 괘선 없는 표 복원')
    conv.add_argument('--images-dir', default=None,
                      help='문서 속 이미지 바이너리를 이 디렉터리에 <파일이름>-image-NNN.<확장자> 로 저장')
    _add_hwpx_options(conv)
    _add_password_option(conv)

    # batch
    bat = subparsers.add_parser('batch', help='디렉토리 일괄 변환', allow_abbrev=False,
                               description='문서마다 암호가 다르므로 batch는 암호 입력과 DOCHAN_PASSWORD를 지원하지 않습니다.')
    bat.add_argument('input_dir', help='입력 디렉토리')
    bat.add_argument('output_dir', help='출력 디렉토리')
    bat.add_argument('-f', '--format', choices=['markdown', 'json', 'text'],
                     default='markdown', help='출력 형식')
    bat.add_argument('-w', '--workers', type=_positive_int, default=4, help='병렬 워커 수')
    _add_hwpx_options(bat)

    # info
    inf = subparsers.add_parser('info', help='문서 메타데이터 출력', allow_abbrev=False)
    inf.add_argument('file', help='문서 파일 경로')
    _add_password_option(inf)

    tokens = list(sys.argv[1:] if argv is None else argv)
    # Reject inline password switches before argparse interprets their values as
    # subcommands; even quotes/newlines in a secret must never reach diagnostics.
    if any(token.startswith('-p') or
           (token.startswith('--pass') and token != '--password-stdin')
           for token in tokens):
        if 'batch' in tokens:
            parser.error('batch 는 암호를 받지 않습니다(문서마다 암호가 다르다). 암호 문서는 convert 로 변환하세요.')
        parser.error('암호는 --password-stdin 또는 DOCHAN_PASSWORD로 제공해야 합니다.')
    for command_parser in (parser, conv, bat, inf):
        command_parser._password_argument_present = '--password-stdin' in tokens
    args = parser.parse_args(tokens)

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
        options = _hwpx_options(args)
        options.update(_password_options(args))
        if args.pdf_text_tables:
            options['pdf_text_tables'] = True
        doc = Dochan(args.file, ocr=args.ocr, **options)

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

    if args.images_dir:
        try:
            saved = doc.save_images(args.images_dir)
        except Exception as exc:
            print(f"에러: 이미지 저장 실패: {exc}", file=sys.stderr)
            return 1
        print(f"이미지 {len(saved)}개 저장: {args.images_dir}", file=sys.stderr)

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
            **_hwpx_options(args),
        )
    except Exception as exc:
        print(f"에러: 배치 변환 실패: {exc}", file=sys.stderr)
        return 1
    print(f"\n완료: {summary.success}/{summary.total} 성공 ({summary.success_rate:.1f}%)")
    for result in summary.results:
        label = '경고' if result.success else '에러'
        for error in result.errors:
            print(f"{label}: {result.file_path}: {error}", file=sys.stderr)
    return 1 if summary.failed else 0


def _cmd_info(args):
    from .batch import _is_fatal_parser_error
    from .reader import Dochan
    import json

    if not os.path.exists(args.file):
        print(f"에러: 파일을 찾을 수 없습니다: {args.file}", file=sys.stderr)
        return 1

    try:
        doc = Dochan(args.file, **_password_options(args))
    except Exception as exc:
        print(f"에러: 문서 정보 확인 실패: {exc}", file=sys.stderr)
        return 1
    info = doc.metadata
    info['file'] = args.file
    extension_format = os.path.splitext(args.file)[1].lower().lstrip('.')
    supported_formats = {
        'hwp', 'hwpx', 'doc', 'ppt', 'xls', 'docx', 'pptx', 'xlsx', 'pdf',
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
