# PPT 암호 문서 실물 검증

2026년 10월 2일에 Apache POI 공개 `test-data/slideshow`의 암호화 PPT 5개를 읽기 전용으로 검증했다. `PPTReader(password=...)`에서 Current User 스트림의 암호화 토큰을 확인하고, UserEditAtom과 PersistDirectoryAtom으로 CryptSession10Container를 찾는다. RC4 CryptoAPI의 지속 객체별 키로 본문을 복호화한 뒤 기존 PPT 구조·텍스트·그림 출력 경로를 재사용한다. 암호 값은 오류에 넣지 않는다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| PPT 암호화 문서 | `Password_Protected-56-hello.ppt` | POI `hslf/record/TestDocumentEncryption.java:54-64`의 암호와 비어 있지 않은 슬라이드 단언이다. | 슬라이드가 1개 이상이어야 한다. | 슬라이드 1개와 본문을 읽었으며 오류가 없다. | 통과했다. |
| PPT 암호화 문서 | `Password_Protected-hello.ppt` | 같은 테스트의 기대값이다. | 슬라이드가 1개 이상이어야 한다. | 슬라이드 1개와 본문을 읽었으며 오류가 없다. | 통과했다. |
| PPT 암호화 문서 | `Password_Protected-np-hello.ppt` | 같은 테스트의 기대값이다. | 슬라이드가 1개 이상이어야 한다. | 슬라이드 1개와 본문을 읽었으며 오류가 없다. | 통과했다. |
| PPT 암호화 문서 | `cryptoapi-proc2356.ppt` | POI `hslf/record/TestDocumentEncryption.java:152-175`의 문자열·그림 해시 단언이다. | `Dominic Salemno`가 있고 그림 7개가 지정 SHA-1과 일치해야 한다. | 문자열을 찾았고 그림 7개 모두 지정 해시와 일치했다. | 통과했다. |
| PPT 암호화 문서 | `ppt_with_png_encrypted.ppt` | POI `hslf/usermodel/TestPictures.java:398-406`의 암호와 암호 없는 `ppt_with_png.ppt`의 본문·PNG 픽셀 바이트이다. | 같은 본문과 PNG 픽셀 바이트가 나와야 한다. | 본문과 PNG 이미지 모델 1개를 읽었다. PNG 데이터 1,360바이트와 형식이 암호 없는 짝과 일치했고 오류·경고는 0개다. | 통과했다. |
| PPT 암호화 문서 | 위 5개 표본 모두이다. | POI `hslf/TestEncryptedFile.java:52-70`의 암호 미제공 거부와 음성 검증이다. | 잘못된 암호와 암호 미제공을 모두 명확한 오류로 처리해야 한다. | 10개 경우 모두 섹션 없이 `ERR: 암호화된 문서 PPT` 오류를 반환했다. | 10/10개가 통과했다. |

공개 POI 테스트에서 암호·문자열·해시 기대값만 읽었으며 POI 구현 코드를 옮기거나 번역하지 않았다. 구현은 [MS-PPT]의 CurrentUserAtom·UserEditAtom·PersistDirectoryAtom·CryptSession10Container 구조, [MS-OFFCRYPTO] RC4 CryptoAPI 규칙과 공개 표본의 바이트 관찰에 근거한다. 네트워크를 사용하지 않았다.

## 단위 검증과 재현

`tests/test_ppt_crypt.py`의 합성 바이트 테스트 18개가 통과했다. 40·56·128비트 키, 지속 객체마다 달라지는 블록 번호, 그림 필드마다 RC4 재시작, 틀린 암호와 미제공, 순환 편집 체인, 과대 객체 길이, 평문 유지 및 리더 연결을 검증한다. 기존 PPT 테스트와 OfficeArt 테스트, 크기 0인 지연 BLIP 회귀 테스트를 함께 실행한 결과는 167개 통과이다. 테스트 픽스처에 실물 파일을 넣지 않았다.

```bash
/usr/bin/python3 -m pytest tests/test_ppt_crypt.py tests/test_ppt_reader.py tests/test_ppt_structure.py tests/test_ppt_shapes.py tests/test_ppt_text.py tests/test_ppt_review.py tests/test_officeart.py tests/test_officeart_delayed_crypto.py -q -p no:cacheprovider --basetemp=.codex-work/pytest-ppt
/usr/bin/python3 -m scripts.probe_ppt_crypto /path/to/poi/test-data
```

실물 프로브는 코퍼스 경로를 인자로 받고 원본을 변경하지 않는다. 결과에는 암호 값을 출력하지 않는다. 전체 형식 회귀 테스트 결과와 공용 API 검증은 통합 보고서에 기록한다.

## 판정과 남은 제한

PPT 암호화 문서는 실물 5/5개에서 본문 복호화와 기대 출력 검증을 통과했고 음성 사례는 10/10개가 통과했다. 따라서 이 칸에 ✅를 제안하며 README는 수정하지 않았다.

`ppt_with_png_encrypted.ppt`에서 FBSE의 `size`가 0인 지연 그림을 건너뛰던 결함을 리뷰 후 수정했다. `foDelay`가 가리키는 BLIP 헤더의 길이를 기존 스트림·레코드·이미지 크기 상한으로 검증한다. 두 번째 FBSE의 `foDelay`는 15203이며 그 위치에 정상 PNG BLIP가 있다. 수정 뒤 문서 이미지 모델 1개가 암호 없는 짝과 일치하며 그림 연결 경고가 사라졌다. 크기 0인 정상 BLIP와 손상·과대 입력의 회귀 테스트를 추가했다.

EncryptedSummary의 속성 정보는 이번 PPT 본문 복호화 범위에서 사용하지 않는다. 이 경로와 그림의 이중 UID·메타파일 분기에는 실물 검증 표본이 없으므로 검증 완료를 주장하지 않는다. 지속 객체·편집 체인·그림 개수 및 스트림 크기에 상한을 두었고 손상된 암호화 구조는 리더가 `doc.errors`로 반환한다.

PPT 소유 변경은 `dochan/crypto/ppt.py`, `dochan/office_binary/ppt.py`, `dochan/office_binary/officeart.py`, `tests/test_ppt_crypt.py`, `tests/test_officeart_delayed_crypto.py`, `scripts/probe_ppt_crypto.py`와 이 보고서이다. 공유 모델·출력 파일은 변경하지 않았다. `PPTReader`에는 선택적인 `password` 생성자 인자와 스트림 복호화 진입점만 추가했다. 별도 커밋은 만들지 않았으며 통합 변경에 대한 커밋 메시지로 `feat(crypto): PPT RC4 CryptoAPI 암호 문서 읽기 지원`을 제안한다.

리뷰에서 재현한 CMYK JPEG 거부는 `0xF01D`의 `0x6E2/0x6E3` 인스턴스를 추가해 수정했다. RGB·CMYK 각각 UID 1개와 2개를 합성 바이트로 검증했다. CMYK 암호 실물은 확보하지 못했으므로 이 세부 분기의 실물 검증은 미검증이다.

암호화 PPTX는 POI `test-data/slideshow`의 PPTX 95개와 LibreOffice `sd/qa/unit/data`의 PPTX 429개를 읽기 전용으로 조사했다. 524개 모두 CFB 매직 `D0 CF 11 E0 A1 B1 1A E1`을 갖지 않았다. 따라서 PPTX 암호화 실물 검증은 계속 미검증이다. 통합 담당자가 제공한 [MS-OFFCRYPTO] 2026-02-17판 2.4.2.3, 66쪽의 기본 암호 규정을 확인한 뒤 `password=None`일 때 빈 암호와 명세의 기본 암호를 최대 2개 후보로 시도하도록 구현했다. 명시적인 빈 암호나 잘못된 암호에는 기본 암호로 폴백하지 않는다. 관련 합성 테스트는 4개가 통과했지만 기본 암호 실물 표본은 없어 이 분기의 실물 검증은 미검증이다.

기본 암호 근거는 Microsoft [MS-OFFCRYPTO] 2.4.2.3의 UTF-8 16진수 `2f303148616e6e65732052756573636865722f3031`이다. [공식 명세](https://officeprotocoldoc.z19.web.core.windows.net/files/MS-OFFCRYPTO/%5BMS-OFFCRYPTO%5D.pdf) 5절 주석 28은 PowerPoint 2007/SP1에서 사용하고 SP2에서는 사용하지 않는다고 설명한다.
