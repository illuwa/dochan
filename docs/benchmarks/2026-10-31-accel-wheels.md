# 가속 휠 릴리스 검증 (2026-10-31)

## 변경 범위

기준 커밋 `c1a6e0bb0c11abccb902c328ed7a794ae5d35c22`의 릴리스는 순수 Python 휠만 게시하고,
Linux 소스 가속 테스트의 성공 여부를 게시 조건에 포함하지 않았다.
새 `wheels` 작업은 다음 4개 `cp39-abi3` 휠을 만들고 검증한다.

| 배포 대상 | GitHub runner | 빌드/검증 환경 |
| --- | --- | --- |
| Linux x86_64 | ubuntu-24.04 | manylinux2014_x86_64 이미지, CPython 3.9 |
| Linux aarch64 | ubuntu-24.04-arm | manylinux2014_aarch64 이미지, CPython 3.9 |
| macOS arm64 | macos-14 | CPython 3.13, setuptools/wheel |
| macOS x86_64 | macos-15-intel | CPython 3.13, setuptools/wheel |

`DOCHAN_BUILD_ACCEL=1`로 빌드하며 Linux는 manylinux 이미지에 포함된 auditwheel로 repair한다.
새 프로젝트 런타임/빌드 의존성이나 cibuildwheel은 추가하지 않았다. 새 artifact 업로드/다운로드 액션도 40자리 SHA로 고정했다.
manylinux 이미지는 `latest` 태그이므로 이미지 digest까지 재현성을 고정한 구성은 아니다.

각 휠은 세 바이너리 확장과 abi3 태그를 검사하고, 새 venv에 해시 고정 dev 의존성과 휠을 설치한다.
실제 venv의 dochan 경로와 세 백엔드 `('c', 'c', 'c')`를 단언한 뒤 전체 테스트를 실행한다.
`DOCHAN_DISABLE_ACCEL=1`에서는 세 백엔드 `python` 단언과 전체 테스트를 반복한다.

pytest가 체크아웃을 sys.path에 추가하거나 multiprocessing이 자식을 생성해도 설치한 휠을 읽도록,
검증용 venv에만 체크아웃의 top-level `dochan` import를 설치 경로로 교정하는 finder를 둔다.
비교 도구가 명시적으로 선택한 별도 기준 소스는 교정하지 않는다. 패키지를 미리 import하지 않으므로
첫 import의 예외·폴백을 검사하는 기존 loader 테스트는 그대로 동작한다. 배포 휠에는 이 finder가 들어가지 않는다.
결함 finder에서 체크아웃 패키지의 예외가 발생하는 것을 먼저 확인한 회귀 테스트도 추가했다.

`wheels`는 `pull_request`에서도 실행하며 job 수준 이벤트 제한이 없다.
`publish`는 tag **push**에서만 실행하며 `needs: [test, security, wheels]`를 요구한다.
`wheels`의 실제 `needs: [test, security]`가 기존 계약 단언도 유지한다.
기존 순수 휠·sdist 빌드 및 설치 smoke test 뒤 플랫폼 휠을 내려받는다.
이후 순수 휠 1개, 정확한 4플랫폼 휠, sdist 1개, 모든 휠의 버전, `twine check`를 확인한다.
누락·중복·다른 아키텍처·선택적 확장 컴파일 실패가 있으면 게시되지 않는다.

## 로컬 확인과 한계

- macOS Apple Silicon, Xcode CPython 3.9.6에서 실행했다.
- `DOCHAN_BUILD_ACCEL=1 python -m build --wheel --no-isolation`은 요구된 `wheel==0.48.0` 부재로 실패했다.
  로컬은 build 1.4.4 / setuptools 82.0.1 / wheel 0.47.0 / twine 6.2.0이다.
  네트워크 금지에 따라 설치 버전은 변경하지 않았다.
- 보조 검증 명령은 `DOCHAN_BUILD_ACCEL=1 python -m build --wheel --no-isolation --skip-dependency-check`이다.
  생성물 `dochan-1.15.0-cp39-abi3-macosx_14_0_universal2.whl`을 새 venv에 `--no-index --no-deps`로 설치했다.
  Mach-O에 arm64/x86_64가 포함됨을 확인했지만 실제 실행은 arm64에서만 검증했다.
- 오프라인 로컬 venv는 설치 휠 경로를 고정한 후 기존 Python 3.9 site-packages의 테스트 도구를 연결했다.
  CI의 locked+hashed dev 의존성을 새로 설치하는 절차 자체는 로컬에서 재현하지 못했다.
- 순수 휠·sdist는 가속 빌드 잔여물이 없는 기준 소스 스냅샷에서 같은 보조 빌드 방식으로 생성했다.
  순수 휠의 바이너리 확장 부재, sdist의 C 소스 3개·헤더 2개 포함과 세 배포물의 twine 검사를 확인했다.
- YAML 파싱, 기존 단언을 유지한 릴리스 계약 및 새 검증 테스트 12개, ruff,
  세 C 파일의 C99 `-Wall -Wextra -Wpedantic -Werror -fsyntax-only` 검사를 통과했다.
- 전체 테스트 결과는 아래와 같다. 최초 pre-import 방식과 무조건 경로 고정 방식에서 발견한 실패는
  원인을 수정한 후 전체 재실행했으며 최종 성공 근거에 이전 실패 실행을 섞지 않았다.

| 최종 전체 검사 | passed | skipped | xfailed | 시간(초) |
| --- | ---: | ---: | ---: | ---: |
| 소스 가속 켬 | 6557 | 36 | 14 | 92.32 |
| 소스 가속 끔 | 6557 | 36 | 14 | 94.46 |
| 설치 휠 가속 켬 | 6557 | 36 | 14 | 77.73 |
| 설치 휠 가속 끔 | 6557 | 36 | 14 | 78.94 |

테스트 실행 시간은 성능 벤치마크가 아니다. 실행 명령은 각 환경에서
`python -m pytest tests/ -q -p no:cacheprovider`이며 끔에는 `DOCHAN_DISABLE_ACCEL=1`을 추가했다.

- Linux 양 아키텍처, macOS Intel, CI 고정 도구 버전 및 GitHub artifact 전달·실제 PyPI 게시 흐름은
  **CI에서만 확인할 수 있으며 이번 로컬 작업에서 실행하지 않았다.** 커밋·푸시·태그·게시하지 않았다.

## Windows 후속 작업

현재 전체 테스트에는 Unix 전용 분석 도구 테스트가 포함되어 있다.
예를 들어 `tests/test_probe_cfb_review.py`는 수집 시 `scripts/probe_cfb_review.py`를 import하며,
그 스크립트는 Windows 표준 Python에 없는 `resource`를 최상위에서 import한다.
`compare_cfb_olefile.py`, `compare_hwp_large_corpus.py`, `benchmark_hwp_runs.py`,
`probe_speed_batch.py` 등에도 같은 제약이 있고, 일부 테스트/도구는 `SIGALRM`을 전제로 한다.
Windows는 이번 빌드 행렬과 게시 필수 배포물에서 제외했다.
**후속: 테스트의 resource/SIGALRM 의존 제거 뒤 추가.**
이는 단순한 CI 미실행과 별개의 **정적 분석으로 확인된 기존 호환성 차단 사항**이다.

기존 테스트를 삭제·축소·무조건 skip하거나 가짜 resource 모듈로 통과시키지 않았다.
Windows 추가 전 분석 도구의 수집/실행 호환성 처리가 필요하다. 네 플랫폼의 실제 CI 성공은 별도로 확인해야 한다.
실제 CI 전체 성공 전에는 README에 가속 휠이 이미 제공된다고 쓰지 않는다.

## 출력 회귀 확인

런타임 Python/C 코드와 알고리즘은 변경하지 않았다. `.git` 쓰기 금지 때문에 공통 규칙의
별도 detached worktree 대신 `git archive HEAD`로 기준 커밋 스냅샷을 만들었다.
전후 모두 Xcode Python 3.9로 `DOCHAN_BUILD_ACCEL=1 python setup.py build_ext --inplace --force`를 실행했다.
입력은 외부 문서를 복사하지 않고 생성한 40문단 DOCX와 40줄 단일 페이지 PDF 각 1개다.

```sh
python -m scripts.probe_output_speed collect "$INPUTS" --source "$BEFORE" --output before.json
python -m scripts.probe_output_speed collect "$INPUTS" --source "$AFTER" --output after.json
python -m scripts.probe_output_speed compare before.json after.json
```

같은 입력·명령으로 전·후·후·전·전·후 순서로 실행했다.

| 순서 | 전 wall(초) | 후 wall(초) | 두 문서 출력 해시 차이 |
| --- | ---: | ---: | ---: |
| 전1 / 후1 | 2.518320 | 0.252309 | 0 |
| 후2 / 전2 | 0.247637 | 0.257329 | 0 |
| 전3 / 후3 | 0.265536 | 0.286515 | 0 |
| 중앙값 | 0.265536 | 0.257329 | 0 |

세 비교 모두 Markdown/JSON/text/errors 해시 차이, 실패 변화, JSON 폴백이 0이다.
표본은 합성 문서 2개뿐이며 코퍼스 전수 검증이 아니다. wall은 최초 import, 캐시, 병행 테스트 영향을 포함한다.
이 수치로 속도 향상이나 실물 문서 성능을 주장하지 않는다. 변경 효과는 릴리스가 검증된 가속 휠을 함께 제공하도록 한 것이다.

## TASK-FIX 후속 검증

Windows를 행렬과 배포물 필수 집합에서 제외했다. 네 플랫폼과 순수 휠·sdist를 요구하며,
Windows는 테스트의 resource/SIGALRM 의존 제거 뒤 추가한다. 기존 파서/분석 도구 테스트는 수정하거나 skip하지 않았다.
PR 이벤트와 test/security/wheels의 job 조건 부재를 계약 테스트로 확인한다. 게시만 tag push에 제한한다.
워크플로의 두 휠 빌드는 기본 격리를 사용하므로 pyproject의 setuptools==82.0.1 / wheel==0.48.0을 그대로 요청한다.
로컬 도구 버전에 맞춰 이 고정을 낮추지 않았다.

이번 설치 재검증에서 외부 임시 venv는 기존 probe 9개의 선택 트리 내부 import 단언과 충돌했다.
검증기의 venv를 체크아웃 아래 임시 디렉터리에 생성하도록 수정했다. site-packages import finder와
실제 sys.prefix 하위 설치 경로 단언은 유지하며, 종료 시 임시 venv를 정리한다.
이는 설치 휠 테스트의 경로 계약을 맞춘 것이며 기존 테스트 단언을 완화하지 않았다.

4플랫폼 계약은 수정 전 2 failed/11 passed, 수정 후 13 passed였다.
YAML 4플랫폼 파싱, Bash 18단계 구문, ruff, 새 macOS universal2 휠 빌드와 twine check를 통과했다.
로컬 빌드는 이전과 같은 오프라인 --no-isolation --skip-dependency-check 보조 검증이다.
실제 실행 아키텍처는 arm64이며, 다른 세 플랫폼 및 CI 고정 버전 빌드·artifact 전달은 PR CI 확인 대상이다.
성능/출력 알고리즘은 바뀌지 않았고 추가 성능 향상을 주장하지 않는다. 위 출력 비교 수치는 앞선 작업 기록이다.

후속 전체 검사는 소스 켬/끔 및 설치 휠 켬/끔 모두 6558 passed, 36 skipped, 14 xfailed였다.
각 실행 시간은 77.25s / 78.77s / 83.10s / 81.58s이며 성능 벤치마크가 아니다.

## TASK-FIX2: CI 호환성과 시간 검사

manylinux 두 작업의 빌드 인터프리터를 cp39에서 cp310으로 변경했다.
TASK-FIX2에 보고된 build 1.5.0의 Python 3.9 비호환을 피하는 선택이며,
build 고정·격리 빌드·setup.py의 cp39 제한 ABI는 유지한다.
오프라인이므로 해당 고정 버전의 배포 존재나 cp310 설치 성공을 새로 확인하지 않았다.
새 계약은 수정 전 1 failed/8 passed였고, 수정 후 휠 검증기 포함 16 passed다.
실제 결과 휠의 cp39-abi3 검사를 유지하며 Linux 양 아키텍처의 cp310-abi3 오태그를 거부하는 회귀도 추가했다.

수식 테스트는 절대 6초 대신 1,000개 워밍업 후 N=30,000과 2N=60,000을
교대 각 3회 측정한 중앙값 비율 ≤3.0으로 선형성을 확인한다.
독립 pytest 프로세스 10회 모두 통과했다(각 전체 실행 8.27–8.43초).
이는 성능 개선 수치가 아니다. Ruff, YAML 4대상 파싱, Bash 18단계 구문 검사도 통과했다.
실제 manylinux cp310 빌드·설치·cp39-abi3 결과, Intel 러너 시간 검사와 artifact 전달은 CI 확인 대상이다.
이번에는 런타임 변경이나 휠 재빌드 없이 소스 전체 회귀를 수행했다.
소스 전체 기본/비활성 모드는 모두 6663 passed, 45 skipped, 14 xfailed였으며
각각 79.43초/76.25초였다. PDF 백엔드 c/c/c 및 python/python/python을 별도로 확인했다.
