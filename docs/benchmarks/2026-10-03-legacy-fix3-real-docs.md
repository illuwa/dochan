# 내장 개체·XLS·암호화 최종 감수 수정 검증

2026년 10월 3일에 기준 HEAD `2668119d7448ece1091311bf990b0c89018d1540`과 작업 결과를 비교했다. 공개 POI·LibreOffice·Tika 표본은 원래 코퍼스에서 읽었으며 복사하지 않았다. 구현은 기존 자체 파서와 공개 형식의 레코드·원시 바이트 관찰에 근거한다. 다른 프로젝트의 구현 코드는 사용하지 않았다. README와 CHANGELOG는 수정하지 않았다.

## 칸별 실물 검증

| 칸 또는 감수 항목 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| XLS·내장 워크북 오류 상한 | 합성 RK 10,000·20,000·40,000개이다. 실물 성능 표본으로 세지 않는다. | 각 RK의 행은 다르고 열 300은 BIFF8 범위를 벗어난다. | 입력 증가에 따라 오류 수·중복 집합이 무제한 증가하지 않아야 한다. | XLS 상세 100줄과 생략 요약 1줄, 내장 개체 상세 16줄과 생략 요약 1줄로 제한된다. 중복 검사는 보존된 메시지의 set을 쓴다. | 합성 공격 재현을 통과했다. 새 기능 ✅의 근거로 쓰지 않는다. |
| 내장 개체 실패의 비치명 처리 | `SimpleWithColours.xls`를 메모리에서 Excel.Chart.8로 감싼다. | 원시 DIMENSION의 범위 오류와 기존 미리보기 계약이다. | 개체 결과는 비어 있고, 호스트에는 WARN만 남아야 한다. | 결과 0개, WARN 2개, ERR 0개이다. | 1/1개 통과했다. 원본 실물에 메모리 어댑터를 적용한 검사이며 실제 PPT에 새로 삽입한 실물은 아니다. |
| OOXML 암호화 | POI `bug53475-password-is-pass.docx`, `bug53475-password-is-solrcell.docx`, `protected_passtika.xlsx`, `58616.xlsx`와 LO `Encrypted_MSO2007_abc.docx`, `Encrypted_MSO2010_abc.docx`, `Encrypted_MSO2013_abc.docx`, `Encrypted_LO_Standard_abc.docx`이다. | 기존 암호 실물 프로브의 공개 기대 문자열·SHA-256, ZIP CRC 및 평문 OOXML 리더 출력이다. | 시간 부하와 무관하게 올바른 암호로 같은 평문을 얻어야 한다. | 8/8개가 본문 또는 해시, CRC, API/평문 리더 대조를 통과했다. | 검증한 Standard/Agile 범위의 기존 지원 판정을 유지한다. |
| OOXML 16 MiB 경계 | 합성 Agile 암호 패키지 1개를 2회 복호화했다. | 생성 전 평문 16,777,216바이트와 SHA-256이다. | 20초 시간 조건 없이 결정적 예산 안에서 동일해야 한다. | 2/2회 정확 일치했다. SHA-256은 `156538b85d03f10777ec99d538420128d3421dc674716fb49442b6b9c2c1a2b0`이다. | 암호 계층 경계 검증이다. 16 MiB Office 실물 검증으로 세지 않는다. |
| XLS 수식·캐시 값 | `testEXCEL_5.xls`, `testEXCEL_95.xls`의 E19이다. | FORMULA 캐시 double 1960.0 및 rgce `44 12 00 02 1e 0a 00 05`이다. | 일부 토큰만 읽은 `=$C$19`를 출력하지 않아야 한다. | 두 문서 모두 `$1,960.00`만 보존하고 E19를 명시한 WARN을 남긴다. | 2/2개 통과했다. BIFF5 RPN 완전 지원은 미검증이며 XLS 수식 칸을 이 근거만으로 ✅로 올리지 않는다. |
| XLS 외부 책 수식 | 여러 `\x03` 디렉터리 구분자·ctab 조합을 가진 합성 SupBook이다. | VirtualPath의 경로 구분자와 DDE 서비스/토픽 구분, ctab를 구별한다. | 외부 통합문서를 DDE로 오판하지 않아야 한다. | 외부 참조 `[1]Remote!$A$1`를 보존하며 실제 DDE는 기존대로 생략한다. | 회귀 단위 테스트를 통과했다. 해당 다중 구분자 실물은 미검증이다. |
| DOC 이미지 참조·빈 FBSE | LO `n757118.doc`와 POI `Bug47958.doc`, `Bug50936_1.doc`, `Bug50936_2.doc`, `Bug50936_3.doc`이다. | FBSE의 bt·cRef 값과 기준 HEAD의 본문·이미지 바이트 해시이다. | 빈 항목이나 참조 없는 항목을 지연 BLIP로 읽지 않아야 한다. | 5개 문서에서 가짜 경고만 사라졌고 Markdown·JSON 본문·이미지 바이트는 동일했다. | 해당 회귀 5/5개 통과했다. |
| PPT 차트 제목/데이터 | `37625.ppt`, `42520.ppt`, `bug61881.ppt`, `53446.ppt`의 저장된 Graph 34개이다. | 변환기의 정규화 캐시를 쓰지 않고 원시 Number/Label, 0x1053/0x1054 포함 범위, 0x1055 방향에서 표를 독립 구성했다. | 선택된 계열만 출력하고 표의 폭·본문·비어 있지 않은 계열 이름이 일치해야 한다. | 연속 선택 31/31개에서 본문 616/616칸과 표 폭·비어 있지 않은 계열 이름이 일치했다. 비연속 선택 3개는 미리보기를 유지했다. | 연속 선택 범위에 ✅를 제안한다. 전체 커버리지는 31/34개이며 34/34개 지원으로 보고하지 않는다. |
| DOC/PPT 수식·MTEF 인접 위첨자 | 합성 MTEF SCRIPT 레코드이다. | 같은 LINE의 형제 SCRIPT 슬롯은 같은 기준선에 있고 중첩 LINE은 다른 수준을 갖는다. | 형제 `x^{2}^{3}`는 `x^{23}`, 중첩은 `x^{2^{3}}`이어야 한다. | 두 구조의 기대식이 각각 일치했다. | 해당 구조의 실물은 미검증이다. 이 수정만으로 DOC/PPT 수식의 ⬜를 변경하지 않는다. |
| Excel.Sheet.12 미리보기 | `testPPT_oleWorkbook.ppt`의 ole2이다. | ExOleObjStg의 선언 길이와 복원 길이는 모두 17,920바이트이고 CFB는 열리지만 zlib eof가 거짓이다. CFB에는 Package가 있고 native Workbook/Book/Equation Native는 없다. | 비대상 OOXML 개체의 기존 미리보기를 보존해야 한다. | Markdown·JSON·이미지는 동일하고 사용하지 않는 스트림의 압축 프레임 경고만 제거했다. | 1/1개 통과했다. OOXML 내장 통합문서 신규 지원을 주장하지 않는다. |
| 암호 미제공 진단·타입 | spinCount 1,000,000 합성 Agile과 형식 8개 × 비문자열 타입 3개이다. | 후보 전체의 KDF 총예산과 API 옵션 검증 계약이다. | 기본 후보 예산 소진은 암호 필요로, bytes 등은 명시 TypeError로 알려야 한다. | 암호 필요 진단과 24개 타입 검사가 통과했다. | 합성 검증이다. 해당 spinCount의 실물은 미검증이다. |
| DOC DRM/IRM 진단 | Tika `testWORD_protected_drm.doc`이다. | `\tDRMContent`와 `\x06DataSpaces/TransformInfo/\tDRMTransform/\x06Primary` 스트림이다. | 안내문만 추출했음을 경고해야 한다. | Dochan/CLI에서 기존 안내문 260자를 유지하고 DRM/IRM WARN 1개를 추가했다. | 1/1개 통과했다. 보호된 본문 복호화는 지원하지 않는다. |

## 자원 제한과 진단

OOXML 암호 패키지 평문 상한은 **16 MiB**이다. EncryptionInfo 64 KiB, 자동 암호 후보 최대 2개, 문서 전체 KDF 반복 총 1,000,000회, AES 작업량 16 MiB + 16 KiB 제한도 유지한다. 제거한 것은 20초 wall-clock 조건뿐이다. 릴리스 담당자는 CHANGELOG에 16 MiB 제한과 시간 조건 제거를 함께 명시해야 한다.

XLS는 워크북과 시트마다 상세 100개와 생략 발생 횟수 요약을 보존한다. 최초 치명 ERR는 앞선 WARN이 상한을 채워도 상세 슬롯 하나를 대체해 보존하므로 단독 XLS의 실패가 가려지지 않는다. 생략 수는 고유 오류 개수가 아니라 보존되지 않은 발생 횟수이다. 내장 개체는 상세 16개와 생략 요약만 호스트로 전달하며 원래 XLS에서 생략한 횟수도 합산한다. 내장 ERR는 WARN으로 내리지만 이미 존재하는 호스트 ERR는 보존한다. 수집기는 내부에만 두고 공개 `Document.errors`는 일반 list로 반환해 `clear()`와 중복 추가 등 기존 가변 리스트 계약을 유지한다.

같은 합성 40,000 RK 입력을 기준 HEAD에서 처리했을 때 단독 XLS는 5.461초·40,002줄, 내장 경로는 10.966초·40,002줄이었다. 최초 수정 후 측정은 각각 0.116초·101줄, 0.103초·17줄이었다. 10,000/20,000/40,000개 단독 XLS는 0.030/0.058/0.116초였으며 제곱 증가가 사라졌음을 확인했다. 시간은 이 호스트의 관찰값이며 성능 보장 수치가 아니다. 최종 재실행의 원시 시간은 `.codex-work/diagnostics-final.json`에 남긴다.

## HEAD 전체 비교

`scripts/probe_legacy_fix3_corpus.py`는 추출한 HEAD 패키지와 작업 패키지를 각각 별도 프로세스에서 로드한다. 전체 Markdown의 SHA-256, 오류만 제외한 전체 JSON의 SHA-256, 문서 순서대로 이미지 바이트의 SHA-256, 오류 목록을 비교한다. 큰 본문은 표시용 발췌 저장만 생략하며 해시는 전체를 계산한다. 표본별 예외·시간 초과는 두 실행 모두 0개였다.

| 코퍼스 | DOC | PPT | XLS | 합계 |
|---|---:|---:|---:|---:|
| POI | 160 | 145 | 417 | 722 |
| LibreOffice | 193 | 72 | 0 | 265 |
| 합계 | 353 | 217 | 417 | 987 |

제공된 LO 코퍼스에는 XLS가 없었으므로 LO XLS를 검증했다고 주장하지 않는다. 손상·암호 미제공 문서의 기존 오류도 비교에 포함했다. 이 987개는 모두 성공적으로 변환됐다는 의미가 아니다. 기준에는 진단이 있는 문서 171개, ERR가 있는 문서 59개가 있었다.

987개 중 966개는 모든 비교값이 동일하다. 본문이 바뀐 문서는 Graph의 빈 열을 제거한 PPT 2개와 잘못된 E19 부분 수식을 제거한 BIFF5 XLS 2개뿐이다. 나머지 17개는 진단만 바뀌었다. 모든 문서의 이미지 바이트는 동일하며 의도하지 않은 변화는 0개이다.

진단만 바뀐 DOC 5개는 위 FBSE 표본이며 PPT 1개는 `testPPT_oleWorkbook.ppt`이다. XLS 11개는 `27349-vlookupAcrossSheets.xls`, `44958.xls`, `44958_1.xls`, `49219.xls`, `60405.xls`, `FormulaEvalTestData.xls`, `Intersection-52111.xls`, `IntersectionPtg.xls`, `RangePtg.xls`, `maxindextest.xls`, `testArraysAndTables.xls`이다. 이들의 수식 진단에 셀 좌표가 추가돼 서로 다른 셀의 오류를 구분한다. `49219.xls`는 NameX 선두 수식 1,399개와 ExternName 경고 1개에서 상세 100개와 생략 1,300건 요약을 낸다. 내용은 변하지 않았다.

Graph 3개 미지원 표본은 `37625.ppt`의 저장소 오프셋 116371·428118과 `53446.ppt`의 454115이다. 모두 비연속 데이터시트 선택이며 이전처럼 미리보기를 유지한다. 34개에는 PPT의 과거 저장소 레코드도 포함되므로 현재 화면에 나타나는 활성 차트 개수와 동일시하지 않는다.

## TDD와 기존 단언 교정

수정 전 전체 실행은 새 회귀 34개 실패, 기존 3,099개 통과, 24개 skip, 14개 xfail을 기록했다. 내장 개체, 최초 ERR 보존, IRM 파일 크기 상한 등 추가 회귀도 각각 실패 확인 뒤 구현했다.

기존 단언 중 다음 7개는 이번 지적의 버그를 고정하고 있어 수정했다. 이외의 기존 단언은 유지했다.

- `test_ooxml_deadline_interrupts_kdf`와 `test_ooxml_deadline_interrupts_aes`는 시간에 따른 실패를 기대했다. 시간 호출 없이 정상 복호화하는 기대값으로 바꿨다.
- `test_ooxml_hash_budget_covers_both_candidates`는 암호 미제공을 반복 작업량 초과로 기대했다. 암호 필요로 바꾸고 총예산 자체의 검사는 유지했다.
- `test_parse_biff_workbook_recovers_partial_formula_tokens`와 `test_parse_biff_workbook_recovers_partial_formula_without_disrupting_following_cells`는 피연산자가 하나뿐인 이항 RPN에서 `30 (=A2)`·`12 (=A2)`를 기대했다. 캐시 값과 위치 WARN으로 교정했으며 후속 셀 18의 단언은 유지했다.
- `test_formula_damaged_operator_warns`는 불완전한 `1 +` 토큰열을 `1`로 출력하도록 기대했다. 빈 수식으로 바꿨다.
- `test_xls_formula_truncated_attr_stops_safely`의 `1e0100191000`은 Attr의 필수 payload 3바이트 중 2바이트만 있다. 부분 수식 `1` 대신 빈 수식과 경고로 교정했다.

기존 실물 프로브 `scripts/probe_legacy_objects.py`의 `bug61881.ppt` 기대값에 있던 선택 밖 North 빈 열도 제거했다. 독립 데이터시트 대조를 근거로 한 정정이며 수정한 프로브의 64/64개 검사가 통과했다.

최종 전체 테스트는 **3,156 passed, 24 skipped, 14 xfailed**이며 33.53초가 걸렸다. `ruff check dochan scripts tests`와 `git diff --check`가 모두 통과했다. 최종 코드로 코퍼스 987개도 다시 비교해 같은 21개의 의도된 변화와 의도하지 않은 변화 0개를 확인했다. 최종 40,000 RK 재측정은 단독 0.135초, 내장 0.121초이며 진단은 각각 101줄·17줄이다. 로그와 원시 비교 결과는 `.codex-work/full-tests.log`, `corpus-head.json`, `corpus-final.json`, `corpus-changes.json`, `diagnostics-final.json`, `graph34.json`, `crypto-real.json`, `crypto-boundary.json`에 보관했다.

## 재현 명령

```bash
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
/usr/bin/python3 -m scripts.probe_legacy_fix3_corpus <corpus> --source <HEAD-추출-디렉터리> --output <기준.json>
/usr/bin/python3 -m scripts.probe_legacy_fix3_corpus <corpus> --source <워크트리> --output <수정.json>
/usr/bin/python3 -m scripts.probe_legacy_fix3_diagnostics <corpus> --source <워크트리> --output <진단.json>
/usr/bin/python3 -m scripts.probe_legacy_fix3_graph <corpus> --output <Graph.json>
/usr/bin/python3 -m scripts.probe_legacy_fix3_xls <POI-test-data/spreadsheet>
/usr/bin/python3 -m scripts.probe_ooxml_crypto <POI-test-data> --lo-corpus <LO-ooxmlexport-data>
```

## 공유 변경과 남은 범위

공유 파일은 `dochan/reader.py` 하나다. password가 str/None인지 파싱 전에 검증하고 DOC 읽기 직후 IRM 식별 helper를 호출하는 작은 추가만 했다. 모델·출력·DOC/PPT 파서 소유 파일과 PDF/HWP 계열은 변경하지 않았다. 새 런타임 의존성도 없다.

IRM 경고는 Dochan/CLI에 적용된다. 직접 `DOCReader`를 호출하는 내부 API까지 확장하려면 DOC 담당자가 helper 호출 위치를 통합해야 한다. BIFF5 RPN 전체 복원, Graph 비연속 선택, 내장 Excel.Sheet.12의 데이터 추출, 이번 MTEF 인접 위첨자 구조의 실물 검증은 남아 있다. 보호된 IRM 본문을 복호화했다고 주장하지 않는다.
