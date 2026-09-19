# HWPX CLI·배치 옵션 통합 검증

검증일: 2026-09-19. 실행 환경: Python 3.9.6, 현재 체크아웃의
`python -m dochan.cli` 및 `python -m pytest`.
구현 경로: `dochan/cli.py` → `dochan/batch.py`/`dochan/reader.py` → HWPX parser.
검증 진입점: `tests/test_hwpx_cli_options.py`.

## 옵션과 기본 호환성

`convert`와 `batch` 모두 다음 옵션을 받는다.

| CLI 옵션 | reader API | 동작 |
| --- | --- | --- |
| 생략 | 기존 호출 유지 | 이미지 로드, 변경 텍스트 모두 보존 |
| `--no-assets` | `include_assets=False` | HWPX 이미지 바이너리 로딩 생략, 참조·캡션 보존 |
| `--revision-mode preserve` | 기본값 유지 | 삽입·삭제 텍스트 보존 |
| `--revision-mode final` | `revision_mode="final"` | 삭제 텍스트 제외 |
| `--revision-mode original` | `revision_mode="original"` | 삽입 텍스트 제외 |

```bash
python -m dochan.cli convert document.hwpx --no-assets --revision-mode final --format json
python -m dochan.cli batch input/ output/ --revision-mode original --workers 2
```

배치 API의 추가 인자는 keyword-only다. 기존 positional 인자 순서는 유지한다.

```python
batch_convert("input/", "output/", output_format="json", max_workers=2,
              include_assets=False, revision_mode="final")
```

기본 배치는 reader에 새 키워드를 전달하지 않으므로 `Dochan(path)`만 받는
기존 mock도 동작한다. 기본값은 다른 형식에도 허용한다.
비기본 옵션은 reader가 실제 패키지 형식으로 검증한다. 따라서 `.pdf`로
이름을 바꾼 HWPX는 허용하고 `.hwpx`로 이름을 바꾼 DOCX는 거부한다.

## 실패와 출력 안전성

- 혼합 배치는 파일별로 처리한다. HWPX는 성공하고 비기본 옵션을 지원하지 않는
  다른 형식은 실패한다. CLI는 파일 경로와 `only for HWPX` 오류를 stderr에
  출력하고, 실패가 하나라도 있으면 종료코드 1을 반환한다.
- 실패 파일의 기존 출력은 보존하며 새 출력도 게시하지 않는다. 성공 파일은
  기존 원자적 게시 경로를 사용한다. 워커 1개와 실제 프로세스 워커 2개 모두 검증했다.
- 비기본 옵션도 배치의 검증된 private snapshot을 통해 파싱한다.
  원본과 출력이 같은 경로인 단일 변환은 여전히 실패하고 원본 바이트를 보존한다.
- `convert --no-assets --ocr`는 reader의 명시적 오류로 종료코드 1을 반환한다.
- 잘못된 CLI revision 값은 argparse 종료코드 2로 거부한다.
  배치 API는 빈 입력에서도 잘못된 값을 출력 디렉터리 생성 전에 거부한다.
- 기본값의 다른 형식 변환, 기존 배치 mock, 파일 충돌·심볼릭 링크·원자적 게시 등
  기존 `tests/test_batch_cli.py`의 안전성 검증도 통과했다.

## 공개 ChangeTrack: 실제 CLI의 독립 정답 대조

표본: `corpus/hwp-public/hwpx/hwpxlib-ChangeTrack.hwpx` (13,027 bytes).

- SHA-256: `05e6384795611406b29302cf62326b6d1f0a9399d2fbc201fcbe459aa730e356`
- 원본 XML `Contents/section0.xml` SHA-256:
  `d37c17279f99e142afdc60683a8025eb57da94324bc57ed100b4466a4724741a`
- 공개 출처·독립 gold: [revision-spec.md](revision-spec.md).
  이번 검증에서도 원본 XML의 Delete/Insert 마커, tail, tab을 직접 확인했다.

실제 subprocess로 `convert --format json --revision-mode MODE`를 실행했다.
아래 문자열은 JSON의 문단 `text`이며 `\t`는 탭이다.

| MODE | 독립 XML gold와 일치한 결과 | 종료코드 |
| --- | --- | ---: |
| preserve | `"변경 추적 \t인간은"` | 0 |
| final | `"변경 \t인간은"` | 0 |
| original | `"변경 추적 \t"` | 0 |

세 경우 모두 stderr가 비어 있었다. JSON에서 후행 공백·탭까지 정확히 비교했다.
Text/Markdown 출력은 기존 렌더러의 공백 정규화가 있으므로 이 정답 검증은
JSON 문단 텍스트를 사용한다. 서식 변경·미완결 범위·한글 UI 표시 전체의
정확성을 이 표본으로 확정하지 않는다.

## 실물 이미지: no-assets API·CLI 비교

표본: `corpus/hwp-public/hwpx/hwpxlib-SimplePicture.hwpx` (79,447 bytes).
SHA-256: `7ed3bdf89986fd88fdbcd92eaeac3f852aa6984fb1f7ddf4dd4f582afe20084c`.
`SOURCES.json`에 기록된 공개 원본은
[hwpxlib SimplePicture](https://raw.githubusercontent.com/neolord0/hwpxlib/main/testFile/reader_writer/SimplePicture.hwpx)다.
이번 비교 대상은 위 해시의 로컬 공개 코퍼스 바이트다.
`Apache-2.0`은 수집 인덱스의 표기다. [revision-spec.md](revision-spec.md)의
라이선스 직접 확인은 그 문서에 고정된 커밋의 저장소 선언에 한정되며,
이 표본의 개별 권리나 main URL의 현재 상태를 보증하지 않는다.

| 측정 항목 | 기본 API | `include_assets=False` |
| --- | ---: | ---: |
| 이미지 수 | 1 | 1 |
| `BinData/image1.jpg`의 `image_data` 바이트 | 23,560 | 0 |
| 파서 오류 수 | 0 | 0 |

`zipfile.ZipFile.read`·`open` 계측에서 no-assets의 `BinData/` 접근은 각각 0회였다.
기본 문서의 `image_data`만 비운 뒤 비교하면 no-assets 문서 모델과 완전히 같다.
CLI 인프로세스 호출에도 `BinData/` open 금지 가드를 적용했다.
JSON·Markdown·Text의 실제 CLI subprocess 출력은 no-assets API 출력과 모두 같다.
합성 이미지 문서로 배치 직렬 경로의 `BinData/` open 0회도 확인했다.
이미지 바이트를 직렬화하지 않는 출력의 동일성만으로 로딩 생략을 판단하지 않았다.

## 초기 TDD 기록과 재검증 명령

구현 전 신규 테스트: **57 failed, 3 passed**.
실패는 새 CLI 옵션 미인식, 배치 API keyword 미지원으로 확인했다.
그 뒤 옵션 전달을 구현하고 배치 실제 subprocess 종료코드·이미지 open 가드를 보강했다.

```bash
python -m pytest tests/test_hwpx_cli_options.py tests/test_batch_cli.py tests/test_hwpx_assets_option.py tests/test_hwpx_revisions.py -q --tb=short
```

초기 통합 당시: **230 passed in 3.93s**. 변경한 Python 3개 파일의 `ruff check`와
`git diff --check`도 통과했다. 공개 ChangeTrack 3모드와 실물 이미지 검증은
이 환경에서 skip 없이 실행했다. 코퍼스가 없는 환경에서는 해당 실물 테스트만
명시적으로 skip하며, skip을 실물 검증 통과로 간주하지 않는다.

현재 차트 통합과 revision 진단 보완까지 포함한 재실행 결과는
[implementation-progress.md](implementation-progress.md)의 검증 표에 기록한다.
초기 통합 시점의 테스트 수를 현재 수치로 사용하지 않는다.
