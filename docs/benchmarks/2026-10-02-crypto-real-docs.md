# 암호화 문서 통합 검증

2026년 10월 2일에 공개 Apache POI Office 표본 15개와 LibreOffice DOCX 4개와 pdf.js PDF 표본 7개를 읽기 전용으로 검증했다. HWP 공개 코퍼스에서는 5,363개 파일의 FileHeader를 조사하고 암호 플래그가 있는 1개를 명시적으로 거부하는지 확인했다. 원본과 복호화한 파일을 저장소에 복사하지 않았으며, README는 수정하지 않았다.

공용 API는 `Dochan(path, password=...)`이며 `password`는 키워드 전용이다. 기본 `None`은 빈 암호 또는 형식의 기본 암호만 시도한다. `convert`와 `info`는 `--password-stdin`의 첫 줄을 읽으며, 이 옵션이 없으면 `DOCHAN_PASSWORD`를 사용한다. 줄 끝의 개행만 제거하고 암호 앞뒤 공백은 보존한다. `batch`는 암호 입력을 지원하지 않는다. OOXML ZIP은 메모리에서만 기존 리더로 전달한다.

## 칸별 판정

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOC | `password_tika_binaryrc4.doc`, `password_password_cryptoapi.doc`이다. | [DOC·XLS 상세 표](2026-10-02-crypto-legacy.md)의 POI 테스트 문자열이다. | RC4와 CryptoAPI 본문을 복원하고 암호 오류를 거부한다. | 선택한 본문 기대값 2/2개와 공용 API·직접 리더 출력 2/2개가 일치했다. 음성 4/4개를 거부했다. | RC4 구현은 통과했으나 XOR method 2 실물이 없으므로 ⬜를 유지한다. |
| PPT | `Password_Protected-56-hello.ppt`, `Password_Protected-hello.ppt`, `Password_Protected-np-hello.ppt`, `cryptoapi-proc2356.ppt`, `ppt_with_png_encrypted.ppt`이다. | [PPT 상세 표](2026-10-02-crypto-ppt.md)의 POI 슬라이드·문자열·그림 해시 및 암호 없는 짝이다. | 지속 객체와 Pictures 스트림을 복호화한다. | 본문 5/5개, 그림 해시 7/7개와 PNG 본문 바이트가 일치했다. API 비교 5/5개와 음성 10/10개가 통과했다. | 복호화 범위에 ✅를 제안한다. 크기 0 FBSE도 복원해 PNG 모델 1개 1,360바이트가 평문 짝과 일치하고 경고는 0개다. |
| XLS | `password.xls`, `35897-type4.xls`, `xor-encryption-abc.xls`, `50833.xls`이다. | [DOC·XLS 상세 표](2026-10-02-crypto-legacy.md)의 POI 본문·원시 BIFF 셀 값이다. | RC4·CryptoAPI·XOR method 1의 셀을 복원한다. | 기대값 4/4개와 API 비교 4/4개가 일치하고 음성 7/7개를 거부했다. | ✅를 제안한다. |
| DOCX | POI 두 DOCX와 [리뷰 표](2026-10-02-crypto-fix-real-docs.md)의 LO 네 DOCX다. | [OOXML 상세 표](2026-10-02-crypto-ooxml.md)의 원시 XML 본문과 ZIP CRC이다. | Agile 및 Standard ZIP과 본문을 복원한다. | 본문·CRC·API JSON 비교 6/6개가 일치하고 음성 12/12개를 거부했다. Agile HMAC도 통과했다. | ✅를 제안한다. |
| PPTX | 유효한 암호화 실물 표본을 찾지 못했다. | OOXML 공통 엔진과 기존 PPTX 출력 계약의 합성 테스트만 있다. | 실제 암호화 PPTX를 복원해야 한다. | Standard·Agile의 메모리 전달 합성 테스트는 통과했으나 실물 0개이다. | 미검증이므로 ⬜를 유지한다. |
| XLSX | `protected_passtika.xlsx`, `58616.xlsx`이다. | [OOXML 상세 표](2026-10-02-crypto-ooxml.md)의 POI 본문·복호화 ZIP SHA-256이다. | 암호 본문과 기본 암호 문서를 복원한다. | 기대값·CRC·API 비교 2/2개가 일치하고 잘못된 암호 2/2개를 거부했다. 사용자 암호 필수 표본의 미제공도 거부했다. | ✅를 제안한다. |
| HWP | 공개 실물 5,363개 중 암호 플래그 양성 1개이다. | FileHeader의 offset 36, bit 1을 직접 관찰했다. | 암호화 본문을 평문으로 파싱하지 않고 명확히 거부한다. | 1/1개가 빈 sections와 기존 `ERR: 암호화/DRM 문서는 직접 파싱할 수 없음`을 반환했다. | 명확한 처리만 검증했으며 복호화 미지원이므로 ⬜를 유지한다. |
| PDF 사용자 암호 API | 아래 PDF 상세 표의 공개 7개이다. | 기존 PDF 작업의 테스트·실물 보고서와 직접 `PDFReader`의 전체 JSON 출력이다. | 공용 API가 같은 문서를 복원하고 실패를 오류로 처리한다. | JSON 7/7개가 완전히 일치하고 잘못된 암호·미제공 14/14개를 거부했다. | 기존 ✅를 유지하며 사용자 암호 연결이 검증되었다. |

Office의 기대 본문 비교는 선택된 문자열·셀·해시에 대한 검증이다. 전체 문서의 모든 모델 요소가 원본과 같다는 뜻으로 확대하지 않는다. 공용 API와 직접 리더의 JSON 일치는 연결 경로의 보존을 별도로 검증한 수치이다.

## PDF 연결 근거

PDF 작업 보고서와 `3811f594ef9e5e44f226cd0069547b3605df92ac` 커밋을 확인했다. 이미 구현된 `PDFReader(text_tables=False, password="").read(path)`를 재사용했으며 PDF 복호화 코드는 변경하지 않았다. 이전 실물 근거는 `docs/benchmarks/2026-10-02-pdf-real-docs.md`의 사용자 암호 절이다. 아래 줄 번호는 공개 pdf.js의 `test/test_manifest.json`을 가리킨다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| PDF R3 | `issue15893_reduced.pdf`이다. | 매니페스트 719–724줄과 기존 실물 본문이다. | `Issue 15893 - password`를 복원하며 직접 리더와 일치한다. | 직접 리더와 전체 JSON이 일치하고 암호 오답·미제공을 거부했다. | 통과했다. |
| PDF R4 | `issue3371.pdf`이다. | 매니페스트 1281–1283줄 및 이미지 페이지의 복호화 콘텐츠이다. | 이미지 페이지를 열고 직접 리더와 일치한다. | 전체 JSON이 일치하고 암호 오답·미제공을 거부했다. | 통과했다. |
| PDF R6 | `issue6010_1.pdf`이다. | 매니페스트 6898–6904줄과 기존 `Issue 6010` 본문이다. | 사용자 암호를 그대로 전달한다. | 전체 JSON이 일치하고 암호 오답·미제공을 거부했다. | 통과했다. |
| PDF R6 UTF-8 | `issue6010_2.pdf`이다. | 매니페스트 6907–6914줄이다. | Unicode 암호를 그대로 전달한다. | 전체 JSON이 일치하고 암호 오답·미제공을 거부했다. | 통과했다. |
| PDF R4 Identity | `bug1782186.pdf`이다. | 매니페스트 9695–9697줄과 원시 `StrF /Identity`이다. | 문자열 Identity 필터와 스트림 복호화를 보존한다. | 전체 JSON이 일치하고 암호 오답·미제공을 거부했다. | 통과했다. |
| PDF R5 UTF-8 | `issue21579.pdf`이다. | 매니페스트 14483–14488줄과 기존 성공 확인 본문이다. | 사용자 암호로 본문을 복원한다. | 전체 JSON이 일치하고 암호 오답·미제공을 거부했다. | 통과했다. |
| PDF R6 SASLprep | `saslprep-r6.pdf`이다. | 매니페스트 14491–14496줄과 기존 `Hello pdf.js world` 본문이다. | 기존 PDFReader의 정규화 동작을 보존한다. | 전체 JSON이 일치하고 암호 오답·미제공을 거부했다. | 통과했다. |

PDF 파싱 실패의 기존 경고를 보존하되 공용 API에는 `ERR: 암호화된 문서`를 추가했다. 이 오류를 CLI의 기존 치명적 오류 판정이 인식하므로 암호 실패 시 빈 Markdown 파일을 성공 결과로 게시하지 않는다. DOC·XLS·HWP의 기존 오류 문구는 회귀 계약에 맞춰 유지했다.

## 재현과 제한

다음 프로브는 코퍼스 경로를 인자로 받고 읽기 전용으로 동작한다. 출력에는 입력 암호를 기록하지 않는다.

```bash
/usr/bin/python3 -m scripts.probe_legacy_crypto /path/to/poi-src/test-data
/usr/bin/python3 -m scripts.probe_ppt_crypto /path/to/poi-src/test-data
/usr/bin/python3 -m scripts.probe_ooxml_crypto /path/to/poi-src/test-data
/usr/bin/python3 -m scripts.probe_crypto_api --pdf-corpus /path/to/pdfjs-src/test/pdfs --hwp-corpus /path/to/hwp-public/hwp
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

HWP 암호 방식은 구현하지 않았으며 기존 거부 정책을 확인했다. DOC XOR method 2는 합성 테스트까지 통과했고 실물은 미검증이다. PPTX는 실물 표본이 필요하다. PPT의 EncryptedSummary 속성, 이중 UID·메타파일의 추가 실물 검증, PDF의 비빈 R2·확장 PDFDocEncoding 암호 실물 검증도 남아 있다. 새 런타임 의존성·외부 변환 엔진은 추가하지 않았고, 공유 모델과 출력 형식은 변경하지 않았다.

리뷰 반영 후 최종 전체 테스트는 위 지정 명령으로 2,666개 통과, 24개 건너뜀, 기존 예상 실패 14개를 확인했다. 암호 관련 합성 테스트는 125개이며 기존 테스트 단언은 변경하지 않았다. `git diff --check`도 통과했다.

최신 리뷰별 재현·실물 조사와 AES 성능은 [crypto-fix 검증 기록](2026-10-02-crypto-fix-real-docs.md)을 따른다. CLI의 빈 환경 변수는 미제공으로 처리하며, TTY의 `--password-stdin`은 getpass를 사용한다.

## 추가 실물 검증 — Apache Tika 테스트 문서 (오케스트레이터, 2026-10-02)

Apache Tika 의 microsoft 모듈 테스트 문서(Office 로 만든 공개 표본)를 `corpus/tika-test-docs/` 에 받아 `password='tika'` 로 읽었다.
`testPPT_protected_passtika.pptx` 는 "This is an encrypted PowerPoint 2007 slide." 를, `testWORD_protected_passtika.docx` 는
"This is an encrypted Word 2007 File." 을, `testEXCEL_protected_passtika.xlsx`·`.xls` 는 "This is an Encrypted Excel spreadsheet." 를,
`testPPT_protected_passtika.ppt` 는 같은 슬라이드 문장을, `testWORD_protected_passtika.doc`(FIB fEncrypted, XOR 아님) 은
"This is an encrypted Word 2007 File." 을 냈다. 이로써 PPTX 암호화 문서의 실물 근거가 생겼다. DOC 의 XOR 난독화는 여전히 실물 표본이 없어
합성 테스트로만 검증했다.
