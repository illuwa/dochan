# HWP 압축 스트림 꼬리의 CRC 0 허용

2026-10-03. 공개 HWP/HWPX 7,038개를 다시 읽어 예외 0, `ERR` 진단 문서 37개를 확인했다. 그중 27개가 `Invalid compressed stream: trailing data checksum mismatch` 로
문서 전체를 읽지 못했다. 원인은 압축 스트림 끝 8바이트 꼬리(CRC32·ISIZE)의 CRC 칸이 0 으로 쓰인 것이다(ISIZE 는 실제 해제 크기와 같다).
hwplib 계열 생성기로 만든 공개 표본(`hwplib-*.hwp`, `getting_clickhere_text.hwp` 등)에서 나타난다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| HWP 본문 · 압축 스트림 꼬리 | 공개 `getting_clickhere_text.hwp` 외 26개 | 꼬리 바이트 관찰(CRC 0, ISIZE 일치)과 한컴오피스 HWP(Mac) 화면 | CRC 0 은 "기록 없음"으로 보고 ISIZE 는 그대로 검증해 문서를 읽는다 | 27/27 문서가 `ERR` 없이 읽힌다(본문 글자가 있는 문서 12개). `getting_clickhere_text.hwp` 의 본문·표·누름틀 글자가 한컴 화면과 같다 | 통과 |
| 회귀 | 나머지 공개 HWP/HWPX | 수정 전 출력 | 바뀌지 않는다 | CRC 가 0 이 아닌 꼬리는 전처럼 불일치를 거부한다(합성 테스트), 전체 테스트 통과 | 통과 |

CRC 가 0 이 아닌데 다르거나 ISIZE 가 다르면 전처럼 거부한다(`tests/test_hwp_zero_crc_trailer.py`). 배포용 문서의 정렬 꼬리 검증(`trailer_validator`)은 바꾸지 않았다.
