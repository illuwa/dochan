# DOC·XLS 암호 문서 실물 검증

2026년 10월 2일 공개 Apache POI 코퍼스를 읽기 전용으로 검증했다. 실물 파일은 저장소로 복사하지 않았다. 기대값은 POI 테스트의 단언만 참고했으며, POI 암호화 구현은 읽거나 번역하지 않았다. 복호화는 [MS-OFFCRYPTO]의 binary RC4·CryptoAPI 키 유도와 XOR method 1·2, [MS-DOC]의 FIB 및 [MS-XLS]의 레코드 암호화 경계를 바탕으로 작성했다. 원시 바이트 관찰로 XOR 파일의 레코드별 위치와 숫자 값을 확인했다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| DOC 암호화 문서, binary RC4 | `document/password_tika_binaryrc4.doc` | `poi-ooxml/src/test/java/org/apache/poi/poifs/crypt/tests/TestHxxFEncryption.java:67` | `This is an encrypted Word 2007 File.`을 복원한다. | 기대 문자열이 있고 오류는 0건이다. | 통과했다. |
| DOC 암호화 문서, RC4 CryptoAPI | `document/password_password_cryptoapi.doc` | `TestHxxFEncryption.java:69` | `This is a test`를 복원한다. | 기대 문자열이 있고 오류는 0건이다. | 통과했다. |
| XLS 암호화 문서, binary RC4 | `spreadsheet/password.xls` | `poi/src/test/java/org/apache/poi/hssf/usermodel/TestCryptoAPI.java:41` | `A ZIP bomb is a variant of mail-bombing.`이라는 기대 본문의 시작 문장이 있다. | 기대 문자열이 있고 오류는 0건이다. | 통과했다. 전체 장문 완전 일치 검사는 하지 않았다. |
| XLS 암호화 문서, RC4 CryptoAPI | `spreadsheet/35897-type4.xls` | `TestCryptoAPI.java:44`, `TestHxxFEncryption.java:73` | `hello there!`를 복원한다. | 기대 문자열이 있고 오류는 0건이다. | 통과했다. |
| XLS 암호화 문서, XOR method 1 | `spreadsheet/xor-encryption-abc.xls` | `TestCryptoAPI.java:38` 및 FILEPASS·BoundSheet8·NUMBER 원시 바이트 | 시트의 세 셀 값이 순서대로 `1`, `2`, `3`이다. | 셀 전체 목록이 정확히 일치하고 오류는 0건이다. | 통과했다. |
| XLS 기본 암호 | `spreadsheet/50833.xls`다. | `poi/src/test/java/org/apache/poi/hssf/usermodel/TestBugs.java:1701-1708`이다. | 암호 미제공 시 `test cell value`를 복원한다. | 기대 셀과 API JSON이 일치하고 잘못된 암호를 거부했다. | 통과했다. |
| DOC·XLS 잘못된 암호와 암호 미제공 | 위 공개 표본 5개 | 기존 오류 계약 및 정상 암호 대조 | 잘못된 암호와 암호 미제공 모두 본문을 내보내지 않고 암호 오류를 남긴다. | 10회 모두 빈 sections와 명확한 `ERR:` 암호 오류를 반환했다. | 10/10회 통과했다. |
| DOC 암호화 문서, XOR method 2 | 표본이 없다. | POI와 LO 공개 WordDocument 356개의 FIB를 조사했다. | XOR 문서의 스트림 복원을 실물로 검증해야 한다. | 방법 2 구현과 합성 모델 출력 테스트는 통과했지만 fObfuscated 표본은 0개다. | 실물 미검증이다. |

재현 명령은 `/usr/bin/python3 -m scripts.probe_legacy_crypto /path/to/poi-src/test-data`이다. 스크립트는 코퍼스 경로를 인자로 받으며 결과에 암호를 출력하지 않는다. 정상 암호 실물 6개 중 6개에서 선택한 기대값이 일치했다. DOC 2개와 XLS 4개는 각각 일치율 100%이다. 암호 없는 짝과 출력 전체를 비교한 것은 아니므로 결과를 전체 문서 동일성으로 확대하지 않는다.

합성 테스트는 `tests/test_legacy_crypt.py`에 있다. RC4와 CryptoAPI의 검증자, 512바이트 DOC 블록 경계, 1024바이트 XLS 블록 경계, PPT에서 재사용하는 지속 객체 키, XLS 평문 레코드·BoundSheet8 오프셋, XOR 키와 검증자, 기본 암호, 잘린 헤더를 검증한다. 최초 테스트의 모듈 부재 실패와 XOR 지원·키 검증 실패를 확인한 뒤 구현하여 통과시켰다. DOC·XLS 기존 리더 및 하드닝 테스트를 포함한 범위에서는 151개가 통과했고 기존 예상 실패 2개는 유지되었다. 기존 테스트 단언은 변경하지 않았다.

DOC 리더의 변경은 암호화 스트림 진입점, 선택한 테이블의 메모리 캐시, Data 스트림 복호화와 선택적 password 생성자에 한정했다. XLS 리더는 FILEPASS 진입점과 선택적 password 생성자만 바꿨다. 수식·차트·도형·내장 개체 해석은 변경하지 않았다. 암호 미제공 시 XLS는 빈 암호와 Excel 기본 암호를 순서대로 시도한다. 암호 미제공 시 기존 정확 문구를 유지하고, 명시 암호가 있으면 정적인 진단 전용 예외의 구체적인 이유를 전달한다. 암호는 노출하지 않는다.

XLS 칸은 세 방식과 기본 암호의 단위 테스트·실물 검증을 통과했으므로 ✅를 제안한다. DOC의 RC4 두 방식은 검증됐고 XOR method 2도 구현했으나 XOR 실물이 없어 DOC 칸은 ⬜ 유지다. 최신 전체 수치와 명세·실물 조사 근거는 [리뷰 반영 통합 표](2026-10-02-crypto-fix-real-docs.md)에 기록했다.
