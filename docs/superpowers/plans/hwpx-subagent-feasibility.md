# HWPX 병렬 구현의 범위·의존성 검토

확인일: 2026-09-19. [원 계획](hwpx-parallel-implementation-plan.md)의 66개 태스크를
분리하기 위한 검토다. 현재 구현·검증 상태는
[진행 기록](../../benchmarks/hwpx/implementation-progress.md)을 기준으로 한다.
작업 세션의 반환 여부를 제품 구현이나 검증 완료의 근거로 사용하지 않는다.

## 현재 코드와 검증 근거

| 검토 항목 | 현재 상태 | 확인 명령·기록 |
| --- | --- | --- |
| charPr ID 조회 | 실제 ID 색인으로 비연속·역순 참조 처리 | `python -m pytest tests/test_hwpx_regressions.py -q -k char_pr` |
| 좌표 없는 표 폴백 | 최초 셀 파싱 결과 재사용, 각주·중첩 표 예산 회귀 검증 | `python -m pytest tests/test_hwpx_regressions.py -q -k 'fallback or coordinate_free'` |
| 변경 추적 | 텍스트 세 모드와 부분 지원 진단. 서식 변경 투영은 미지원 | `python -m pytest tests/test_hwpx_revisions.py -q`; [검증 범위](../../benchmarks/hwpx/revision-validation.md) |
| 차트 | XML 캐시 추출과 ZIP/API 연결. 미지원 유형은 명시 진단 | `python -m pytest tests/test_hwpx_charts.py tests/test_hwpx_chart_integration.py -q`; [통합 검증](../../benchmarks/hwpx/chart-integration-validation.md) |
| CLI·배치 옵션 | 이미지 로딩·변경 보기 옵션 전달, 실패 시 출력 보존 | `python -m pytest tests/test_hwpx_cli_options.py tests/test_batch_cli.py -q` |
| 코퍼스 분류 | 확장자와 magic 구분, SHA-256 중복군 식별 | `python -m pytest tests/test_hwpx_inventory.py -q`; [조사 시점별 집계](../../benchmarks/hwpx/inventory.md) |

전체 취소선 제거 휴리스틱의 실제 오판 여부는 독립 실물 gold로 확정되지 않았다.
이 항목을 수정 완료나 확인된 실물 결함으로 기록하지 않는다. 전체 코퍼스 정확도,
한글 UI 동일성, 성능 우위도 위 테스트의 검증 대상이 아니다.

## 원 계획의 의존성·소유권 정정

아래는 향후 계획을 실행할 때 적용할 정정이다. 이미 연결된 최소 구현을
미구현으로 되돌리거나 아래 의존성 전체가 충족됐다고 간주하지 않는다.

- K01의 필수 선행은 A02/A05/A09로 축소한다. A03/A04는 각각 변경 추적/차트
  확장 계약에 필요하다. 미확정 확장 때문에 기본 계약을 막지 않는다.
- K04는 검증된 기본 모델부터 결정한다. 현재 차트는 기존 표 모델을 쓰고,
  변경 추적은 텍스트만 투영하므로 별도 모델 완료로 세지 않는다.
- C01에 필요한 제한된 ZIP 읽기는 현재 parser에 있다. 향후 P04로 공용화할 때
  기존 경로·읽기·누적 예산 검증을 유지한다. 별도 `package.py` 구현 완료는 아니다.
- O02/O03/O04의 기능 선행은 각각 I02/I04/I05와 O01이다. O02→O03→O04는
  파일 예약 순서이며 필수 기능 의존성은 아니다.
- I06과 최종 게이트는 마일스톤에 포함된 기능만 기다린다. 제외한 기능은 명시한다.
- Q의 `docs/benchmarks/hwpx/*` 소유권에서 S/R/C/D의 개별 spec 문서를 제외한다.
- 기존 `tests/test_hwpx_reader.py`와 `tests/test_parser_hardening_review.py`는 I,
  `tests/test_conversion_model.py`는 M이 관리한다. 독립 신규 테스트는 기능 담당 소유다.
- 스트리밍 미채택 시 실험 모듈·테스트는 P, parser 연결부는 I가 정리한다.
- S01의 최소 ID 조회와 P05의 정확성 수정은 공통 모델·성능 측정과 독립적으로
  검증할 수 있다. 전체 서식 해석이나 성능 태스크의 완료와 구분한다.

## 이후 작업과 통합 조건

남은 작업은 스타일·목록 규격, 공통 위치/누락 진단, 홀드아웃·평가기,
정식 성능/RSS 측정 및 복잡한 변경 추적·미지원 차트 범위다.
parser는 단일 통합 담당이 수정하고 독립 기능 모듈과 테스트는 경로를 분리한다.
성능 측정은 다른 테스트·빌드와 겹치지 않게 단독 실행한다.

통합 근거는 diff, 재현 명령과 결과, 독립 gold 및 미지원 범위다.
실물 자료가 없는 테스트는 skip으로 구분하며 비공개 문서의 원문·이름·내부정보를
공개 기록에 추가하지 않는다. 이 검토는 66개 태스크 전체 완료나 릴리스 승인을 뜻하지 않는다.
