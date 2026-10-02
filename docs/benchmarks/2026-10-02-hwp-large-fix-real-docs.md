# HWP 대형 문서 리뷰 반영 실물 검증

2026-10-03에 작업 `hwp-large-fix`를 검증했다. 파일명 날짜는 작업 지시의 명명 규칙을 따른다. 기준 구현은 `332d6d6`(작업 시작 시 HEAD~1), 리뷰 대상은 `571e0fa`이다. 공개 코퍼스 원본은 읽기만 했고 내부 문서는 파일명·내용 없이 집계했다.

## 판정과 실물 근거

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| HWP 대형 본문 | `big_file.hwp`, `hwplib-big_file.hwp` | 원시 헤더가 각각 638,984레코드이다. | 기존 20만 절단 없이 끝까지 읽는다. | 각각 plain 2,359,294자이며 ERR가 없다. | 통과했다. 새 README 칸을 추가하지 않는다. |
| HWP 대형 표 본문 | `issue2063_huge_cellbreak_table.hwp` | 원시 212,442레코드와 격자 52,770셀이다. | 레코드를 완독하고 셀 제한을 유지한다. | plain 147,145자이며 ERR가 없다. | 통과했다. |
| HWP 대형 본문 | `pubinst-kostat_2024년_사회조사_결과_보도자료.hwp` | 원시 217,588레코드이다. | 끝까지 읽고 ERR가 없다. | plain 203,725자이며 ERR가 없다. | 통과했다. |
| HWP 대형 변경 추적 본문 | `rhwp-1130000-201900011_D0150004-1-002_2017년기준_시장구조조사.hwp` | BodyText 212,001, ViewText 265,451레코드이다. | 마지막 본문까지 읽는다. | plain 402,642자이며 ERR가 없다. | 대형 본문은 통과했다. 변경 추적 기능의 ✅ 근거로 확대하지 않는다. |
| HWP 변경 추적 | 공개 변경 추적 3문서이다. | 저장 BodyText와 독립 ViewText를 비교했다. | 독립 투영의 본문·서식이 같아야 한다. | API final은 BodyText와 같지만 독립 ViewText에는 style_id 52,477개와 heading_level 255개 차이가 남는다. | ⬜를 유지한다. |
| HWP DocInfo | 공개 전체이며 최대 5,361레코드이다. | 스트림 원시 헤더 전수 계수이다. | 기존 20만 상한을 유지한다. | 공개 출력 변화가 없으며 합성 20만은 수용하고 200,001번째는 거부한다. | 상한 회귀는 통과했다. 20만 초과 실물 구현·승격은 없다. |
| HWPX 셀·차트 | 기본 1,675파일과 혼재 확장자 추가 표본이다. | 원시 XML 계수와 기준 출력이다. | 기존 제한과 출력이 같아야 한다. | 모든 출력이 같다. 물리 셀 최대 49,925, 격자 52,825, 배치 차트 점 528이다. | 새 기능 승격은 없다. |

공개 총 7,076파일 중 리뷰 대상 구현과 7,076/7,076(100%)의 JSON·Markdown·plain·오류 목록이 같다. HEAD~1과는 7,071개가 같고 위 대형 5개만 바뀌었다. 기본 HWP 5,363개 중 5,358개, 기본 HWPX 1,675개 전부, 추가 확장자 38개 전부가 HEAD~1과 같다. 변환 예외는 양쪽 모두 0개이다. 기존 오류도 같은 오류이면 동일에 포함되므로 이 수치를 완독률로 해석하지 않는다.

내부 실물 76쌍의 비교 지표 익명 SHA-256은 양쪽 모두 `e499b657caf5d937af020976b60ea295a06fba5d53c41f29fa2d939f5c7d37e8`이다. 평균 토큰 비율 0.9997, 평균 셀 일치율 0.9991, 평균 서식 일치율 1.0이다. HWPX 표 796개와 HWP 표 795개의 기존 차이는 남는다. 구조 프로브를 재실행했으며 공개·내부 분포는 기존 측정과 같고 소요시간만 달랐다.

## 손상 다중 섹션 보존

기존 공개 코퍼스 기준선에는 `섹션 N 파싱 실패` 사례가 없었으므로 합성 OLE 스트림을 추가했다. OLE 접근만 메모리 대역으로 바꾸고 실제 Dochan 파서와 출력기를 사용한다. 각 사례는 첫 섹션을 손상시키고 뒤 999섹션에 순서가 다른 본문을 넣는다.

| 합성 표본 | HEAD~1의 정상 섹션 보존 | 수정 후 보존 | Markdown·JSON·오류 비교 | 판정 |
| --- | ---: | ---: | --- | --- |
| 즉시 잘못된 DEFLATE 바이트 | 999/999 | 999/999 | 모두 정확히 같다. | 통과했다. |
| 잘린 DEFLATE | 999/999 | 999/999 | 모두 정확히 같다. | 통과했다. |
| 해제 완료 후 CRC 불일치 | 999/999 | 999/999 | 모두 정확히 같다. | 통과했다. |

각 사례에는 실제로 `ERR: 섹션 0 파싱 실패`가 하나 남으며 뒤 정상 본문은 사라지지 않는다. 손상을 숨기거나 정답을 빈 본문으로 바꾸지 않았다.

## 최종 자원 정책과 측정 범위

섹션 100만, 본문 문서 누적 130만, DocInfo 별도 20만 레코드이다. 문서 전체로는 두 저장소 합산 최대 150만 레코드이며, DocInfo 200MiB와 본문 문서 누적 200MiB의 해제 바이트 제한은 별개이다. 공개 본문 문서 최대 638,984에 대해 누적 130만은 약 2.03배 여유를 둔다. DocInfo 실물 최대 5,361에는 상한 확대 근거가 없어 이전 20만으로 복귀했다.

일반 본문과 배포용 본문 모두 성공한 해제와 손상 스트림의 이미 해제된 바이트를 차감한다. 배포용 CRC·정렬 검증을 본문 해제와 통합해 중복 해제를 없앴다. CRC·잘림은 실제 반환 누적량을 사용한다. Python zlib이 같은 호출의 실패 직전 출력을 반환하지 않는 경우에는 64KiB 이하 입력·출력으로 최대 32회 제한 재탐색한다. 그 경우 최대 1바이트를 보수적으로 추가 계상할 수 있다. 이 재탐색 비용은 별도로 제한된 오류 처리 오버헤드이며, 바이트 예산은 재탐색을 포함한 CPU 시간이나 OS RSS 상한이 아니다. 즉시 잘못된 `0xff`는 0바이트로 계상한다.

문서 예산 소진 진단은 종류별로 1회만 기록한다. 서로 다른 손상 섹션의 개별 실패는 그대로 남긴다. 4MiB를 해제한 뒤 CRC가 실패하는 80개 섹션은 일반·배포용 모두 50개(200MiB)까지만 검증하고 나머지 30개는 해제 전에 거부한다. 오류는 개별 손상 50개와 문서 상한 1개이다. ViewText가 문서 레코드 예산을 소진해도 폴백 예외 계약을 지키며, 폴백은 예산을 초기화하지 않으므로 본문이 반드시 복구되는 것은 아니다.

레코드 슬롯화·트리 표현 변경·5패스 복제 제거는 이번 수정에 넣지 않았다. 상한과 확인된 반복량 문제를 고치는 범위로 제한했으며, 입출력 동등성을 증명하지 않은 메모리 최적화를 적용하지 않았다. 링크는 정렬 경계와 힙으로 처리해 O(R + L log L)이며 기존 서식·런 분할을 유지한다.

시간은 Dochan 생성부터 to_markdown과 to_json 완료까지이며, 모델과 두 출력 문자열을 동시에 보관한다. 각 사례를 Python 3.9 새 프로세스에서 실행하고 프로세스 최대 RSS를 기록했다. 입력은 합성 레코드를 압축한 OLE 스트림 대역이며 AES 배포용 사례는 실제 암호문을 사용했다. 전체 테스트·코퍼스 프로브도 함께 실행된 환경이므로 시간은 통제된 성능 비교가 아니다. RSS에는 인터프리터·입력 생성도 포함한다. 이전 parse_stream 단독 최대 1,157.62MiB는 공개 API 자원 수치로 사용할 수 없어 다음 표로 대체한다.

| 합성 사례 | 공개 API 전체 초 | 최대 RSS MiB | 결과 |
| --- | ---: | ---: | --- |
| 빈 레코드 1,000,000개 | 2.540045 | 585.41 | 요소 0개, 서식 0개, 오류 0개이다. |
| 빈 레코드 1,000,001개 | 2.412847 | 597.88 | 요소 0개, 서식 0개, 오류 1개이다. |
| 빈 LIST_HEADER 뒤 형제 999,999개 | 2.446565 | 576.61 | 요소 0개, 서식 0개, 오류 0개이다. |
| 한 섹션 문단 500,000개 | 24.969326 | 1431.91 | 요소 500,000개, 서식 0개, 오류 0개이다. |
| 3×100만 레코드 시도, 130만 보존 | 21.992935 | 1923.45 | 요소 650,000개, 서식 0개, 오류 1개이다. |
| 압축 해제 200MiB | 0.220026 | 520.53 | 요소 0개, 서식 0개, 오류 0개이다. |
| 압축 해제 200MiB+1바이트 | 0.117236 | 288.64 | 요소 0개, 서식 0개, 오류 1개이다. |
| DocInfo CHAR_SHAPE 200,001개 | 1.880191 | 265.25 | 요소 0개, 서식 200,000개, 오류 1개이다. |
| DocInfo CHAR_SHAPE 200,000개 | 1.709234 | 295.00 | 요소 0개, 서식 200,000개, 오류 0개이다. |
| DocInfo 20만과 본문 3×100만 레코드 | 19.159028 | 2598.95 | 요소 650,000개, 서식 200,000개, 오류 1개이다. |
| 표 격자 200,000셀 | 1.518320 | 343.47 | 요소 1개, 서식 0개, 오류 0개이다. |
| 잘못된 DEFLATE 뒤 정상 999섹션 | 0.040220 | 42.75 | 정상 999/999섹션을 보존했다. |
| 잘린 DEFLATE 뒤 정상 999섹션 | 0.035495 | 42.77 | 정상 999/999섹션을 보존했다. |
| CRC 오류 뒤 정상 999섹션 | 0.037676 | 41.80 | 정상 999/999섹션을 보존했다. |
| 일반 본문 4MiB CRC 실패 80회 시도 | 0.055369 | 57.84 | 50회 해제 후 200MiB를 소진했다. 이후 거부 진단은 1회이다. |
| 배포용 4MiB CRC 실패 80회 시도 | 0.186049 | 59.34 | 50회 해제 후 200MiB를 소진했다. 이후 거부 진단은 1회이다. |

관측 최대 RSS는 2,598.95MiB이고 전체 시간 최댓값은 24.969326초이다. 최대 RSS 사례는 DocInfo CHAR_SHAPE 20만을 유지한 채 본문 3×100만 레코드를 시도한 경우이며, 65만 문단(130만 레코드)을 보존하고 문서 상한 오류를 1회 기록했다. 이 수치는 악성 입력 전체에 대한 메모리 상한을 증명하지 않는다.

## 테스트와 기존 기대값 정정

신규 예산·상한·배포용 테스트 12개는 수정 전에 모두 실패했다. 해제 계상 테스트 9개와 링크 반복량 테스트도 실패를 확인했다. 이후 경계 출력 버퍼 회귀와 보수 계상 테스트를 보완했다. 전체 실행 결과는 **3,324 passed, 24 skipped, 14 xfailed**이다. Ruff와 diff 공백 검사도 통과했다. 기존 skip·xfail은 성공으로 세지 않았다.

HEAD의 `test_failed_inflation_cannot_restart_document_work_budget`는 0바이트를 해제한 `0xff`에도 남은 예산 전부를 소비해야 한다고 단언해 결함을 고정했다. 이 단언만 뒤 정상 섹션 보존으로 정정하고 반복 CRC 실패 예산 소진을 별도 테스트로 검증했다. `test_large_doc_info_preserves_last_record`는 200,002레코드 수용을 전제한 합성 크기를 200,000으로 바꿨다. 마지막 레코드 보존 단언은 그대로이며 초과 거부는 새 테스트로 검증했다. 그 밖의 HEAD 테스트 단언은 바꾸지 않았다.

## 재현

```bash
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
/usr/bin/python3 -m scripts.benchmark_hwp_large_limits --output .codex-work/fix-resources.json
/usr/bin/python3 -m scripts.probe_hwp_corrupt_sections --source-root /path/to/baseline --output .codex-work/fix-corrupt-baseline.json
/usr/bin/python3 -m scripts.compare_hwp_large_corpus snapshot --corpus /path/to/hwp-public --source-root /path/to/source --revision REV --pairs /path/to/private-pairs --output .codex-work/snapshot.jsonl
/usr/bin/python3 -m scripts.compare_hwp_large_corpus compare --before .codex-work/fix-corpus-baseline.jsonl --after .codex-work/fix-corpus-current.jsonl --output .codex-work/fix-corpus-comparison.json
/usr/bin/python3 -m scripts.probe_hwp_large_inventory /path/to/hwp-public --private-pairs /path/to/private-pairs --output .codex-work/fix-inventory.json
```

README·CHANGELOG는 수정하지 않았다. 독립 ViewText 서식 차이와 기존 HWPX XML·이미지 크기 제한은 남아 있으며 변경 추적은 ⬜ 유지이다.

## 리뷰 지적별 조치

| 지적 | 재현 여부 | 조치 | 테스트 이름 |
| --- | --- | --- | --- |
| codex P1: 링크마다 런 전체 재순회 | 링크 1,000개에서 길이 접근 500,500회로 재현했다. | 경계를 정렬하고 우선순위 힙으로 한 번 순회한다. 중첩의 마지막 링크 우선, 서식과 런 분할을 유지한다. | test_many_disjoint_links_do_not_rescan_all_previous_runs, test_link_boundary_sweep_preserves_overlaps_styles_and_empty_runs |
| codex P2: 배포용 사전 검증 비용 누락 | 5개 손상 입력 모두 CRC 검증에 도달하고 성공 입력이 두 번 해제됨을 재현했다. | 검증 콜백과 본문 해제를 통합하고 같은 문서 예산으로 성공·실패를 차감한다. | test_distribution_failures_share_document_inflation_budget, test_distribution_success_inflates_once |
| Opus P1: 손상 섹션 뒤 정상 본문 소실 | 잘못된 DEFLATE·잘림·CRC 3종에서 재현했다. | 원래 예외의 inflated를 차감한다. 1+999섹션의 공개 API 출력은 HEAD~1과 같다. | test_damaged_section_keeps_following_sections, test_repeated_crc_failure_spends_only_emitted_bytes, test_invalid_later_deflate_block_accounts_for_same_call_output |
| Opus P2-1: DocInfo 상한 확대 | 상수와 200,001번째 레코드 수용으로 재현했다. | DocInfo 20만, 본문 문서 130만, 섹션 100만으로 정정했다. | test_default_record_caps_match_measured_policy, test_docinfo_stops_at_original_cap |
| Opus P2-2: 자원 수치 과소 기술 | 이전 스크립트가 parse_stream만 호출함을 확인했다. | Dochan→to_markdown→to_json과 동시 보관 상태를 새 프로세스 16사례에서 재측정했다. | test_resource_benchmark_retains_public_api_outputs, test_synthetic_ole_runs_real_public_reader_and_serializers |
| Opus P3-1: 예산 소진 진단 폭주 | 1,000섹션에 중복 오류 1,000개로 재현했다. | 섹션 초기화와 별개인 문서 키로 같은 예산 오류를 1회만 남긴다. | test_exhausted_document_reports_limit_only_once |
| Opus P3-2: 문서 레코드 초과 시 폴백 우회 | reject_record_limit에서 예외가 없고 경고도 없음으로 재현했다. | 문서 상한도 HWPRecordLimitError를 발생시킨다. 예산은 복원하지 않으며 경고는 폴백 시도를 정확히 표시한다. | test_document_record_limit_rejects_view_before_building_model, test_document_record_limit_attempts_body_fallback |
| Opus P3-3: 중첩 LIST_HEADER 동등성 테스트 누락 | 이동 자식 재귀 삭제 변형이 신규 2개 테스트에서 실패했다. | 실제 트리·순서 및 깊이 제한을 단언하는 회귀 테스트를 추가했다. | test_moved_list_header_children_receive_nested_repair, test_moved_children_obey_structure_depth_limit |
| Opus P3-4: README·CHANGELOG | 오케스트레이터 담당이다. | 지정대로 수정하지 않았다. | 해당하지 않는다. |
