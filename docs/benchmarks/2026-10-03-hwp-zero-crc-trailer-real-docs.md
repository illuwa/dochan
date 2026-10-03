# HWP 압축 스트림 꼬리의 CRC 0 허용과 그림 하나 때문에 문서가 비던 문제

2026-10-03. 공개 HWP/HWPX 7,038개를 다시 읽어 예외 0, `ERR` 진단 문서 37개를 확인했다. 그중 27개가 `Invalid compressed stream: trailing data checksum mismatch` 로
문서 전체를 읽지 못했다. 원인은 압축 스트림 끝 8바이트 꼬리(CRC32·ISIZE)의 CRC 칸이 0 으로 쓰인 것이다(ISIZE 는 실제 해제 크기와 같다).
hwplib 계열 생성기로 만든 공개 표본(`hwplib-*.hwp`, `getting_clickhere_text.hwp` 등)에서 나타난다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| HWP 본문 · 압축 스트림 꼬리 | 공개 `getting_clickhere_text.hwp` 외 26개 | 꼬리 바이트 관찰(CRC 0, ISIZE 일치)과 한컴오피스 HWP(Mac) 화면 | CRC 0 은 "기록 없음"으로 보고 ISIZE 는 그대로 검증해 문서를 읽는다 | 27/27 문서가 `ERR` 없이 읽힌다(본문 글자가 있는 문서 12개). `getting_clickhere_text.hwp` 의 본문·표·누름틀 글자가 한컴 화면과 같다 | 통과 |
| 회귀 | 나머지 공개 HWP/HWPX | 수정 전 출력 | 바뀌지 않는다 | CRC 가 0 이 아닌 꼬리는 전처럼 불일치를 거부한다(합성 테스트), 전체 테스트 통과 | 통과 |

CRC 가 0 이 아닌데 다르거나 ISIZE 가 다르면 전처럼 거부한다(`tests/test_hwp_zero_crc_trailer.py`). 배포용 문서의 정렬 꼬리 검증(`trailer_validator`)은 바꾸지 않았다.

## 해제 상한을 넘는 그림 하나

같은 재스캔에서 공개 `2026년 2분기 가축동향조사 결과 보도자료(최종).hwp` 가 `ERR: HWP stream validation failed: BinData/BINNC.bmp exceeds extracted BinData budget` 로
본문까지 통째로 비었다. 12MB 로 압축된 BMP(`BIN000C.bmp`) 하나가 그림 한 개 상한(100MB)을 넘었기 때문이다. 이제 그 그림만 생략하고 경고를 남긴다
(`WARN: HWP BinData/BIN000C.bmp exceeds the image size limit; image omitted`). 해제는 전처럼 상한에서 멈추므로 메모리 상한은 그대로다. 문서 전체 그림 예산을 다 쓰면
남은 그림을 버리되, 이미 읽은 본문은 버리지 않는다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| HWP 그림 · 해제 상한 | 공개 `2026년 2분기 가축동향조사 결과 보도자료(최종).hwp` | BinData 스트림 크기 관찰(12개 중 1개가 상한 초과) | 본문과 나머지 그림은 남고 그 그림만 생략 | 본문 32,060자, 그림 13개, `ERR` 0, 경고 1 | 통과 |

## HWPX 본문 섹션 크기 상한

공개 `pubinst-kostat_2022년_사회조사_결과_보도자료.hwpx` 는 본문 `Contents/section0.xml` 이 41.7MB(압축 1.4MB)라 XML 파트 공통 상한 32MB 에 걸려
`ERR: 섹션 … 크기 초과` 로 본문이 비었다. 본문 섹션만 64MB 상한을 따로 둔다(다른 XML 파트는 32MB 그대로). 이 문서는 2.2초, 최대 RSS 487MB 로
본문 362,434자·표 1,859개를 오류 없이 낸다. 요소 수(100만)·압축률·전체 해제 크기 상한은 그대로다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| HWPX 본문 · 큰 섹션 | 공개 `pubinst-kostat_2022년_사회조사_결과_보도자료.hwpx` | zip 항목 크기 관찰, 수정 전 `ERR` | 본문을 읽는다 | 362,434자, 표 1,859개, `ERR` 0 | 통과 |

