# PDF 속도 변경의 실물 출력 검증

속도 작업이므로 README의 `Supported Elements` 칸에 새 ✅를 제안하지 않는다. 변경 전 동일 문서의 Markdown·JSON·오류 목록 SHA-256을 정답으로 삼고 변경 후 전수 비교했다. 공개 파일명은 대표 표본이며 실제 판정은 각 코퍼스의 모든 PDF에 적용했다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| PDF 출력 불변 | `corpus/pdfjs-src/test/pdfs/freeculture.pdf` | 변경 전 동일 PDF의 세 출력 SHA-256 | 983/983 일치 | 983/983 일치 | 통과 |
| PDF 출력 불변 | `corpus/press-pairs/156784075.pdf` | 변경 전 동일 PDF의 세 출력 SHA-256 | 375/375 일치 | 375/375 일치 | 통과 |
| PDF 출력 불변 | `corpus/press-pairs-holdout/156782883.pdf` | 변경 전 동일 PDF의 세 출력 SHA-256 | 217/217 일치 | 217/217 일치 | 통과 |
| PDF 출력 불변 | `corpus/press-pairs-holdout2/156782662.pdf` | 변경 전 동일 PDF의 세 출력 SHA-256 | 232/232 일치 | 232/232 일치 | 통과 |
| PDF 출력 불변 | `corpus/press-pairs-holdout3/156782137.pdf` | 변경 전 동일 PDF의 세 출력 SHA-256 | 233/233 일치 | 233/233 일치 | 통과 |
| PDF 출력 불변 | 내부 PDF 80건 집계 | 변경 전 동일 PDF의 세 출력 SHA-256 | 80/80 일치 | 80/80 일치 | 통과 |

내부 표본은 파일명과 개별 결과를 기록하지 않았다. 전체 2,120건에서 변환 실패와 출력 해시 불일치가 없었다.
