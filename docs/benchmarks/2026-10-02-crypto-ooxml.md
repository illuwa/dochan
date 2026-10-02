# OOXML 암호화 문서 검증 기록

2026년 10월 2일에 Apache POI 공개 코퍼스를 읽기 전용으로 검사했다. 암호화된 원본이나 복호화한 ZIP은 저장소에 복사하지 않았다. 구현은 `dochan/crypto/ooxml.py`에 두었으며, 복호화 결과를 메모리의 `BytesIO`로 기존 OOXML 리더에 전달한다. POI 구현 코드는 읽거나 번역하지 않았으며, 테스트에 적힌 공개 암호와 기대값만 검증 근거로 사용했다.

다음 표의 `crypt/tests/`는 POI의 `poi-ooxml/src/test/java/org/apache/poi/poifs/crypt/tests/`를 뜻한다. DOCX의 기대 문장은 복호화 ZIP 안의 원시 `word/document.xml`에서 관찰했다. 해당 ZIP의 모든 엔트리는 CRC 검사를 통과했다. XLSX에는 POI 테스트가 직접 단언하는 본문과 전체 복호화 바이트의 SHA-256을 사용했다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOCX | `document/bug53475-password-is-pass.docx` | `crypt/tests/TestEncryptor.java:149-150`의 공개 암호와 원시 `word/document.xml`의 `w:t`를 확인했다. | `The is a password protected document.`를 추출해야 한다. | Agile의 HMAC과 ZIP CRC가 통과했고, 23,162바이트 ZIP에서 기대 문장을 추출했다. | 통과했다. |
| DOCX | `document/bug53475-password-is-solrcell.docx` | `crypt/tests/TestEncryptor.java:245-246`의 공개 암호와 원시 `word/document.xml`의 `w:t`를 확인했다. | `This is password protected Word document.`를 추출해야 한다. | Standard의 암호 검증과 ZIP CRC가 통과했고, 24,950바이트 ZIP에서 기대 문장을 추출했다. | 통과했다. |
| XLSX | `spreadsheet/protected_passtika.xlsx` | `crypt/tests/TestSecureTempZip.java:119-140`에 암호와 본문 기대값이 있다. | `This is an Encrypted Excel spreadsheet.`를 추출해야 한다. | Standard의 암호 검증과 ZIP CRC가 통과했고, 8,230바이트 ZIP에서 기대 문장을 추출했다. | 통과했다. |
| XLSX | `spreadsheet/58616.xlsx` | `crypt/tests/TestDecryptor.java:161-169`에서 복호화 ZIP의 SHA-256을 단언한다. | SHA-256의 Base64 값이 `L1vDQq2EuMSfU/FBfVQfM2zfOY5Jx9ZyVgIQhXPPVgs=`여야 한다. | 암호를 지정하지 않았을 때 기본 암호로 연 120,332바이트 ZIP의 해시가 정확히 일치했고 CRC도 통과했다. | 통과했다. |
| PPTX | 유효한 암호화 실물 표본을 찾지 못했다. | 기존 코퍼스 1,430개 파일 조사에 더해 POI·LO PPTX 524개를 추가 조사했으며 이 중 CFB는 0개였다. | 유효한 암호화된 PPTX 실물을 기존 PPTX 출력 계약으로 검증해야 한다. | 확장자가 `.ppt`인 암호화 OOXML 퍼징 표본 여섯 개는 손상된 길이 또는 암호 메타데이터 때문에 거부되었다. 유효한 PPTX 실물로 셀을 검증하지 못했다. | 미검증이므로 ⬜를 유지해야 한다. |

DOCX 두 표본과 XLSX 두 표본의 복호화 검증은 총 네 건 모두 통과했다. 사용자 암호가 필요한 세 표본은 암호 미제공 시 모두 `ERR: 암호화된 문서` 오류를 냈다. 네 표본 모두 잘못된 암호를 거부했으며, 오류에는 입력 암호를 포함하지 않았다. 공용 API와 복호화 ZIP을 직접 읽은 기존 OOXML 리더의 최종 출력도 네 표본 모두 일치했고, 공용 API의 문서 오류 목록은 모두 비어 있었다. `scripts/probe_ooxml_crypto.py`가 이 비교를 함께 수행한다.

검증은 다음 명령으로 재현한다. 경로는 실행 환경에 맞는 POI `test-data` 디렉터리를 인자로 전달한다.

```bash
/usr/bin/python3 -m scripts.probe_ooxml_crypto /path/to/poi-src/test-data
/usr/bin/python3 -m pytest tests/test_ooxml_crypt.py -q -p no:cacheprovider --basetemp=.codex-work/pytest-ooxml
```

단위 테스트 20개는 합성 바이트만 사용한다. Standard AES-128·192·256, Agile SHA-1·256·512와 AES-128·192·256, 4,096바이트 경계를 넘는 세그먼트, 빈 암호 및 Office 기본 암호, 잘못된 암호, HMAC 변조, 반복 횟수와 스트림 크기 제한, UTF-8 및 UTF-16·32 XML의 엔터티 선언을 검증했다. UTF-16의 DTD 우회는 실패 테스트에서 재현한 뒤 UTF-8 전용 디코딩과 선언 거부로 수정했다.

Standard는 명세상 HMAC을 갖지 않으므로 암호 검증자와 기존 ZIP 파서의 CRC 검사를 사용한다. Agile은 암호 검증자에 더해 길이 접두부를 포함한 `EncryptedPackage` 전체의 HMAC을 확인한 뒤 본문을 복호화한다. SHA-384도 코드에서 지원하지만 이번 실물과 단위 테스트의 해시 조합에는 포함하지 않았으므로 별도로 검증했다고 주장하지 않는다.

안전 상한은 암호 메타데이터 64 KiB, 복호화 ZIP 16 MiB, 문서당 암호 후보 2개·해시 반복 합계 1,000,000회·복호화 시간 20초로 정했다. 이는 자원 소비를 제한하기 위한 구현 정책이며 Microsoft 형식의 최대치를 실측했다고 주장하는 수치가 아니다. 지원 범위는 Standard AES와 Agile AES-CBC 및 암호 기반 키이며, 인증서 기반 키와 Agile의 다른 블록 암호·체이닝 모드는 명확한 오류로 거부한다. 새 런타임 의존성이나 외부 변환 엔진은 추가하지 않았다.

## 리뷰 반영 후 추가 실물

2026년 10월 2일 LO `Encrypted_MSO2007_abc.docx`, `Encrypted_MSO2010_abc.docx`, `Encrypted_MSO2013_abc.docx`, `Encrypted_LO_Standard_abc.docx`를 추가 검증했다. LO 테스트의 기대값은 앞의 두 개가 `abc`, 뒤의 두 개가 `ABC`다. 모두 본문·CRC·전체 API JSON 일치를 확인해 DOCX는 총 6/6개, XLSX는 2/2개다. 모든 8개가 오답을 거부하고 사용자 암호 필수 7개가 암호 미제공을 거부했다. 프로브에 `--lo-corpus /path/to/lo-src/sw/qa/extras/ooxmlexport/data`를 추가하면 함께 재현된다.

Standard 2.2를 추가했으며 3.2·4.2와 함께 처리한다. AES 가속 및 memoryview·단일 출력 버퍼 적용 후의 예산, 성능, 구체적인 오류 결과와 행별 정답 근거는 [crypto-fix 통합 검증](2026-10-02-crypto-fix-real-docs.md)에 있다. 기존 20개 테스트 외에 `tests/test_crypto_review.py`에서 버전·진단·작업량·시간 제한·사본 감소를 검증한다.
