# HWPX 구현·검증 진행 기록

확인일: 2026-09-19. 현재 체크아웃의 코드와 테스트를 기준으로 기록한다.
[66개 태스크 계획](../../superpowers/plans/hwpx-parallel-implementation-plan.md)의
일부 범위를 구현한 상태이며, 아래 기능의 존재가 각 태스크의 전체 완료를 뜻하지 않는다.

## 현재 구현과 근거

| 범위 | 현재 동작 | 재현 가능한 근거 |
| --- | --- | --- |
| S01 최소 범위 | `parser.py`의 `_char_shapes_by_id`로 실제 charPr ID 조회. 기존 `Document.char_shapes` 목록 계약 보존 | `tests/test_hwpx_regressions.py`: 역순·비연속 ID, 누락 참조, 파서 재사용 |
| P05 정확성 수정 | `_parse_table_elem`이 최초 셀 파싱 결과를 폴백에서도 재사용. 셀 예산을 파싱 전에 예약 | 같은 테스트 파일: 셀 파싱 횟수, 각주 번호, 중첩 표 예산 |
| P06·I06 이미지 옵션 | `include_assets=False`와 CLI `--no-assets`를 reader·parser·직렬/병렬 배치로 전달. 이미지 참조·캡션 보존, OCR 병용 거부 | `tests/test_hwpx_assets_option.py`, `tests/test_hwpx_cli_options.py`, [옵션 검증](options-validation.md) |
| A01 인벤토리 | magic 분류, SHA-256 중복군, 제한된 ZIP 메타데이터 읽기, 결정적 JSON | `tests/test_hwpx_inventory.py`, [초기 조사 기록](inventory.md) |
| A03·A04 조사 | 공개 XML에서 독립 도출한 gold·표본/파트 SHA-256, 확인된 구조와 미확정 의미 분리 | [revision-spec.md](revision-spec.md), [chart-spec.md](chart-spec.md) |
| 변경 추적 텍스트·API 연결 | `RevisionProjector`와 parser·reader 연결. `preserve`/`final`/`original` 제공. 미확정 범위는 보존·진단, 하위 본문 흐름 격리 | `tests/test_hwpx_revisions.py`, [변경 추적 검증](revision-validation.md) |
| 차트 XML·ZIP/API 연결 | `parse_chart_xml`이 제목·계열별 표 반환. parser가 참조 경로·switch·본문 순서·ZIP/문서 예산 처리 | `tests/test_hwpx_charts.py`, `tests/test_hwpx_chart_integration.py`, [차트 통합 검증](chart-integration-validation.md) |
| I06 변경 보기 옵션 | `--revision-mode` 및 배치 API 전달. preserve 경고는 출력 허용, 불완전 final/original은 실패·기존 출력 보존 | `tests/test_hwpx_cli_options.py`, `tests/test_batch_cli.py`, [옵션 검증](options-validation.md) |

차트 출력은 기존 `Paragraph`/`Table` 모델을 사용하며, 변경 추적은 텍스트 투영이다.
원 계획의 구조화 변경 메타데이터 모델·공통 위치/진단 모델·범례/서식 렌더링까지
구현되었다고 해석하지 않는다. `preserve`는 변경 이력까지 표시하는 `all` 모델이 아니다.

## 검증 명령과 기록

저장소 루트에서 의존성이 설치된 Python 환경으로 실행한다. 여기서 `python`은
그 환경의 인터프리터를 뜻한다. 검증 환경: Python 3.9.6, pytest 8.4.2.

```bash
python -m pytest tests/test_hwpx_*.py tests/test_batch_cli.py tests/test_parser_hardening_review.py -q --tb=short
python -m pytest tests/ -q --tb=short
git diff --check
```

2026-09-19 문서 정리 후 전체 명령을 실행한 결과는 **1,604 passed, 14 xfailed**
(31.79초), 실패·일반 skip 0건이다. 아래 관련 항목은 같은 전체 실행의 JUnit 결과에서
집계했으며 별도 실행 결과를 합산한 것이 아니다. 시간은 이 실행의 경과 시간이며
파서 성능 벤치마크가 아니다.

| 검증 파일/범위 | passed | xfailed | 일반 skip |
| --- | ---: | ---: | ---: |
| `test_hwpx_regressions.py` | 20 | 0 | 0 |
| `test_hwpx_inventory.py` | 34 | 0 | 0 |
| `test_hwpx_assets_option.py` | 32 | 0 | 0 |
| `test_hwpx_revisions.py` | 170 | 0 | 0 |
| `test_hwpx_charts.py` | 53 | 0 | 0 |
| `test_hwpx_chart_integration.py` | 66 | 0 | 0 |
| `test_hwpx_cli_options.py` | 89 | 0 | 0 |
| 기존 HWPX reader·ZIP guard·XML 문자 회귀 | 33 | 0 | 0 |
| `test_batch_cli.py` | 44 | 0 | 0 |
| `test_parser_hardening_review.py` | 95 | 5 | 0 |
| 관련 범위 합계 | **636** | **5** | **0** |
| 전체 `tests/` | **1,604** | **14** | **0** |

`git diff --check`도 통과했다. 문서 정리 전후 spec JSON 블록은 바이트 단위로
동일하며 기존 SHA-256 값도 모두 유지했다. 이번 정리의 파일 변경은 허용된
벤치마크 문서 8개와 계획 문서 2개에 한정되며 코드·테스트는 수정하지 않았다.

실물 테스트는 로컬 공개 corpus가 없으면 명시적으로 skip한다. skip과 기존 xfail은
통과로 세지 않는다. spec JSON은 테스트가 읽는 고정 정답이므로 공개 문서 정리에서도
블록 순서·값과 표본 SHA-256을 유지한다.

각 검증 문서의 초기 TDD 수치는 해당 개발 시점의 기록이다. 코퍼스 조사마다 모수와
시점이 다를 수 있으므로 파일 수를 합산하거나 현재 전체 정확도로 해석하지 않는다.

## 실물 검증의 한계

- 변경 추적의 정확한 텍스트 gold는 공개 테스트 표본 R1 한 문서다. R2는 부분 지원
  진단·preserve XML 보존을 확인하며, final/original 전체 본문 정확도는 미검증이다.
- 차트는 공개 4문서의 38개 참조 중 지원 차트 33개를 독립 XML 데이터와 비교한다.
  미지원 차트 5개는 진단을 확인한다. 저장 캐시/literal 추출이며 재계산·UI 재현은 아니다.
- charPr·표 폴백의 근거는 지정 회귀 테스트다. 실물 서식 전체의 정확도나 성능 향상을
  이 결과만으로 확정하지 않는다.
- 라이선스는 spec에 기록된 저장소 선언의 직접 확인과 수집 인덱스의 분류를 구분한다.
  공개 접근·해시 일치는 개별 파일의 저작권 또는 재배포 권리 보증이 아니다.

## 남은 범위

**66개 전체 완료가 아니다.** 스타일 우선순위·목록, 공통 위치/누락 진단 모델,
구조화 변경 메타데이터, 복잡한 변경 범위·서식 변경 투영, 미지원 차트 유형,
홀드아웃 분리·평가기, 정식 성능/RSS 비교와 스트리밍 채택 판단이 남아 있다.
전체 테스트 통과도 이 미구현 범위나 계획의 공개·릴리스 게이트 완료를 뜻하지 않는다.
단위 테스트와 실물 검증이 모두 없는 항목을 지원 완료로 표시하지 않는다.
