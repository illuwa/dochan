# native-cfb2 리뷰 반영 실물 검증

## 3차 최종 검증: 1.7.0 대비와 직전 대비

이번 기준선은 1.7.0 `107e18d`와 직전 수정 `554ade6` 두 개이다. 각 커밋의 소스를 `git archive`로 고정하고 별도 프로세스에서 실제 Dochan API의 Markdown·JSON·errors 전체 문자열 SHA-256을 비교했다. 아래 2차 이력의 79개 변화는 `f9d0d50` 대비이며 이번 81개·37개와 기준이 다르다.

Opus와 같은 1,893개를 다시 선정했다. POI document 162개, slideshow 145개, spreadsheet 420개, LO 635개, Tika 10개와 공개 HWP 521개이다. HWP는 DIFAT가 있는 121개 전수와 나머지에서 `random.Random(4242)`로 고른 400개이다. 디렉터리와 파일을 각각 정렬한 탐색 순서도 기존 감수 목록과 일치한다. 파일당 제한은 400초·7,168 MiB이며 이는 측정된 필요량이 아닌 검증 작업의 상한이다.

| 기준선 → 최종 수정본 | 표본 | 세 출력 동일 | 변화 | Markdown 변화 | 정상군 errors 변화 | 미검증 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.7.0 `107e18d` 대비이다. | 1,893 | 1,812 | 81 | 5 | 0 | 0 |
| 직전 `554ade6` 대비이다. | 1,893 | 1,856 | 37 | 0 | 0 | 0 |
| 1.7.0 대비 메타데이터 편차 정상군이다. | 47 | 47 | 0 | 0 | 0 | 0 |

정상군은 경로에서 `clusterfuzz`, `ofz`, `crash`, `hang`, `fuzz`, `leak`, `oom`, `forcepoint` 및 `/fail/`을 제외한 1,741개이다. 이 집합은 두 기준선 대비 세 출력이 전부 같다. 명칭 필터만으로 나머지의 손상을 단정하지 않았으며 실제 변화 81개 전부에 독립 원시 바이트 감사의 주소·디렉터리·본문 손상 근거가 있다. Byte Order 편차나 마지막 섹터 패딩 부족만으로는 손상으로 분류하지 않았다. 검사 범위의 회귀 판정이며 모든 정상 문서에 대한 증명은 아니다.

메타데이터 47개는 직전 리더로 공개 CFB 6,761개의 모든 스트림을 열어 `parsing_issues`는 있지만 `recovery_issues`가 없는 67개에서 위 퍼즈 키워드를 제외한 48개를 얻고, 지원 문서 확장자 `.doc/.ppt/.xls/.hwp`가 아닌 공개 `62625.bin`을 제외한 집합이다. 46개는 1,893개 표본과 겹치므로 합집합은 1,894개이다. 47개 모두 errors를 포함한 세 출력이 1.7.0과 같으며 새 WARN은 0개이다.

### 3차 변경 동작과 칸별 증거

선언된 섹터 개수를 모두 읽으면 꼬리는 순회하지 않고 `stream has excess allocated sectors` 메타데이터로만 기록한다. 실제 본문 내부 순환·교차 할당과 자원 상한은 계속 거부하며, 크기가 없는 v3 디렉터리 체인은 종결까지 검사한다. `raise_defects=DEFECT_INCORRECT`는 메타데이터까지 거부하지만 내장 압축 검증의 `strict_recovery=True`는 미사용 꼬리를 허용한다.

손상 WARN은 범위·스트림 경로·원인으로 구별한다. 외부는 `WARN: OLE/CFB 컨테이너 손상 복구:`, 내장은 `WARN: embedded OLE/CFB 컨테이너 손상 복구:`와 `ole번호/스트림` 경로를 쓴다. 같은 경로의 크기 초과·주소 범위 초과·짧은 체인·잘린 페이로드는 최초 진단 하나로 접는다. 세부 범주는 `parsing_issues`에 남는다. 자원 상한 예외는 `CFBResourceError`로 구별하며 `자원 제한` 접두어를 쓴다. 수집은 컨테이너당 경로·원인 16개, 문서 전달은 외부 16개와 내장 전체 16개로 각각 제한한다. 두 범위는 서로의 경고를 지우지 않는다. 경로는 256자로 제한하며 한도를 넘는 경로는 열거하지 않는다. 이전의 범주만으로 중복 제거한다는 설명은 폐기했다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 선언 범위 밖 FREESECT·순환이다. | POI `SimpleMultiCell.xls`의 공개 원본에서 두 변조본을 만들었다. | Workbook 4,096바이트·8섹터이며 FAT offset 12,828의 마지막 워드만 END에서 FREESECT 또는 첫 SID 0으로 바꿨다. 원본과 1.7.0 출력 해시가 정답이다. | 본문·JSON·errors를 보존해야 한다. | 2/2 원본 해시와 같고 errors=0이다. 직전판의 FREESECT errors=1과 순환 본문 소실/errors=2를 재현했다. | 실물 기반 변조 2/2 통과이다. 미변조 실물에서 결함을 발견했다는 주장은 하지 않는다. |
| 정상 출력 보존이다. | 공개 1,893개 및 메타데이터 편차 47개이다. | 1.7.0과 직전판의 직접 실행 해시이다. | 정상군의 세 출력 변화가 없어야 한다. | 정상군 1,741/1,741 및 별도 47/47이 1.7.0과 같다. | 검증 범위에서 100% 통과이다. |
| 손실 경고의 파생 진단을 접는다. | LO `hang-14.ppt` 및 공개 변동 표본 37개이다. | 직전판과 최종판 해시 및 바이트 감사이다. | 본문을 바꾸지 않고 진단을 정리해야 한다. | 37/37 Markdown이 같다. `hang-14.ppt`는 errors 4개가 2개로 줄었다. | 비교 범위에서 통과이다. |
| 내장·외부 경고 분리와 상한이다. | 두 손상이 겹친 미변조 실물은 확보하지 못했다. | 합성 Workbook·Regular 절단, BinData 100개, 내장 개체 40개이다. | 두 범위 경고를 보존하고 경로별 상한을 적용해야 한다. | 합성 테스트가 통과했다. | 구현 완료이며 결함별 실물 칸은 ⬜ 유지이다. |
| 자원 제한과 꼬리 예산이다. | 해당 경계의 미변조 실물은 확보하지 못했다. | 크기·단계 상한을 낮춘 입력과 미사용 꼬리 100섹터이다. | 상한을 손상으로 표시하지 않고 꼬리가 뒤 스트림 예산을 쓰지 않아야 한다. | 자원 제한 경고와 필요한 13단계만 쓰는 읽기를 확인했다. | 구현 완료이며 결함별 실물 칸은 ⬜ 유지이다. |
| HWP/HWPX 회귀이다. | 내부 실물 76쌍이다. | HWPX 정답지와 기존 비교 도구의 집계이다. | 직전 검증에서 회귀하지 않아야 한다. | 오류 쌍 0개, 토큰 비율 0.9997, 표 서명 0.9987, 셀 적중률 0.9991, 중첩·서식 1.0이다. | 기존 76쌍 집계와 같다. 내부 파일명과 내용은 기록하지 않았다. |

### 3차 검증과 기존 단언의 예외 근거

최초 새 재현 테스트는 25개 실패·1개 통과였다. 수정 후 전체 테스트는 **3,433 passed, 28 skipped, 14 xfailed**이며 28.63초였다. olefile import를 자식까지 차단한 실행은 **3,431 passed, 30 skipped, 14 xfailed**였다. 공개 절단 PPT 회귀 4개도 별도 통과했다. Ruff와 로컬 절대 경로 검사를 통과했다.

기존 `test_root_overallocated_chain_is_fully_checked_but_payload_is_sized`와 `test_regular_excess_chain_keeps_declared_extent_and_checks_cycles`는 선언 범위 밖 꼬리 순환을 기본 모드에서 거부하도록 요구해 이번 결함을 고정하고 있었다. 위 공개 XLS 변조와 [MS-CFB]의 선언 크기를 근거로 해당 거부 호출만 `raise_defects=DEFECT_INCORRECT`로 바꿨으며 기존 `assert`는 모두 보존했다. 기본 모드 보존은 새 regular·mini·MiniFAT 꼬리 테스트가 검증한다. 경고 테스트의 one/two 경로는 같은 범주라도 서로 달라야 하므로 기대 목록에 two를 추가했다. 이는 승인된 WARN 계약 변경이다. HWP `image_cycle` 픽스처는 9바이트로 한 섹터에서 끝나 기존 자기 순환이 미사용 꼬리였다. 선언 크기를 65바이트로 바꿔 실제 필요한 두 번째 섹터에서 순환하도록 했으며 본문·경고 단언은 그대로다. AST 비교 기록은 `r3-assertion-audit.json`이다.

공개 컨테이너 6,761개와 참조 olefile 재비교는 완전 일치 6,722개, 양쪽 열림·차이 20개, 참조만 열림 5개, 양쪽 거부 13개, 자체만 열림 1개로 직전과 같다. 양쪽에서 열린 기준 스트림 77,281개 중 77,252개의 바이트를 검증했다. 생략한 거대 스트림을 일치로 세지 않았다. 공개 입력 퍼즈 5,000회는 허용 4,715개·예상 거부 285개이며 예상 밖 예외·시간 초과·비정상 종료·메모리 제한 초과는 모두 0회였다. 최대 RSS는 42.38 MiB, 최장 처리 시간은 0.0253초였다. 초기 탐색의 넓은 루트 결과는 쓰지 않고 공개 여섯 루트만 지정한 재실행을 최종 수치로 삼았다.

잘린 암호 PPT `testPPT_protected_passtika.ppt`의 97% 입력에서 Current User가 사라져 암호문을 본문으로 읽는 문제는 Opus의 범위 밖 지적으로 기록만 한다. 1.7.0에도 있는 형식 계층 문제이며 이번 작업에서 수정 또는 재검증 완료라고 주장하지 않는다.

### 3차 재현 명령과 산출물

`corpus`는 읽기 전용 공개 코퍼스, `BASE170`은 `107e18d`, `PREVIOUS`는 `554ade6` 패키지의 별도 트리이다. 메타데이터 manifest의 47개 상대경로는 문서 끝에 나열했다. 비교 명령의 차이 81개·37개에 따른 종료 코드 1을 전체 동일 성공으로 취급하지 않는다.

```sh
/usr/bin/python3 -m scripts.probe_cfb_review snapshot corpus --tree BASE170 --selection opus --label 107e18d --jobs 4 --timeout 400 --memory-mb 7168 --output baseline.json
/usr/bin/python3 -m scripts.probe_cfb_review snapshot corpus --tree PREVIOUS --selection opus --label 554ade6 --jobs 4 --timeout 400 --memory-mb 7168 --output previous.json
/usr/bin/python3 -m scripts.probe_cfb_review snapshot corpus --tree . --selection opus --label native-cfb2-fix-r3 --jobs 4 --timeout 400 --memory-mb 7168 --output current.json
/usr/bin/python3 -m scripts.probe_cfb_review compare baseline.json current.json --corpus corpus --output vs-170.json
/usr/bin/python3 -m scripts.probe_cfb_review compare previous.json current.json --corpus corpus --output vs-previous.json
/usr/bin/python3 -m scripts.probe_cfb_review snapshot corpus --tree BASE170 --paths metadata-normal-paths.json --label 107e18d --output metadata-baseline.json
/usr/bin/python3 -m scripts.probe_cfb_review snapshot corpus --tree . --paths metadata-normal-paths.json --label native-cfb2-fix-r3 --output metadata-current.json
/usr/bin/python3 -m scripts.probe_cfb_review compare metadata-baseline.json metadata-current.json --corpus corpus --output metadata-vs-170.json
/usr/bin/python3 -m scripts.probe_cfb_tail_review corpus --baseline-tree BASE170 --previous-tree PREVIOUS --current-tree . --output tail.json
/usr/bin/python3 -m scripts.compare_cfb_olefile corpus/hwp-public/hwp corpus/poi-src/test-data/document corpus/poi-src/test-data/slideshow corpus/poi-src/test-data/spreadsheet corpus/lo-src corpus/tika-test-docs --mode compare --jobs 2 --timeout 30 --memory-mb 512 --output cfb-compare.json
/usr/bin/python3 -m scripts.compare_cfb_olefile corpus/hwp-public/hwp corpus/poi-src/test-data/document corpus/poi-src/test-data/slideshow corpus/poi-src/test-data/spreadsheet corpus/lo-src corpus/tika-test-docs --mode fuzz --iterations 5000 --seed 20261003 --jobs 2 --timeout 30 --memory-mb 512 --output fuzz.json
```

원시 기록은 `.codex-work/third-review/{summary,baseline-170,previous-554ade6,current,vs-170,vs-previous,metadata-baseline,metadata-current,metadata-vs-170,metadata-normal-paths,tail}.json`, `.codex-work/r3-{cfb-compare,fuzz,assertion-audit,hwp-pairs-summary}.json` 및 `r3-*-tests.log`에 있다. 공개 경로·해시·개수만 남기고 본문은 저장하지 않았다.

## 2차 이력: f9d0d50 대비 554ade6

이하 기존 본문은 2차 수정의 이력이며 위 3차 최종 판정과 구분한다.

2026년 10월 3일 `f9d0d50`을 기준선으로 두 독립 리뷰를 재현하고 수정했다. 이 작업은 공통 CFB 리더의 결함 수정이며 README 표시 요소를 새로 추가하지 않는다. README·CHANGELOG·uv.lock·AGENTS·의존성과 출력 모델은 수정하지 않았다. 구현 근거는 기존 Microsoft [MS-CFB] §2.2–2.6의 필드 해석과 합성·공개 실물의 원시 바이트이다. 네트워크와 다른 프로젝트의 구현 소스는 사용하지 않았다.

## 변경과 판정 경계

MiniFAT는 헤더가 선언한 섹터 개수까지만 소유권과 할당 워드로 사용한다. 초과 링크는 순환·범위 검증을 받지만 일반 스트림의 소유권을 빼앗거나 할당표가 되지 않는다. FAT 배열도 실제 파일의 섹터 수까지만 보관한다. 거대한 루트 크기는 실제 미니 스트림 접근 때 기존 256 MiB 상한을 적용하므로 일반 스트림을 가리지 않는다.

디렉터리 가지·항목 생략, 절단된 할당표·체인·본문, 주소 범위 초과와 선택 스트림 읽기 실패는 `append_recovery_warnings()` 하나에서 `WARN: OLE/CFB 컨테이너 손상 복구: <범주> (<경로>)`로 만든다. 문서당 같은 범주는 한 번만 내보내며 최대 16개, 경로는 최대 256자이다. HWP BinData의 순환·교차 할당 실패도 이 경로로 드러난다. 없는 선택 스트림을 조회한 사실만으로는 경고하지 않는다.

FAT 표식, 미사용 DIFAT 슬롯·종결자, 루트 이름, 여분 할당과 미사용 MiniFAT 개수 같은 메타데이터 편차는 기존 `parsing_issues`에만 남긴다. `raise_defects=DEFECT_INCORRECT`는 기존 테스트의 엄격 계약을 유지한다. 내장 OLE의 압축 프레이밍 검증은 별도 `strict_recovery=True`로 메타데이터 편차를 허용하고, 모든 스트림의 체인·실제 범위를 열어 주소 손상과 절단을 거부한다.

Byte Order의 0xFFFE는 고정 표식이며 섹터 주소 산식이 아니다. 기본 모드는 잘못된 표식에도 little-endian 필드 해석을 유지하고, 엄격 모드는 거부한다. 이를 주소 체계 손상으로 간주해 문서를 통째로 거부한 이전 판정은 철회한다. 대소문자 정규화 후 이름이 중복되면 먼저 탐색한 객체를 유지하고 나중 객체만 생략하며 손실 경고를 남긴다. 손상 전 작성자의 의도를 복원했다고 주장하지 않는다.

## 칸별 실물 판정

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 정상 문서 진단 보존 | 공개 POI·LO·Tika·HWP CFB 6,761개이다. | `f9d0d50`과 `554ade6`의 Markdown·JSON·errors 전체 문자열 SHA-256 및 변경 파일별 독립 주소 감사이다. | 정상 문서의 errors 변화가 없어야 한다. | 6,682개는 세 출력이 같다. 변화 79개 모두 주소·디렉터리·본문 범위 손상이며 정상 문서 변화는 0개이다. | 검증 범위에서 통과이다. |
| 디렉터리·절단 손실 WARN | LO `tdf168786.ppt`, `tdf168736-1.ppt`, `tdf105150.ppt`와 POI `41071.ppt`이다. | 원본 바이트를 각각 97%, 90%, 60%, 90% 길이로 자른 입력과 실제 리더의 errors이다. | 본문 일부가 반환되더라도 손상 경고가 있어야 한다. | 네 개 모두 공통 WARN을 반환한다. 원본 표본은 변경하지 않았다. | 4/4 통과이며 복원 본문의 의미 정확성은 입증하지 않는다. |
| Byte Order 표식의 관용 처리 | LO `ofz18414-1.doc`, `ofz18534-1.doc`, `ofz18554-1.doc`이다. | 헤더 offset 28의 0xFF20, 참조 API 스트림 목록·크기·해시와 기존 errors이다. | 표식만으로 거부하지 않고 별도 손상을 진단해야 한다. | 3/3 컨테이너가 참조와 같다. 합계 12개 스트림이 일치한다. 본문과 기존 오류도 3/3 같고 실제 손상 WARN이 추가된다. `ofz18534-1.doc`의 Markdown 6,590자를 다시 읽는다. | 해당 범위에서 통과이다. |
| MiniFAT 선언 밖 꼬리 | 이 결함을 그대로 가진 실물 표본은 확보하지 않았다. | 두 합성 할당표에서 일반 스트림 점유와 선언 밖 워드 사용을 각각 재현했다. | 일반 4,096바이트를 보존하고 선언 밖 mini sid 128의 데이터를 반환하지 않아야 한다. | 두 실패 테스트가 수정 후 통과했다. 전체 실물 회귀도 통과했다. | 구현은 완료했으며 결함별 실물 검증은 미검증이므로 ⬜ 유지이다. |
| 중복 이름·거대한 미사용 루트·FAT 메모리 상한 | 해당 경계 조건의 실물 표본은 별도 확보하지 않았다. | 합성 중복 이름, 256 MiB 초과 루트 선언과 240개 여분 FAT 섹터이다. | 다른 스트림을 유지하고 실제 섹터 수 이상의 FAT 워드를 보관하지 않아야 한다. | 해당 합성 테스트와 전체 실물 회귀가 통과했다. | 구현은 완료했으며 경계별 실물 검증은 미검증이다. |
| 내장 OLE의 메타데이터 허용·손실 거부 | 특수 프레이밍과 메타데이터 편차가 함께 있는 실물은 별도 검증하지 않았다. | zlib 체크섬을 뺀 합성 CFB의 FAT 표식 편차와 잘린 실제 페이로드이다. | 표식 편차는 허용하고 잘린 데이터는 거부해야 한다. | 두 합성 경로 모두 통과했다. | 구현은 완료했으며 해당 조합의 실물 검증은 미검증이다. |
| HWP 실물 회귀 | 내부 실물 76쌍이다. | HWPX를 정답지로 삼은 동일 비교 도구의 수정 전후 집계이다. | 새 오류나 구조·서식 회귀가 없어야 한다. | 양쪽 모두 오류 쌍 0개이며 평균 토큰 비율 0.9997, 표 서명 일치율 0.9987, 평균 셀 적중률 0.9991, 중첩·서식 일치율 1.0이다. | 전후 집계가 동일하다. 내부 파일명과 내용은 기록하지 않았다. |

6,682개를 모두 정상 문서라고 분류한 것은 아니다. 손상 표본도 출력이 같을 수 있다. 정상 문서 변화 0개라는 결론은 6,761개 전부의 출력을 비교한 뒤 변화 79개를 각각 독립 원시 바이트로 확인한 결과이다. 단순 Byte Order 편차나 불완전한 마지막 섹터 길이만으로 손상 판정을 내리지 않았다.

## 컨테이너·참조 변환·퍼즈

선택적 참조 `olefile`과 6,761개 컨테이너를 다시 비교했다. 완전 일치 6,722개, 양쪽 열림·차이 20개, 참조만 열림 5개, 양쪽 거부 13개, 자체 리더만 열림 1개이다. 양쪽에서 열린 기준 스트림 77,281개 중 77,252개의 크기·실제 길이·SHA-256이 검증됐다. Byte Order 때문에 남았던 세 컨테이너가 완전 일치로 바뀌었다. 기존 거대 스트림 비교 상한 등 잔여 차이를 성공으로 세지 않았다.

기존 형식별 최대 300개 추출도 다시 실행했다. 이 1,113개 표본에서 참조 대비 1,051개가 완전 일치하고 62개가 다르다. HWP는 300/300, DOC는 269/300, PPT는 187/213, XLS는 295/300이 일치한다. 차이에는 새 복구 경고가 포함되므로 이전의 경고 누락 상태와 숫자를 단순 비교하지 않는다. 첫 실행에서 자원 상한에 걸린 아홉 개는 참조와 자체 변환을 각각 6,144 MiB·240초 제한의 별도 프로세스로 재실행해 모두 검증했다. 이전의 “판정된 차이 23개”는 리뷰 전 1,113개 추출 표본에만 해당하며 전체 코퍼스 수치가 아니다.

시드 20261003으로 공개 컨테이너를 5,000회 변형했다. 4,715개는 열렸고 285개는 예상된 CFB 오류로 거부했다. 예상 밖 예외·시간 초과·프로세스 비정상 종료·메모리 상한 초과는 모두 0회이다. 최대 자식 RSS는 43.05 MiB, 최장 입력 처리 시간은 0.0401초였다. 이 관찰을 모든 악성 입력의 안전성 증명으로 확대하지 않는다.

## 테스트와 재현

최초 코어 재현은 9개 실패, 리더 전달 재현은 14개 실패였다. 없는 선택 스트림의 오탐, 참조 비교용 키워드 변환과 내장 OLE 절단 검사도 추가 실패 테스트 뒤 수정했다. 전체 테스트는 3,403 passed, 28 skipped, 14 xfailed이며, olefile import를 자식까지 차단한 실행은 3,401 passed, 30 skipped, 14 xfailed이다. 네 실물 PPT 회귀는 별도 실행에서 4 passed이다. 기존 HEAD에서 수정된 테스트 파일의 함수 8개·assert 20개는 AST가 모두 같다. 기존 단언을 완화하지 않았다.

첫 전체 테스트는 검증 스크립트의 메모리 상한 API를 편집하는 동안 실행해 구버전 함수와 신버전 테스트가 섞여 한 개 실패했다. 파일을 고정한 재실행으로 해결했으며 이를 파서 실패로 숨기거나 통과로 세지 않았다. Ruff 전체 검사와 공백 검사도 통과했다.

아래 명령의 `corpus`는 외부 공개 코퍼스 경로이며, `BASELINE_TREE`는 `f9d0d50`의 dochan 패키지를 별도로 둔 경로이다. 전체 출력 비교는 메모리가 큰 XLS를 포함하므로 재현 명령에 6 GiB 상한을 명시한다.

```sh
/usr/bin/python3 -m scripts.probe_cfb_review snapshot corpus --tree BASELINE_TREE --output baseline.json --jobs 2 --memory-mb 6144 --timeout 240
/usr/bin/python3 -m scripts.probe_cfb_review snapshot corpus --tree . --output current.json --jobs 2 --memory-mb 6144 --timeout 240
/usr/bin/python3 -m scripts.probe_cfb_review compare baseline.json current.json --corpus corpus --output diff.json
DOCHAN_CORPUS_ROOT=corpus /usr/bin/python3 -m pytest tests/test_cfb_reader_warnings.py -k real_truncated -q -p no:cacheprovider
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

원시 증거는 `.codex-work/review-output-diff.json`, 두 `review-*-outputs.json`, 두 XLS 재실행 기록, `review-cfb-compare.json`, `review-reference-convert-final.json`, `review-reference-retries.json`, `review-byte-order.json`, `review-fuzz.json`, `review-assertions.json`과 테스트 로그에 있다. 파일명·본문을 포함하는 내부 자료는 산출물에 저장하지 않았다.

## 2차 이력: f9d0d50 대비 554ade6 출력 비교와 변경 파일 79개

`f9d0d50`과 `554ade6`의 Markdown·JSON·errors 전체 문자열 SHA-256을 비교했다. 6,761개 모두 완료했고, 처음 1,536 MiB를 초과한 XLS 13개는 6,144 MiB·240초로 각각 다시 실행해 모두 검증했다. 6,682개는 세 출력이 같고, 79개는 errors와 JSON이 달랐다. Markdown은 ofz18534-1.doc 한 개만 달랐다. 변경 79개는 모두 독립 바이트 감사에서 주소·디렉터리·본문 범위의 손상이 확인되었다. 바이트 순서 표식과 불완전한 마지막 섹터 크기만으로는 손상으로 판정하지 않았다.

| 공개 코퍼스 | 전체 | 세 출력 일치 | errors 변화 |
|---|---:|---:|---:|
| hwp-public | 5389 | 5389 | 0 |
| lo-src | 635 | 585 | 50 |
| poi-src/test-data/document | 162 | 155 | 7 |
| poi-src/test-data/slideshow | 145 | 135 | 10 |
| poi-src/test-data/spreadsheet | 420 | 408 | 12 |
| tika-test-docs | 10 | 10 | 0 |

세부 숫자와 모든 감사 소견은 `.codex-work/review-output-diff.json`에 기록했다. 아래의 entry 번호와 sector 번호는 MS-CFB 디렉터리·섹터의 원시 주소이며 문서 본문을 포함하지 않는다.

| 공개 파일 | 변화 | errors 개수(전→후) | 독립 바이트 근거 |
|---|---|---:|---|
| `lo-src/sc/qa/unit/data/xls/pass/ofz14120-1.xls` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 4278190091, "sector_bound": 11, "table_words": 1408, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 4278190089, "sector_bound": 11, "table_words": 1408, "visited": 6}` |
| `lo-src/sc/qa/unit/data/xls/pass/ofz5527-1.xls` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 4278190093, "sector_bound": 13, "table_words": 1664, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 538976288, "sector_bound": 13, "table_words": 1664, "visited": 1}` |
| `lo-src/sd/qa/unit/data/ppt/pass/crash-3.ppt` | json, errors | 0→1 | `{"code": "directory_outside", "entry": 4294967042, "entry_count": 8}; {"code": "directory_outside", "entry": 227, "entry_count": 8}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-10.ppt` | json, errors | 0→1 | `{"actual": 0, "code": "directory_name_length", "entry": 4}; {"actual": 0, "code": "directory_type", "entry": 4}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-14.ppt` | json, errors | 1→4 | `{"code": "allocation_outside", "mini": true, "owner": "entry:3", "sector": 4294967113, "sector_bound": 78, "table_words": 128, "visited": 5}; {"code": "allocation_outside", "mini": true, "owner": "entry:4", "sector": 4294967295, "sector_bound": 78, "table_words": 128, "visited": 1}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-15.ppt` | json, errors | 1→4 | `{"code": "allocation_outside", "mini": true, "owner": "entry:1", "sector": 229, "sector_bound": 78, "table_words": 128, "visited": 7}; {"actual": 7, "code": "chain_length", "expected": 60, "mini": true, "owner": "entry:1", "terminator": 229}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-16.ppt` | json, errors | 0→1 | `{"actual": 0, "code": "directory_name_length", "entry": 4}; {"actual": 0, "code": "directory_type", "entry": 4}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-17.ppt` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": true, "owner": "entry:1", "sector": 318767133, "sector_bound": 78, "table_words": 128, "visited": 29}; {"actual": 29, "code": "chain_length", "expected": 60, "mini": true, "owner": "entry:1", "terminator": 318767133}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-2.ppt` | json, errors | 1→4 | `{"code": "allocation_outside", "mini": true, "owner": "entry:1", "sector": 32825, "sector_bound": 78, "table_words": 128, "visited": 57}; {"actual": 57, "code": "chain_length", "expected": 60, "mini": true, "owner": "entry:1", "terminator": 32825}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-20.ppt` | json, errors | 0→1 | `{"actual": 0, "code": "directory_name_length", "entry": 4}; {"actual": 0, "code": "directory_type", "entry": 4}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-21.ppt` | json, errors | 0→1 | `{"code": "allocation_outside", "mini": true, "owner": "entry:3", "sector": 4293460040, "sector_bound": 78, "table_words": 128, "visited": 4}; {"actual": 0, "code": "directory_name_length", "entry": 4}` |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-7.ppt` | json, errors | 0→1 | `{"actual": 0, "code": "directory_name_length", "entry": 4}; {"actual": 0, "code": "directory_type", "entry": 4}` |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz14989-1.ppt` | json, errors | 1→2 | `{"code": "directory_outside", "entry": 5, "entry_count": 5}` |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz21531-1.ppt` | json, errors | 2→5 | `{"code": "allocation_outside", "mini": true, "owner": "entry:5", "sector": 4278976510, "sector_bound": 68, "table_words": 128, "visited": 1}; {"available": 47, "code": "payload_truncated", "entry": 5, "mini": true, "offset": 35520, "requested": 56, "sector": 67}` |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz37370-1.ppt` | json, errors | 1→6 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 16, "sector_bound": 8, "table_words": 128, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 1966348, "sector_bound": 8, "table_words": 128, "visited": 0}` |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz43902-1.ppt` | json, errors | 0→4 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 134217771, "sector_bound": 85, "table_words": 128, "visited": 1}; {"actual": 0, "code": "directory_name_length", "entry": 4}` |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz7469-leak-1.ppt` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 4294967072, "sector_bound": 8, "table_words": 1024, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 538976288, "sector_bound": 8, "table_words": 1024, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww6/fail/ofz45140-1.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 16252935, "sector_bound": 7, "table_words": 128, "visited": 4}; {"code": "allocation_outside", "mini": true, "owner": "entry:1", "sector": 1279524864, "sector_bound": 39, "table_words": 128, "visited": 22}` |
| `lo-src/sw/qa/core/data/ww6/pass/crash-1.doc` | json, errors | 1→6 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 3301229764, "sector_bound": 12, "table_words": 128, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 3301229764, "sector_bound": 12, "table_words": 128, "visited": 1}` |
| `lo-src/sw/qa/core/data/ww6/pass/crash-3.doc` | json, errors | 0→1 | `{"code": "directory_outside", "entry": 65530, "entry_count": 8}` |
| `lo-src/sw/qa/core/data/ww6/pass/crash-4.doc` | json, errors | 1→2 | `{"actual": 52, "code": "chain_length", "expected": 61, "mini": true, "owner": "entry:2", "terminator": 31}; {"code": "allocation_cycle", "mini": true, "owner": "entry:2", "sector": 31, "visited": 52}` |
| `lo-src/sw/qa/core/data/ww6/pass/crash-5.doc` | json, errors | 0→1 | `{"code": "directory_outside", "entry": 65530, "entry_count": 8}` |
| `lo-src/sw/qa/core/data/ww6/pass/crash-7.doc` | json, errors | 1→4 | `{"available": 36, "code": "payload_truncated", "entry": 2, "mini": true, "offset": 6464, "requested": 64, "sector": 61}` |
| `lo-src/sw/qa/core/data/ww6/pass/hang-1.doc` | json, errors | 1→2 | `{"actual": 35, "code": "chain_length", "expected": 61, "mini": true, "owner": "entry:2", "terminator": 17}; {"code": "allocation_cycle", "mini": true, "owner": "entry:2", "sector": 17, "visited": 35}` |
| `lo-src/sw/qa/core/data/ww6/pass/ofz-redlining-1.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 70, "sector_bound": 68, "table_words": 8704, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 69, "sector_bound": 68, "table_words": 8704, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww6/pass/ofz-trailingpara.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 70, "sector_bound": 68, "table_words": 8704, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 69, "sector_bound": 68, "table_words": 8704, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww6/pass/ofz21168-1.doc` | json, errors | 0→4 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 70, "sector_bound": 68, "table_words": 128, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 69, "sector_bound": 68, "table_words": 128, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww6/pass/ofz21385-1.doc` | json, errors | 0→1 | `{"code": "directory_outside", "entry": 4278255615, "entry_count": 188}` |
| `lo-src/sw/qa/core/data/ww6/pass/ofz34898-1.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 7, "sector_bound": 7, "table_words": 896, "visited": 3}; {"code": "allocation_outside", "mini": false, "owner": "MiniFAT", "sector": 7, "sector_bound": 7, "table_words": 896, "visited": 2}` |
| `lo-src/sw/qa/core/data/ww6/pass/ofz41398-1.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 6, "sector_bound": 6, "table_words": 128, "visited": 3}; {"code": "allocation_outside", "mini": true, "owner": "entry:1", "sector": 1279524864, "sector_bound": 39, "table_words": 128, "visited": 22}` |
| `lo-src/sw/qa/core/data/ww6/pass/ofz42330-1.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 6, "sector_bound": 6, "table_words": 128, "visited": 3}; {"code": "allocation_outside", "mini": true, "owner": "entry:1", "sector": 1279524864, "sector_bound": 39, "table_words": 128, "visited": 22}` |
| `lo-src/sw/qa/core/data/ww8/fail/hang-2.doc` | json, errors | 1→2 | `{"actual": 14, "code": "chain_length", "expected": 4194182, "mini": false, "owner": "entry:3", "terminator": 4294967294}; {"actual": 1, "code": "chain_length", "expected": 57, "mini": true, "owner": "entry:5", "terminator": 50}` |
| `lo-src/sw/qa/core/data/ww8/fail/redline-1.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 4294967072, "sector_bound": 16, "table_words": 2048, "visited": 2}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 4294967072, "sector_bound": 16, "table_words": 2048, "visited": 11}` |
| `lo-src/sw/qa/core/data/ww8/pass/crash-2.doc` | json, errors | 1→2 | `{"actual": 14, "code": "chain_length", "expected": 41, "mini": true, "owner": "entry:3", "terminator": 16}; {"actual": 7, "code": "chain_length", "expected": 57, "mini": true, "owner": "entry:5", "terminator": 16}` |
| `lo-src/sw/qa/core/data/ww8/pass/forcepoint50-grfanchor-1.doc` | json, errors | 1→3 | `{"actual": 88, "code": "chain_length", "expected": 96, "mini": false, "owner": "entry:3", "terminator": 4294967294}` |
| `lo-src/sw/qa/core/data/ww8/pass/hang-1.doc` | json, errors | 1→3 | `{"actual": 38, "code": "chain_length", "expected": 41, "mini": true, "owner": "entry:3", "terminator": 4294967294}` |
| `lo-src/sw/qa/core/data/ww8/pass/hang-2.doc` | json, errors | 1→2 | `{"code": "allocation_outside", "mini": true, "owner": "entry:3", "sector": 58915, "sector_bound": 109, "table_words": 128, "visited": 32}; {"actual": 32, "code": "chain_length", "expected": 41, "mini": true, "owner": "entry:3", "terminator": 58915}` |
| `lo-src/sw/qa/core/data/ww8/pass/hang-3.doc` | json, errors | 1→4 | `{"code": "allocation_outside", "mini": true, "owner": "entry:3", "sector": 16318296, "sector_bound": 109, "table_words": 128, "visited": 41}; {"code": "allocation_outside", "mini": true, "owner": "entry:5", "sector": 16318296, "sector_bound": 109, "table_words": 128, "visited": 39}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz18414-1.doc` | json, errors | 1→4 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 117, "sector_bound": 116, "table_words": 128, "visited": 0}; {"code": "allocation_outside", "mini": false, "owner": "MiniFAT", "sector": 116, "sector_bound": 116, "table_words": 128, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz18534-1.doc` | markdown, json, errors | 1→4 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 96, "sector_bound": 96, "table_words": 128, "visited": 2}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 98, "sector_bound": 96, "table_words": 128, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz18554-1.doc` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 4294967295, "sector_bound": 45, "table_words": 128, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 63, "sector_bound": 45, "table_words": 128, "visited": 3}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz19065.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 72, "sector_bound": 71, "table_words": 128, "visited": 0}; {"code": "allocation_outside", "mini": false, "owner": "MiniFAT", "sector": 71, "sector_bound": 71, "table_words": 128, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz34749-1.doc` | json, errors | 0→4 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 352, "sector_bound": 96, "table_words": 128, "visited": 2}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 98, "sector_bound": 96, "table_words": 128, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz38011-1.doc` | json, errors | 19→23 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 124, "sector_bound": 123, "table_words": 128, "visited": 0}; {"code": "allocation_outside", "mini": false, "owner": "MiniFAT", "sector": 123, "sector_bound": 123, "table_words": 128, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz46457-1.doc` | json, errors | 1→7 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 46, "sector_bound": 34, "table_words": 4352, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 63, "sector_bound": 34, "table_words": 4352, "visited": 3}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz47205-1.doc` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 71, "sector_bound": 54, "table_words": 128, "visited": 0}; {"code": "allocation_outside", "mini": false, "owner": "MiniFAT", "sector": 62, "sector_bound": 54, "table_words": 128, "visited": 0}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz53457-1.doc` | json, errors | 1→7 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 46, "sector_bound": 34, "table_words": 4352, "visited": 1}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 63, "sector_bound": 34, "table_words": 4352, "visited": 3}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz57592-1.doc` | json, errors | 4→5 | `{"code": "directory_outside", "entry": 7, "entry_count": 7}` |
| `lo-src/sw/qa/core/data/ww8/pass/ofz7322-1.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "directory", "sector": 96, "sector_bound": 96, "table_words": 12288, "visited": 2}; {"code": "allocation_outside", "mini": false, "owner": "root", "sector": 98, "sector_bound": 96, "table_words": 12288, "visited": 0}` |
| `lo-src/sw/qa/filter/ww8/data/ofz-delflyinrange-1.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 6, "sector_bound": 6, "table_words": 128, "visited": 3}; {"code": "allocation_outside", "mini": true, "owner": "entry:1", "sector": 4115, "sector_bound": 39, "table_words": 128, "visited": 19}` |
| `poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` | json, errors | 11→14 | `{"code": "allocation_outside", "mini": false, "owner": "entry:4", "sector": 822083920, "sector_bound": 91, "table_words": 128, "visited": 0}; {"code": "directory_outside", "entry": 47231010, "entry_count": 8}` |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-4892412469968896.doc` | json, errors | 0→1 | `{"code": "directory_outside", "entry": 4160749575, "entry_count": 16}` |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5074346559012864.doc` | json, errors | 0→1 | `{"code": "directory_outside", "entry": 4294967040, "entry_count": 8}; {"actual": 14336, "code": "directory_name_length", "entry": 6}` |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc` | json, errors | 12→15 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 111, "sector_bound": 111, "table_words": 128, "visited": 0}; {"code": "allocation_outside", "mini": true, "owner": "entry:5", "sector": 808468802, "sector_bound": 2, "table_words": 128, "visited": 1}` |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5418937293340672.doc` | json, errors | 1→2 | `{"actual": 0, "code": "directory_name_length", "entry": 2}` |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5440721166139392.doc` | json, errors | 4→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:7", "sector": 4294967295, "sector_bound": 35, "table_words": 128, "visited": 1}; {"code": "directory_outside", "entry": 4294935010, "entry_count": 8}` |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5832867957309440.doc` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 25, "sector_bound": 9, "table_words": 128, "visited": 5}; {"code": "allocation_outside", "mini": true, "owner": "entry:2", "sector": 50, "sector_bound": 49, "table_words": 128, "visited": 2}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIFuzzer-5429732352851968.ppt` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:2", "sector": 16, "sector_bound": 16, "table_words": 128, "visited": 9}; {"available": 356, "code": "payload_truncated", "entry": 2, "mini": false, "offset": 8192, "requested": 512, "sector": 15}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4624961081573376.ppt` | json, errors | 1→2 | `{"code": "directory_outside", "entry": 1566399837, "entry_count": 12}; {"code": "directory_outside", "entry": 4294967133, "entry_count": 12}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4983252485210112.ppt` | json, errors | 1→6 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 21, "sector_bound": 17, "table_words": 128, "visited": 2}; {"code": "allocation_outside", "mini": true, "owner": "entry:2", "sector": 234881536, "sector_bound": 262174, "table_words": 128, "visited": 1}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5018229722382336.ppt` | json, errors | 1→4 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 21, "sector_bound": 17, "table_words": 128, "visited": 2}; {"actual": 2, "code": "chain_length", "expected": 4, "mini": false, "owner": "root", "terminator": 21}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt` | json, errors | 8→9 | `{"code": "allocation_outside", "mini": false, "owner": "entry:3", "sector": 8388612, "sector_bound": 163, "table_words": 256, "visited": 8}; {"code": "directory_outside", "entry": 4294967042, "entry_count": 8}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6192650357112832.ppt` | json, errors | 1→4 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 21, "sector_bound": 17, "table_words": 128, "visited": 2}; {"actual": 2, "code": "chain_length", "expected": 4, "mini": false, "owner": "root", "terminator": 21}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6360479850954752.ppt` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 21, "sector_bound": 18, "table_words": 128, "visited": 2}; {"code": "allocation_outside", "mini": true, "owner": "entry:2", "sector": 150994952, "sector_bound": 30, "table_words": 128, "visited": 8}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6416153805979648.ppt` | json, errors | 1→2 | `{"code": "allocation_outside", "mini": true, "owner": "entry:4", "sector": 4026531838, "sector_bound": 28, "table_words": 128, "visited": 1}; {"actual": 111, "code": "directory_name_terminator", "entry": 3}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6614960949821440.ppt` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 14, "sector_bound": 14, "table_words": 128, "visited": 1}; {"code": "allocation_outside", "mini": true, "owner": "entry:2", "sector": 7274578, "sector_bound": 30, "table_words": 256, "visited": 1}` |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6710128412590080.ppt` | json, errors | 1→2 | `{"code": "directory_outside", "entry": 137216, "entry_count": 8}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4651309315719168.xls` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 124, "sector_bound": 16, "table_words": 128, "visited": 0}; {"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 20, "sector_bound": 16, "table_words": 128, "visited": 11}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4657005060816896.xls` | json, errors | 2→3 | `{"code": "allocation_outside", "mini": true, "owner": "entry:2", "sector": 65536, "sector_bound": 11, "table_words": 128, "visited": 1}; {"code": "allocation_outside", "mini": true, "owner": "entry:3", "sector": 393215, "sector_bound": 11, "table_words": 128, "visited": 1}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4734163573080064.xls` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 13, "sector_bound": 13, "table_words": 128, "visited": 11}; {"actual": 0, "code": "chain_length", "expected": 16384, "mini": false, "owner": "root", "terminator": 4294967294}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4819588401201152.xls` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 6, "sector_bound": 6, "table_words": 128, "visited": 4}; {"available": 110, "code": "payload_truncated", "entry": 1, "mini": false, "offset": 3072, "requested": 512, "sector": 5}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5175219985448960.xls` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "root", "sector": 79, "sector_bound": 52, "table_words": 128, "visited": 11}; {"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 52, "sector_bound": 52, "table_words": 128, "visited": 1}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5786329142919168.xls` | json, errors | 1→2 | `{"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 27, "sector_bound": 27, "table_words": 128, "visited": 25}; {"actual": 19, "code": "directory_name_length", "entry": 1}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5889658057523200.xls` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 26, "sector_bound": 26, "table_words": 128, "visited": 24}; {"available": 50, "code": "payload_truncated", "entry": 1, "mini": false, "offset": 13312, "requested": 512, "sector": 25}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6137883240824832.xls` | json, errors | 1→1 | `{"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 3, "sector_bound": 3, "table_words": 128, "visited": 1}; {"available": 127, "code": "payload_truncated", "entry": 1, "mini": false, "offset": 1536, "requested": 512, "sector": 2}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6322470200934400.xls` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 6, "sector_bound": 6, "table_words": 128, "visited": 4}; {"available": 275, "code": "payload_truncated", "entry": 1, "mini": false, "offset": 3072, "requested": 512, "sector": 5}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6483562584932352.xls` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 25, "sector_bound": 25, "table_words": 128, "visited": 18}; {"available": 334, "code": "payload_truncated", "entry": 1, "mini": false, "offset": 12800, "requested": 512, "sector": 24}` |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6537773940867072.xls` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:1", "sector": 3, "sector_bound": 3, "table_words": 128, "visited": 1}; {"available": 246, "code": "payload_truncated", "entry": 1, "mini": false, "offset": 1536, "requested": 512, "sector": 2}` |
| `poi-src/test-data/spreadsheet/crash-9bf3cd4bd6f50a8a9339d363c2c7af14b536865c.xlsx` | json, errors | 1→5 | `{"code": "allocation_outside", "mini": false, "owner": "entry:2", "sector": 16, "sector_bound": 16, "table_words": 128, "visited": 9}; {"available": 356, "code": "payload_truncated", "entry": 2, "mini": false, "offset": 8192, "requested": 512, "sector": 15}` |

## 3차 부록: 1.7.0 대비 변화 81개

errors는 1.7.0에서 최종판으로의 변화이다. 직전 변화 37개를 별도 표시했다. 각 행은 독립 바이트 감사에서 손상을 확인했으며 전체 근거는 `vs-170.json`에 있다.

| 공개 표본 | 변화 | errors | 직전 변화 | 원시 손상 근거 |
| --- | --- | ---: | --- | --- |
| `lo-src/sc/qa/unit/data/xls/pass/ofz14120-1.xls` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, difat_fat_count, difat_missing_slot, directory_type, fat_sector_truncated_or_outside |
| `lo-src/sc/qa/unit/data/xls/pass/ofz5527-1.xls` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, difat_fat_count, difat_missing_slot, directory_outside, fat_sector_truncated_or_outside |
| `lo-src/sd/qa/unit/data/ppt/pass/crash-3.ppt` | json, errors | 0→1 | 없음 | directory_outside |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-10.ppt` | json, errors | 0→1 | 없음 | directory_cycle_or_crosslink, directory_name_length, directory_type |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-14.ppt` | json, errors | 1→2 | 있음 | allocation_outside, chain_length |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-15.ppt` | json, errors | 1→2 | 있음 | allocation_outside, chain_length |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-16.ppt` | json, errors | 0→1 | 없음 | directory_cycle_or_crosslink, directory_name_length, directory_type |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-17.ppt` | json, errors | 1→3 | 있음 | allocation_outside, chain_length, directory_name_utf16 |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-18.ppt` | markdown, json, errors | 1→1 | 없음 | directory_type |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-2.ppt` | json, errors | 1→2 | 있음 | allocation_outside, chain_length |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-20.ppt` | json, errors | 0→1 | 없음 | directory_cycle_or_crosslink, directory_name_length, directory_type |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-21.ppt` | json, errors | 0→1 | 없음 | allocation_outside, chain_length, directory_cycle_or_crosslink, directory_name_length, directory_type |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-7.ppt` | json, errors | 0→1 | 없음 | directory_cycle_or_crosslink, directory_name_length, directory_type |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz14989-1.ppt` | json, errors | 1→2 | 없음 | directory_outside |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz21531-1.ppt` | json, errors | 1→5 | 있음 | allocation_cycle, allocation_outside, chain_length, payload_truncated |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz37370-1.ppt` | json, errors | 1→4 | 있음 | allocation_outside, chain_length, directory_outside, payload_truncated |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz43902-1.ppt` | json, errors | 0→2 | 있음 | allocation_outside, chain_length, directory_cycle_or_crosslink, directory_name_length, directory_type, mini_payload_outside_root_chain |
| `lo-src/sd/qa/unit/data/ppt/pass/ofz7469-leak-1.ppt` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, difat_fat_count, difat_missing_slot, directory_type, fat_sector_truncated_or_outside |
| `lo-src/sw/qa/core/data/ww6/fail/ofz45140-1.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, directory_outside |
| `lo-src/sw/qa/core/data/ww6/pass/crash-1.doc` | json, errors | 1→4 | 있음 | allocation_outside, chain_length, directory_outside, mini_payload_outside_root_chain |
| `lo-src/sw/qa/core/data/ww6/pass/crash-3.doc` | json, errors | 0→1 | 없음 | directory_outside |
| `lo-src/sw/qa/core/data/ww6/pass/crash-4.doc` | markdown, json, errors | 0→2 | 없음 | allocation_cycle, chain_length |
| `lo-src/sw/qa/core/data/ww6/pass/crash-5.doc` | json, errors | 0→1 | 없음 | directory_outside |
| `lo-src/sw/qa/core/data/ww6/pass/crash-7.doc` | json, errors | 1→3 | 있음 | payload_truncated |
| `lo-src/sw/qa/core/data/ww6/pass/hang-1.doc` | markdown, json, errors | 0→2 | 없음 | allocation_cycle, chain_length |
| `lo-src/sw/qa/core/data/ww6/pass/ofz-redlining-1.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, difat_fat_count, difat_missing_slot, directory_outside, fat_sector_truncated_or_outside |
| `lo-src/sw/qa/core/data/ww6/pass/ofz-trailingpara.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, difat_fat_count, difat_missing_slot, directory_outside, fat_sector_truncated_or_outside |
| `lo-src/sw/qa/core/data/ww6/pass/ofz21168-1.doc` | json, errors | 0→2 | 있음 | allocation_outside, chain_length, directory_outside |
| `lo-src/sw/qa/core/data/ww6/pass/ofz21385-1.doc` | json, errors | 0→1 | 없음 | directory_outside |
| `lo-src/sw/qa/core/data/ww6/pass/ofz34898-1.doc` | json, errors | 1→1 | 없음 | allocation_crosslink, allocation_outside, chain_length, cutoff, difat_fat_count, difat_missing_slot, directory_outside, fat_sector_truncated_or_outside, mini_payload_outside_root_chain, mini_shift |
| `lo-src/sw/qa/core/data/ww6/pass/ofz41398-1.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, directory_outside, payload_truncated |
| `lo-src/sw/qa/core/data/ww6/pass/ofz42330-1.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, directory_outside, payload_truncated |
| `lo-src/sw/qa/core/data/ww8/fail/hang-2.doc` | json, errors | 1→2 | 없음 | allocation_crosslink, allocation_cycle, chain_length, native_stream_size_limit |
| `lo-src/sw/qa/core/data/ww8/fail/redline-1.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, difat_fat_count, difat_missing_slot, directory_outside, fat_sector_truncated_or_outside |
| `lo-src/sw/qa/core/data/ww8/pass/crash-2.doc` | json, errors | 2→2 | 없음 | allocation_crosslink, allocation_cycle, chain_length |
| `lo-src/sw/qa/core/data/ww8/pass/forcepoint50-grfanchor-1.doc` | json, errors | 1→2 | 있음 | chain_length |
| `lo-src/sw/qa/core/data/ww8/pass/hang-1.doc` | json, errors | 1→2 | 있음 | chain_length |
| `lo-src/sw/qa/core/data/ww8/pass/hang-2.doc` | json, errors | 1→2 | 없음 | allocation_outside, chain_length, directory_type |
| `lo-src/sw/qa/core/data/ww8/pass/hang-3.doc` | json, errors | 1→2 | 있음 | allocation_crosslink, allocation_outside, chain_length |
| `lo-src/sw/qa/core/data/ww8/pass/ofz18414-1.doc` | json, errors | 1→3 | 있음 | allocation_outside, chain_length |
| `lo-src/sw/qa/core/data/ww8/pass/ofz18534-1.doc` | json, errors | 0→2 | 있음 | allocation_outside, chain_length, directory_outside |
| `lo-src/sw/qa/core/data/ww8/pass/ofz18554-1.doc` | json, errors | 1→4 | 있음 | allocation_outside, chain_length, directory_outside, payload_truncated |
| `lo-src/sw/qa/core/data/ww8/pass/ofz19065.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, directory_outside |
| `lo-src/sw/qa/core/data/ww8/pass/ofz34749-1.doc` | json, errors | 0→2 | 있음 | allocation_outside, chain_length, directory_outside |
| `lo-src/sw/qa/core/data/ww8/pass/ofz38011-1.doc` | json, errors | 19→21 | 있음 | allocation_outside, chain_length, directory_outside |
| `lo-src/sw/qa/core/data/ww8/pass/ofz46457-1.doc` | json, errors | 1→5 | 있음 | allocation_crosslink, allocation_cycle, allocation_outside, chain_length, difat_missing_slot, directory_name_terminator, directory_outside, fat_sector_truncated_or_outside, payload_truncated |
| `lo-src/sw/qa/core/data/ww8/pass/ofz47205-1.doc` | json, errors | 1→3 | 있음 | allocation_outside, chain_length |
| `lo-src/sw/qa/core/data/ww8/pass/ofz53457-1.doc` | json, errors | 1→5 | 있음 | allocation_crosslink, allocation_outside, chain_length, difat_missing_slot, directory_name_terminator, directory_outside, fat_sector_truncated_or_outside, payload_truncated |
| `lo-src/sw/qa/core/data/ww8/pass/ofz57592-1.doc` | json, errors | 4→5 | 없음 | directory_outside |
| `lo-src/sw/qa/core/data/ww8/pass/ofz7322-1.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, difat_fat_count, difat_missing_slot, directory_outside, fat_sector_truncated_or_outside |
| `lo-src/sw/qa/filter/ww8/data/ofz-delflyinrange-1.doc` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, cutoff, difat_cycle_or_outside, directory_outside |
| `poi-src/test-data/document/clusterfuzz-testcase-POIHWPFFuzzer-5696094627495936.doc` | json, errors | 11→13 | 있음 | allocation_outside, chain_length, directory_name_empty_or_nul, directory_name_length, directory_name_terminator, directory_outside, directory_type, native_stream_size_limit |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-4892412469968896.doc` | json, errors | 0→1 | 없음 | directory_outside |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5074346559012864.doc` | json, errors | 0→1 | 없음 | directory_name_length, directory_outside, directory_type |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5195207308541952.doc` | json, errors | 12→13 | 있음 | allocation_outside, chain_length, mini_payload_outside_root_chain |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5418937293340672.doc` | json, errors | 1→2 | 없음 | directory_name_length |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5440721166139392.doc` | json, errors | 4→5 | 없음 | allocation_outside, chain_length, directory_outside |
| `poi-src/test-data/document/clusterfuzz-testcase-minimized-POIHWPFFuzzer-5832867957309440.doc` | json, errors | 1→1 | 없음 | allocation_crosslink, allocation_outside, chain_length, directory_name_terminator, directory_outside, mini_shift |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIFuzzer-5429732352851968.ppt` | json, errors | 1→2 | 있음 | allocation_outside, chain_length, payload_truncated |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4624961081573376.ppt` | json, errors | 1→2 | 없음 | directory_name_length, directory_outside, directory_type |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-4983252485210112.ppt` | json, errors | 1→4 | 있음 | allocation_outside, chain_length, directory_name_terminator, mini_payload_outside_root_chain |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-5018229722382336.ppt` | json, errors | 1→3 | 있음 | allocation_crosslink, allocation_cycle, allocation_outside, chain_length, mini_payload_outside_root_chain |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6032591399288832.ppt` | json, errors | 8→9 | 없음 | allocation_outside, directory_outside |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6192650357112832.ppt` | json, errors | 1→3 | 있음 | allocation_crosslink, allocation_cycle, allocation_outside, chain_length, mini_payload_outside_root_chain |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6360479850954752.ppt` | json, errors | 1→4 | 있음 | allocation_outside, chain_length, directory_name_length, mini_payload_outside_root_chain |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6416153805979648.ppt` | json, errors | 1→2 | 없음 | allocation_outside, directory_name_terminator |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6614960949821440.ppt` | markdown, json, errors | 1→1 | 없음 | allocation_crosslink, allocation_outside, chain_length, cutoff, directory_outside, mini_payload_outside_root_chain |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6710128412590080.ppt` | json, errors | 1→2 | 없음 | directory_outside |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4651309315719168.xls` | json, errors | 1→3 | 있음 | allocation_outside, chain_length, directory_cycle_or_crosslink, directory_name_length, directory_type |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4657005060816896.xls` | json, errors | 2→3 | 없음 | allocation_outside, chain_length, directory_name_length, directory_outside, directory_type |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4734163573080064.xls` | json, errors | 1→3 | 있음 | allocation_outside, chain_length |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-4819588401201152.xls` | json, errors | 1→2 | 있음 | allocation_outside, chain_length, payload_truncated |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5175219985448960.xls` | json, errors | 1→4 | 있음 | allocation_outside, chain_length, directory_cycle_or_crosslink, directory_name_length, directory_outside, directory_type, payload_truncated |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5786329142919168.xls` | json, errors | 1→2 | 없음 | allocation_outside, chain_length, directory_name_length, payload_truncated |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5816431116615680.xls` | markdown, json, errors | 5→1 | 없음 | allocation_crosslink, allocation_outside, chain_length, directory_cycle_or_crosslink, directory_outside |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-5889658057523200.xls` | json, errors | 1→2 | 있음 | allocation_outside, chain_length, payload_truncated |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6137883240824832.xls` | json, errors | 1→1 | 없음 | allocation_outside, chain_length, mini_shift, payload_truncated |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6322470200934400.xls` | json, errors | 1→2 | 있음 | allocation_outside, chain_length, payload_truncated |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6483562584932352.xls` | json, errors | 1→2 | 있음 | allocation_outside, chain_length, payload_truncated |
| `poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIHSSFFuzzer-6537773940867072.xls` | json, errors | 1→2 | 있음 | allocation_outside, chain_length, payload_truncated |
| `poi-src/test-data/spreadsheet/crash-9bf3cd4bd6f50a8a9339d363c2c7af14b536865c.xlsx` | json, errors | 1→2 | 있음 | allocation_outside, chain_length, payload_truncated |

## 메타데이터 정상 47개 상대경로

```json
[
  "hwp-public/hwp/business_card.hwp",
  "hwp-public/hwp/catalogue.hwp",
  "hwp-public/hwp/famous_restaurant_note.hwp",
  "hwp-public/hwp/hwpers-converted_output.hwp",
  "hwp-public/hwp/hwpers-minimal_base_template.hwp",
  "hwp-public/hwp/img_03_two_images_png_jpg.hwp",
  "hwp-public/hwp/nts-2008신고서작성요령_책자(1_2편).hwp",
  "hwp-public/hwp/nts-2008신고서작성요령_책자(3_4편).hwp",
  "hwp-public/hwp/nts-2009신고서작성요령_책자(1_2편).hwp",
  "hwp-public/hwp/nts-2009신고서작성요령_책자(3_4편).hwp",
  "hwp-public/hwp/real_crop_vs_original_two_objects.hwp",
  "hwp-public/hwp/table_07_image_in_merged_cell.hwp",
  "lo-src/sw/qa/core/data/ww8/pass/fdo40686-1.doc",
  "lo-src/sw/qa/extras/ww8export/data/n652364.doc",
  "lo-src/sw/qa/extras/ww8export/data/n750255.doc",
  "lo-src/sw/qa/extras/ww8export/data/n757118.doc",
  "poi-src/test-data/document/Bug48075.doc",
  "poi-src/test-data/document/Bug60942.doc",
  "poi-src/test-data/document/test-fields.doc",
  "poi-src/test-data/slideshow/43781.ppt",
  "poi-src/test-data/slideshow/45776.ppt",
  "poi-src/test-data/slideshow/54111.ppt",
  "poi-src/test-data/slideshow/WithMacros.ppt",
  "poi-src/test-data/slideshow/backgrounds.ppt",
  "poi-src/test-data/slideshow/bug60345_Jankovic_final_Retreat_2002.ppt",
  "poi-src/test-data/slideshow/bug60345_paperfigures.ppt",
  "poi-src/test-data/slideshow/numbers.ppt",
  "poi-src/test-data/slideshow/numbers2.ppt",
  "poi-src/test-data/slideshow/numbers3.ppt",
  "poi-src/test-data/slideshow/pictures.ppt",
  "poi-src/test-data/spreadsheet/1900DateWindowing.xls",
  "poi-src/test-data/spreadsheet/1904DateWindowing.xls",
  "poi-src/test-data/spreadsheet/44861.xls",
  "poi-src/test-data/spreadsheet/45290.xls",
  "poi-src/test-data/spreadsheet/45322.xls",
  "poi-src/test-data/spreadsheet/46904.xls",
  "poi-src/test-data/spreadsheet/48180.xls",
  "poi-src/test-data/spreadsheet/48325.xls",
  "poi-src/test-data/spreadsheet/49761.xls",
  "poi-src/test-data/spreadsheet/51461.xls",
  "poi-src/test-data/spreadsheet/53404.xls",
  "poi-src/test-data/spreadsheet/FormatChoiceTests.xls",
  "poi-src/test-data/spreadsheet/SimpleWithImages-mac.xls",
  "poi-src/test-data/spreadsheet/atp.xls",
  "poi-src/test-data/spreadsheet/ex47747-sharedFormula.xls",
  "poi-src/test-data/spreadsheet/moodle.iamm.fr_pluginfile.php_2971_mod_resource_content_4_evaluation_module_decouverte_qesamed.xls",
  "poi-src/test-data/spreadsheet/noHeaderFooter47244.xls"
]
```
