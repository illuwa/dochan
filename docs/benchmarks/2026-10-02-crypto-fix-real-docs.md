# 암호화 리뷰 반영 실물 검증

2026년 10월 2일 공개 POI Office 15개와 LibreOffice DOCX 4개를 원본 위치에서 읽기 전용으로 검증했다. Office 19개 모두 선택한 본문·셀·해시 기대값과 공용 API·직접 리더 JSON 비교를 통과했다. 사용자 암호가 필요한 17개는 암호 미제공을 거부했으며, 모든 19개는 잘못된 암호를 거부했다. 이것은 선택한 기대값에 대한 일치율이며 모든 문서 요소의 완전 복원을 뜻하지 않는다. 코퍼스 원본이나 복호화한 파일은 저장소에 복사하지 않았다.

## 칸별 실물 결과

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOC 암호화 | `password_tika_binaryrc4.doc`, `password_password_cryptoapi.doc`이다. | [legacy 상세 표](2026-10-02-crypto-legacy.md)의 POI 기대 문자열이다. | RC4 두 방식의 본문과 API 출력이 일치해야 한다. | 2/2개와 음성 4/4개가 통과했다. | RC4는 통과했으나 XOR 실물이 없어 칸은 ⬜ 유지다. |
| DOC XOR | 실물이 없다. | POI 전체의 WordDocument 161개와 LibreOffice sw/qa의 195개에서 FIB offset 10의 fObfuscated를 관찰했다. | 방법 2 실물로 본문을 검증해야 한다. | 356개 중 XOR 플래그 양성은 0개다. POI 손상 CFB 2개는 별도로 검사하지 못했다. | 합성 테스트만 통과했으므로 실물 미검증이다. |
| PPT 암호화 | `Password_Protected-56-hello.ppt`, `Password_Protected-hello.ppt`, `Password_Protected-np-hello.ppt`, `cryptoapi-proc2356.ppt`, `ppt_with_png_encrypted.ppt`다. | [PPT 상세 표](2026-10-02-crypto-ppt.md)의 POI 단언과 `ppt_with_png.ppt` 평문 짝이다. | 본문·그림 해시와 PNG 이미지 모델이 복원되어야 한다. | 5/5개, 음성 10/10개, 그림 해시 7/7개와 PNG 모델 1개 1,360바이트가 일치했다. 경고는 0개다. | ✅를 제안한다. CMYK·기본 암호 조합은 합성 검증만 했다. |
| XLS 암호화 | `password.xls`, `35897-type4.xls`, `xor-encryption-abc.xls`, `50833.xls`다. | 기존 legacy 표와 `poi/src/test/java/org/apache/poi/hssf/usermodel/TestBugs.java:1701-1708`의 셀 단언이다. | 기존 세 방식과 기본 암호의 `test cell value`를 복원해야 한다. | 4/4개 및 음성 7/7개가 통과했다. `50833.xls`는 암호 생략 시 정상적으로 열렸다. | ✅를 제안한다. |
| DOCX 암호화 | POI의 `bug53475-password-is-pass.docx`, `bug53475-password-is-solrcell.docx`다. | [OOXML 상세 표](2026-10-02-crypto-ooxml.md)의 원시 XML 기대값이다. | Standard·Agile 본문과 CRC가 일치해야 한다. | 2/2개가 통과했다. | 아래 LO 4개와 합쳐 6/6개이며 ✅를 제안한다. |
| DOCX 암호화 | `Encrypted_MSO2007_abc.docx`, `Encrypted_MSO2010_abc.docx`다. | LO `sw/qa/extras/ooxmlexport/ooxmlencryption.cxx:25-38`의 첫 문단 단언이다. | 첫 문단이 소문자 `abc`여야 한다. | 두 파일의 기대 본문·CRC·API JSON이 일치했다. | 2/2개가 통과했다. |
| DOCX 암호화 | `Encrypted_MSO2013_abc.docx`, `Encrypted_LO_Standard_abc.docx`다. | 같은 LO 테스트의 46-60줄이다. | 첫 문단이 대문자 `ABC`여야 한다. | 두 파일의 기대 본문·CRC·API JSON이 일치했다. | 2/2개가 통과했다. 파일명의 소문자를 본문 기대값으로 삼지 않았다. |
| PPTX 암호화 | 유효한 실물이 없다. | POI slideshow의 PPTX 95개와 LO sd/qa/unit/data의 PPTX 429개에서 CFB 매직을 검사했다. | 암호화 OOXML PPTX 실물이 있어야 한다. | 총 524개 중 CFB 0개다. 기존 손상 퍼징 표본은 유효한 실물로 세지 않았다. | ⬜ 유지다. |
| XLSX 암호화 | `protected_passtika.xlsx`, `58616.xlsx`다. | 기존 OOXML 표의 POI 본문·ZIP SHA-256 단언이다. | 본문 또는 전체 ZIP 해시와 CRC가 일치해야 한다. | 2/2개 및 음성 3/3개가 통과했다. `58616.xlsx` 전체 읽기는 0.150296초였다. | ✅를 제안한다. |
| PDF 사용자 암호 API | 기존 [PDF 상세 표](2026-10-02-crypto-real-docs.md)의 공개 7개다. | pdf.js 매니페스트와 직접 PDFReader JSON이다. | 공용 API와 기존 리더 출력이 같아야 한다. | 7/7개가 일치하고 음성 14/14개를 거부했다. | 기존 ✅를 유지한다. |
| HWP 암호화 | 공개 헤더 5,363개 중 암호 플래그 양성 1개다. | FileHeader offset 36의 bit 1이다. | 미지원 암호화를 명확히 거부해야 한다. | 1/1개를 거부했다. | 복호화 미구현이므로 ⬜ 유지다. |

`protected_passtika.xlsb`의 실제 API 결과는 `ERR: 암호화된 문서 — XLSB 형식은 미지원입니다.`다. LO의 MSO2013 표본 암호문을 메모리에서 한 바이트 바꾼 경우에는 HMAC 무결성 실패가 명확히 반환됐다. 원본 파일은 그대로 두었다. `DOCHAN_PASSWORD`가 빈 문자열일 때 `58616.xlsx`를 CLI info로 여는 결과는 종료 코드 0이었다.

## AES 성능과 문서별 예산

동일 Python 3.9에서 결정적인 1 MiB 입력을 전후 각 1회 측정했다. PDF·HWP와 Office가 공유하는 AES 구현에 T-table과 재사용 라운드 키를 적용했다. FIPS-197 부록 C.1–C.3 및 SP 800-38A 부록 F.1–F.2의 독립 기지 답안으로 검증했다.

| 연산 | 수정 전 | 수정 후 | 개선 |
|---|---:|---:|---:|
| AES-128 ECB 복호화 | 35.483404초 | 0.555490초 | 63.9배다. |
| AES-256 CBC 복호화 | 51.302556초 | 0.794189초 | 64.6배다. |

가장 느린 CBC 관측값은 약 1.26 MiB/s다. 이를 근거로 OOXML의 암호 패키지 크기를 16 MiB로 제한하고, 문서당 후보는 최대 2개, 모든 후보의 KDF 반복 합계는 1,000,000회, AES 처리 합계는 16 MiB와 검증 정보 여유 16 KiB, 복호화 시간은 20초로 제한했다. 크기 초과는 스트림을 읽기 전에 거부한다. KDF는 1,024회마다, AES는 4 KiB마다 시각을 확인하므로 협력적 시간 제한이다. OS 정지나 I/O 대기를 중단하는 강제 워커 타임아웃을 뜻하지 않는다. ZIP 파싱 시간도 이 암호 예산에 포함하지 않는다.

암호 패키지는 memoryview로 참조하고 평문은 정확한 길이의 bytearray에 직접 쓴다. Agile 세그먼트는 하나의 출력 버퍼와 키 스케줄을 재사용한다. Standard의 패키지 슬라이스 및 결과의 padding 제거용 전체 사본을 없앴다. 반환 bytes 사본은 API 계약 때문에 남아 있다. 패키지 최대 사본 5개를 그대로 유지한다는 이전 평가는 이 구현에는 적용되지 않는다.

## 명세 확인 및 제한

DOC XOR는 [MS-DOC 2.2.6.1](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/79dea1e9-4dce-4fa0-8c6b-56ba37b68351)과 [MS-OFFCRYPTO 2.3.7.4](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-offcrypto/0752a14e-70ed-4965-b8fb-193223223445), [2.3.7.5](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-offcrypto/06494548-8c5c-4697-bce1-e2a9fe1c4de4), [2.3.7.6](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-offcrypto/5e09eb75-9135-4585-b7fb-031261c25920)에 따라 구현했다. lKey의 상위 키·하위 검증자와 ROR1 배열, Word의 첫 68바이트 예외 및 0 바이트 예외를 적용했다. Word 방법 2는 의뢰에 적힌 2.3.7.1–2.3.7.4 이후의 절차도 필요하다. 알 수 없거나 ANSI 코드페이지가 없는 LCID에는 cp1252 후보와 UTF-16 low/high 후보를 검사한다는 제한이 있으며, 모든 로캘의 실물 검증을 주장하지 않는다.

PowerPoint 기본 암호는 [MS-OFFCRYPTO v20260217 PDF](https://officeprotocoldoc.z19.web.core.windows.net/files/MS-OFFCRYPTO/%5BMS-OFFCRYPTO%5D.pdf) 66쪽 2.4.2.3의 바이트열을 확인한 뒤 추가했다. 암호 생략 시 빈 암호와 그 기본 암호만 시도하며, 명시한 오답에는 폴백하지 않는다. 문서 검색 도구로 공식 명세를 확인했으며 호스트 셸의 네트워크나 외부 구현 코드는 사용하지 않았다.

Standard 2.2, CMYK JPEG 및 PowerPoint 기본 암호는 합성 기지 사례를 통과했지만 해당 실물 조합은 확보하지 못했다. HWP 암호 복호화, DOC XOR 실물, PPTX 암호 실물, PPT EncryptedSummary 및 추가 이중 UID·메타파일 실물 검증은 남아 있다.

## 재현 명령

```bash
/usr/bin/python3 -m scripts.benchmark_aes --modes ecb128 cbc256
/usr/bin/python3 -m scripts.probe_legacy_crypto /path/to/poi-src/test-data
/usr/bin/python3 -m scripts.probe_ppt_crypto /path/to/poi-src/test-data
/usr/bin/python3 -m scripts.probe_ooxml_crypto /path/to/poi-src/test-data --lo-corpus /path/to/lo-src/sw/qa/extras/ooxmlexport/data
/usr/bin/python3 -m scripts.probe_crypto_review --poi-corpus /path/to/poi-src/test-data --lo-corpus /path/to/lo-src
/usr/bin/python3 -m scripts.probe_doc_xor_inventory /path/to/poi-src/test-data /path/to/lo-src/sw/qa
/usr/bin/python3 -m scripts.probe_crypto_api --pdf-corpus /path/to/pdfjs-src/test/pdfs --hwp-corpus /path/to/hwp-public/hwp
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```
