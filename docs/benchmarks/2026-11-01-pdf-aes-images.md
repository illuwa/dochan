# PDF AES 가속과 이미지 추출 계약 (2026-11-01)

## 변경 범위

`dochan/utils/_caes.c`는 FIPS-197의 바이트 상태, 키 확장, SubBytes,
ShiftRows, MixColumns 및 SP 800-38A의 ECB/CBC를 직접 구현한다.
새 의존성은 없다. 제한 API는 `0x03090000`이며 표 참조 구현이므로
상수 시간 암호 라이브러리를 표방하지 않는다.

`aes.py`는 원래 Python 구현을 독립 거울로 보존한다. C 경로는 검증된
bytes 입력만 처리하고, 그 밖의 객체와 잘못된 입력은 원래 Python 경로로
돌려서 반환 타입 및 예외를 유지한다. 블록 연산은 128/192/256비트,
기존 공개 CBC는 128/256비트만 허용한다(192비트 CBC 요청은 기존처럼 빈 bytes).
ECB-128의 잘못된 키/블록 길이는 기존 ValueError를 유지한다.

`DOCHAN_BUILD_ACCEL=1`일 때만 빌드하고 `DOCHAN_DISABLE_ACCEL=1`이면
Python을 선택한다. ImportError만 폴백하며 `AES_BACKEND`로 실제 선택을
표시한다. setup, sdist manifest, 설치 wheel 검증에도 `_caes`를 연결했다.
README 지원 표와 CHANGELOG는 변경하지 않았다.

## 이미지 지연화를 채택하지 않은 근거

| 소비 경로 | 이미지 바이트 의존성 |
|---|---|
| PDF `_page_images` | 추출 바이트가 비어 있으면 Image 요소 자체를 만들지 않음 |
| PDF 스캔 판정 | Image 생성 성공 여부가 두 종류의 스캔 진단을 결정 |
| PDF asset 등록 | 바이트 존재 여부와 확장자로 asset, MIME, 파일명 결정 |
| Markdown | 바이트 truthiness가 자리표시 출력을 결정 |
| 일반 텍스트 | Image 요소 존재 여부가 `[이미지]` 출력을 결정 |
| JSON 및 to_dict | 바이트는 미포함이지만 이미지 요소, 크기, OCR 텍스트와 assets를 포함 |
| OCR | 실제 이미지 바이트를 디코딩 |
| save_images | 바이트 해시와 서명으로 중복 제거 및 확장자 결정 |

`decode_image_bytes`는 문서 본문과 predictor 예산을 공유한다. 디코딩을
뒤로 미루면 경고 순서나 후속 본문 결과도 달라질 수 있다. PNG 저장만
미루어도 Pillow 저장 실패 시 기존에는 없던 Image 요소가 이미 출력된다.
Pillow가 없는 경우 raw 이미지 디코딩 자체를 하지 않고 JPEG 원본은 유지한다.

`tests/test_pdf_image_optimization.py`는 PNG 저장 실패를 주입했을 때
Markdown/JSON/plain text/to_dict/assets/스캔 경고가 모두 달라짐을 확인한다.
별도 테스트는 Pillow 부재 시 raw decode 콜백을 호출하지 않는 계약을 고정한다.
따라서 이미지 런타임 변경은 하지 않았다.

필터 0 + zlib PNG 대안도 미채택했다. 4×3 RGB `(200,30,30)`의 픽셀은 같지만
Pillow는 76 bytes, SHA-256 `dc1534c349a4fb97d56ed5f764a468b282b6c49b651d652906c34aa2624a3bb6`,
대안은 73 bytes, `949e22933c7b68cf5e247bb85d75e71af8d008d9446101fe6a3768e66744bfb1`로
바이트가 달랐다.

## 검증 방법

- TDD: 기존 구현에서 새 AES 계약 테스트 13 실패를 확인한 뒤 구현했다.
  최종 검토에서 비정상 5-byte 라운드 워드의 예외/결과 불일치 3건도 재현한 뒤,
  정상 bytes 키 확장에서 만든 스케줄만 C 블록 경로에 허용했다.
- FIPS-197 부록 C 및 SP 800-38A F.1/F.2 기지 답안, 128/192/256비트 블록,
  CBC 블록 경계/빈 입력/잘못된 길이/버퍼 폴백/로더 예외를 검증했다.
- 공개 pdf.js 암호 PDF 26개 중 16개에서 AES 1,733회 호출을 수집했다.
  고유 입력 1,024개와 변형 100,000건, 블록 비교 200,000건에서 차이 0.
  수집은 호출당 64KiB 이하, 고유 입력 최대 1,024개로 제한했다(초과 크기 호출 0).
  입력의 키와 문서 바이트는 메모리에만 보관하고 결과에는 집계만 기록한다.
- 같은 검증을 ASan+UBSan 계측 확장에서 반복했다. 직접 C 경계 호출 335건
  포함, 진단 0. 누수 검사는 제외(`detect_leaks=0`).
- 최종 C SHA-256:
  `a4be9ca30ae724488207c7dc076b333038aae39a1b9ee9f66610cc1d3dde7b06`.
- 설치된 Tika 코퍼스에는 PDF가 0개이므로 Tika PDF 검증을 주장하지 않는다.

재현(저장소 루트에서 `BASE`는 기준 소스, `PUBLIC_LIST`는 공개 암호 PDF 목록):

```sh
DOCHAN_BUILD_ACCEL=1 /usr/bin/python3 setup.py build_ext --inplace --force
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider
DOCHAN_DISABLE_ACCEL=1 /usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider
/usr/bin/python3 -m ruff check dochan scripts tests setup.py
/usr/bin/python3 -m scripts.probe_caes_fuzz --reference-source "$BASE" \
  --paths "$PUBLIC_LIST" --count 100000 --output fuzz.json
```

엄격 컴파일과 sanitizer 재현(헤더/런타임 경로는 사용 환경에서 지정):

```sh
clang -std=c99 -Wall -Wextra -Wpedantic -Werror -fsyntax-only \
  -I"$PY39_HEADERS" dochan/utils/_caes.c
mkdir -p .codex-work/caes-sanitize
clang -std=c99 -O1 -g -ffp-contract=off \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  -bundle -undefined dynamic_lookup -I"$PY39_HEADERS" \
  dochan/utils/_caes.c -o .codex-work/caes-sanitize/_caes.abi3.so
DYLD_INSERT_LIBRARIES="$ASAN_RUNTIME" \
  ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "$PY312_REAL" -m scripts.probe_caes_fuzz \
  --paths "$PUBLIC_LIST" --reference-source "$BASE" \
  --extension .codex-work/caes-sanitize/_caes.abi3.so --count 100000
```

`PY39_HEADERS`는 Xcode 3.9 Headers, `ASAN_RUNTIME`은
`clang -print-file-name=libclang_rt.asan_osx_dynamic.dylib` 결과,
`PY312_REAL`은 벤치마크 venv의 `sys._base_executable`이다.
계측 바이너리와 dSYM은 검증 후 삭제했다.

## 실측 결과

아래는 비정상 라운드 키 폴백 수정까지 포함한 **최종 소스**로 재실행한 결과다.
기준과 시작 HEAD는 `4ad1a29d8cb9e8a411c21461153cdaee0e59c30c`이다.
기준 체크아웃은 수정하지 않았다. 시간은 canonical
`scripts.probe_output_speed.measure_file`의 parse + Markdown + JSON + text
합계이며, 전·후·후·전·전·후 순서로 실행한 각 3회 중앙값이다.

| Python | 묶음 | 문서 수 | 전 중앙값(초) | 후 중앙값(초) | 시간 감소율 |
|---|---|---:|---:|---:|---:|
| 3.9 | 고정 표본 | 300 | 6.211781 | 5.964845 | +3.98% |
| 3.9 | 암호 PDF | 26 | 4.054481 | 0.272522 | +93.28% |
| 3.9 | 이미지 다수 PDF | 30 | 4.803132 | 4.756989 | +0.96% |
| 3.12 | 고정 표본 | 300 | 4.568497 | 4.460450 | +2.37% |
| 3.12 | 암호 PDF | 26 | 3.045309 | 0.196609 | +93.54% |
| 3.12 | 이미지 다수 PDF | 30 | 3.226778 | 3.216741 | +0.31% |

음수 감소율은 느려졌다는 뜻이다. 이미지 런타임 변경이 없으므로 이미지 묶음의
시간 변화를 최적화 효과라고 주장하지 않는다. 암호 묶음은 공개 pdf.js
`/Encrypt` 표본 26개, 이미지 묶음은 공개 전수 중 5MB 미만 PDF에서
`/Subtype /Image` 표식 수가 가장 많은 30개(문서별 124–1,603개)다.
표식 수는 실제 렌더된 이미지 수와 같은 값이라고 주장하지 않는다.

원시 3회 합계:

| Python/묶음 | 전 3회(초) | 후 3회(초) |
|---|---|---|
| 39/sample | 6.183080, 6.215467, 6.211781 | 6.015718, 5.954017, 5.964845 |
| 39/encrypted | 4.031607, 4.065705, 4.054481 | 0.272522, 0.272496, 0.277025 |
| 39/images | 4.810878, 4.803132, 4.735607 | 4.788175, 4.722467, 4.756989 |
| 312/sample | 4.563262, 4.828836, 4.568497 | 4.371685, 4.460450, 4.469502 |
| 312/encrypted | 3.072775, 3.045309, 2.960735 | 0.196194, 0.197237, 0.196609 |
| 312/images | 3.250764, 3.222715, 3.226778 | 3.229843, 3.216741, 3.216689 |

### 정확성과 회귀 게이트

- 공개 PDF 2,281개(pdf.js, press-pairs 전체 묶음, LibreOffice): Markdown·JSON·
  일반 텍스트·진단 SHA-256이 기준 대비 가속 켬/끔 모두 차이 0, 파싱 실패 0.
- 실패 수는 probe 예외·시간 초과 기준이며, 문서 진단은 별도 해시로 대조했다.
- 두 Python × 세 묶음 × 여섯 실행의 36회 출력 대조도 모두 차이 0.
- 전수 파일별 2회 최솟값: 1.2배 이상 느려진 파일 0/2,281,
  최대 후/전 비율 1.112300. 가속 켬의 총 단계 시간 기준.
- 전체 테스트 켬: 7008 passed, 39 skipped, 14 xfailed in 101.17s (0:01:41)
- 전체 테스트 끔: 6998 passed, 49 skipped, 14 xfailed in 107.29s (0:01:47)
- ruff, 제한 API 3.9 헤더 strict compile, ASan+UBSan 통과.
- 로컬 cp39-abi3 wheel에 `_caes.abi3.so` 포함 확인, C 소스는 wheel에서 제외.
  네 플랫폼 배포 전체 검증이나 게시를 수행한 것은 아니다.

10ms 미만 회귀 의심 파일도 0개이므로 20회 재검사 대상이 없다.

### 판정과 한계

**합류 보류.** 출력 동일성과 AES 가속은 확인했으나 다른 부하 없는 성능 조건을
인증하지 못했다. 자체 테스트/퍼징 종료 후 측정은 순차 실행했지만 호스트의
다른 작업은 배제하지 못했고 프로세스별 확인은 sandbox에서 불가했다.
따라서 위 시간은 이 환경의 잠정 실측이며 무부하 재측정이 합류 전 필요하다.
이미지 지연화와 대체 PNG는 출력 계약 때문에 채택하지 않았다.
300개 표본의 −5% 목표도 3.9, 3.12에서 미달했다.

원자료는 `.codex-work/`의 `summary.json`, `file-gate.json`, `quiet-*.json`,
`time-*.json`, `hash-*-compare.log`, `aes-fuzz-final.json`,
`aes-sanitizer-final.json`, `aes-validation-sources.json`, `test-*-final.log`이다.
시간 측정 harness는 `probe.py`와 `timing_suite.py`다. 경계 수정 전 증거는
`before-boundary-fix/`로 격리했으며 최종 수치에 섞지 않았다.
