# 끝부분이 손상된 ZIP 문서의 본문 복구 검증

2026-10-04에 공개 코퍼스를 읽기 전용으로 검사했다. 로컬 항목을 보존한 중앙 디렉터리 복구와 본문 부품 검증은 구현했지만, **요청한 전체 수용 기준은 미통과다.** 정상 ZIP 출력 회귀는 없으며 기존 손상 DOCX 하나를 복구했다. 선택 부품 손실과 표준 ZIP 판별의 한계 때문에 모든 정상 원본 절단을 동일 출력으로 복구했다고 주장하지 않는다. `Supported Elements`의 체크는 바꾸지 않았다.

## 범위와 독립 정답

`corpus/poi-src/test-data/`에서 614개, `corpus/lo-src/`에서 3,032개, `corpus/hwp-public/hwpx/`에서 1,687개의 ZIP 시그니처를 확인했다. 합계 5,333개로, 작업 관찰의 5,374개보다 41개 적다. 차이의 원인은 확인하지 못했지만 대상 손상 ZIP 40개는 모두 포함한다. 소스 코드 확장자는 서명 읽기 대상에서도 제외한다. 내부 문서는 사용하지 않았다.

변경 전 저장소 소스의 `Dochan`으로 Markdown SHA-256·문자 수·진단만 저장했다. 정상 ZIP 5,293개 중 OOXML·HWPX로 식별되는 문서는 4,364개이고, 나머지는 다른 ZIP 패키지다. 변경 후 정상 ZIP 5,293/5,293개의 출력 해시가 일치했으며 처리 중 예외·시간 초과는 0개다.

절단 실험은 원본의 중앙 디렉터리 오프셋과 마지막 로컬 항목 오프셋으로 절단점을 계산했다. 원본 및 절단본은 기존 형식 리더에 메모리 버퍼로 전달했다. 원본 메모리 변환 해시는 변경 전 경로 변환 해시와 모두 같다. 잘린 파일이나 출력 전문은 디스크에 쓰지 않았다.

초기에는 기존 리더가 ERR 없이 비어 있지 않은 출력을 낸 문서에서 시드 `20261004`로 형식별 150개를 뽑았다. 원본부터 헤더·관계·CRC가 불일치하는 표본과 요청상 미지원 ZIP64가 섞여 있어 이 결과도 보존했다. 별도 `--intact-samples` 실험에서는 복구 코드를 호출하지 않는 원본 검사로 로컬/중앙 필드·연속성·CRC·모든 내부 관계 대상·HWPX 섹션 선언의 정합성을 확인한 뒤 같은 시드로 다시 150개씩 뽑았다. 원본 103개를 제외했고, 적격 후보는 DOCX 1,710개·PPTX 497개·XLSX 315개·HWPX 1,598개다. 내장 ZIP을 가진 온전한 원본과 관계 없는 최소 문서는 제외하지 않았다.

## 형식별 절단 결과

각 형식의 원본은 150개이고 원본마다 여섯 위치를 잘라 900번, 합계 3,600번 검사했다. 중앙 디렉터리 직전·중간 절단은 WARN만 남기면서 원본 해시와 같아야 한다. 나머지 절단은 ERR·빈 출력이거나 ERR 없는 동일 출력이어야 한다.

| 형식 | 중앙 두 절단 동일·WARN | 전체 판정 통과 | ERR 없는 해시 차이 | 정상 ZIP 회귀 | 판정 |
|---|---:|---:|---:|---:|---|
| DOCX | 288/300 | 877/900 | 11 | 1784/1784 | 미통과이므로 체크 변경을 제안하지 않는다. |
| PPTX | 292/300 | 822/900 | 70 | 544/544 | 미통과이므로 체크 변경을 제안하지 않는다. |
| XLSX | 298/300 | 848/900 | 50 | 351/351 | 미통과이므로 체크 변경을 제안하지 않는다. |
| HWPX | 300/300 | 896/900 | 4 | 1685/1685 | 미통과이므로 체크 변경을 제안하지 않는다. |

적격 원본 실험의 판정 통과는 3443/3,600개다. 원본 동일 출력은 2005개, ERR·빈 출력은 1460개다. 이 중 중앙 두 절단의 ERR 22개는 해당 절단의 필수 성공 조건을 만족하지 못했다. ERR 없는 해시 차이는 135개이고, ERR가 있는데 비어 있지 않은 출력·처리 중 예외·시간 초과는 각각 0개다. 프로브는 이 실패를 숨기지 않고 종료 코드 1을 반환했다.

원본 정합성을 선별하지 않은 초기 600개 실험은 3401/3,600개 판정 통과, 중앙 절단 실패 50개, ERR 없는 차이 149개다. 적격성을 선별한 후에도 0개 차이 기준을 만족하지 못했으므로 표본 교체를 성공 근거로 쓰지 않는다.

## 미통과 원인과 정책 충돌

문서 속성의 `docProps/core.xml`은 선택 부품이지만 기존 Markdown이 작성자·제목을 출력한다. 따라서 속성이 잘리면 본문 XML이 모두 있어도 출력 해시가 달라진다. 그림의 부품이 없으면 Office의 별도 이미지 요소가 사라지거나 HWPX의 `BinData/image1.png` 링크가 `image1`로 바뀌는 사례도 있다. 적격 표본의 Office 차이는 DOCX 11개·PPTX 70개·XLSX 50개이고 HWPX 그림 경로 차이는 4개다. 이는 없는 그림·속성을 WARN으로 허용하라는 계약과 ERR 없는 출력의 전체 해시를 원본과 같게 만들라는 계약 사이의 충돌이다. 출력에 영향을 주는 선택 부품도 필수로 취급할지 사용자에게 질문했으며 답변은 아직 없다.

중앙 디렉터리 두 절단의 실패 22개 중 18개는 온전한 원본 9개의 내장 XLSX 종료 레코드를 표준 `zipfile`이 대신 읽어 여는 경우다. 이 경우 `BadZipFile`이 발생하지 않아 지정된 복구 조건에 들어가지 않는다. 나머지는 주 문서 관계 부품이 없는 최소 DOCX 하나와, 원본부터 관계 속성이 있지만 해당 worksheet 관계 파일이 없는 XLSX 하나의 두 절단이다. 누락된 관계 파일을 허용하면 없어졌을 수 있는 스타일·노트·그림 연결의 완결성을 증명할 수 없어 현재는 거부한다. ZIP 열기 성공 후 첫 로컬 항목과 중앙 디렉터리의 일관성을 추가 검사하는 방안은 별도 계약 조정이 필요하다.

원본 `hwpx-01-saved.hwpx`는 `secCnt=1`인데 실제 섹션이 두 개다. 잘린 헤더와 첫 섹션만으로 원래 두 번째 섹션이 있었음을 알아낼 근거가 없어 원본 정합성 검사에서 제외했다. 원본 정합성을 선별하지 않은 실험의 차이 한 개로 남겼으며, 헤더 선언이 잘못된 원본까지 완결성을 보장한다고 주장하지 않는다. 11개 섹션에서 `content.hpf`가 잘려 기존 사전순 정렬과 실제 읽기 순서가 달라지는 사례는 완결성을 입증할 수 없는 경우로 거부한다. 참조된 HWPX 차트 및 OOXML VML 관계 부품이 없는 경우도 ERR·빈 출력으로 처리한다.

## 기존 손상 ZIP 40개 전수

원본이 온전한 짝을 갖지 않는 손상 표본의 기대값은 남은 로컬 바이트의 CRC·deflate 종료와 본문 관계 선언의 정합성이다. 원본 전체와의 출력 동일성 정답은 위 절단 실험에서 별도로 확보했다. 현재 40개 중 하나가 WARN과 함께 변환되고 39개는 ERR·빈 출력이다. 모든 표본에 복구 WARN이 있으며 예외·시간 초과는 0개다.

`truncated62886.docx`는 로컬 항목 26개에서 본문 부품을 검증하여 1,228자의 Markdown을 출력한다. 출력 SHA-256은 `252297b7e891361f901ab15efbc9703efadaef5cd72208590055a4d91eb45b36`이다. `Divino_Revelado.pptx`는 로컬 항목 65개가 남아도 필수 `ppt/tableStyles.xml`이 없어 거부한다. 발표·보기 속성과 name/value 태그는 문서 속성으로 취급하지만 표 스타일은 선택 속성이 아니다. name/value 태그의 구조는 공개 `aascu.org_workarea_downloadasset.aspx_id=5864.pptx`의 `ppt/tags/tag1.xml` 바이트에서 확인했다.

관찰에 제시된 국가재난관리지원기업 평가 기준 HWPX는 네 로컬 항목이 남았지만 `Contents/section0.xml`의 raw deflate가 끝나지 않는다. 독립 `zlib.decompress(..., -15)`도 불완전 스트림으로 실패한다. 헤더의 CRC는 일치하나 섹션의 완결성을 검증하지 못하므로 복구 성공으로 세지 않았다.

| 칸 | 공개 표본 파일 | 정답 근거 | 기대 | 변경 전 | 실제 | 판정 |
|---|---|---|---|---|---|---|
| ZIP 본문 복구 | corpus/hwp-public/hwpx/ministry-[별표 3] 국가재난관리지원기업 지정 공모 평가 기준 및 평가 방법(제7조 관련)(국가재난관리지원기업 및 국가재난관리물류기업 지정 공모 운영 지침).hwp | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: 지원하지 않는 ZIP 문서 형식 | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 4개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(Contents/section0.xml: deflate EOF missing) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/hwp-public/hwpx/nts-20250512 봄 향기 가득한 날, 성실납세에 아름다운 음악으로 보답.hwpx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: 유효하지 않은 HWPX 파일 | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 6개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음('Contents/section0.xml') | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIFuzzer-6709287337197568.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 8개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/_rels/document.xml.rels: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-4791943399604224.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 10개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/_rels/document.xml.rels: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-4959857092198400.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 15개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/numbering.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-4961551840247808.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 4개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/document.xml: deflate EOF missing) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-5166796835258368.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 5개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/_rels/document.xml.rels) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-5313273089884160.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 5개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/fontTable.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-5564805011079168.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 6개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/document.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-5569740188549120.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 6개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/theme/theme1.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-6061520554164224.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 9개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/document.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-6120975439364096.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 32개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/document.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/clusterfuzz-testcase-minimized-POIXWPFFuzzer-6442791109263360.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 1개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/document.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/crash-517626e815e0afa9decd0ebb6d1dee63fb9907dd.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: DOCX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 6개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(word/document.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/document/truncated62886.docx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 필수 부품이 검증되므로 WARN과 본문을 출력해야 한다. | ERR: DOCX package parse failed: File is not a zip file | 1228자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 26개를 복구함 | WARN 복구를 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/Divino_Revelado.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 65개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/tableStyles.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIFuzzer-5205835528404992.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 41개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/presentation.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-4838644450394112.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 10개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/slideMasters/slideMaster1.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-4986044400861184.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 29개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/slides/slide7.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-5463285576892416.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 46개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/slides/slide1.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-5471515212382208.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 10개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/tableStyles.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-5611274456596480.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 12개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(_rels/.rels: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-6071540680032256.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 7개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/_rels/presentation.xml.rels: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-6254434927378432.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 9개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/slideMasters/slideMaster1.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-6372932378820608.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 82개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/slides/slide7.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIXSLFFuzzer-6435650376957952.pptx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: PPTX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 8개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(ppt/slideMasters/slideMaster1.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-4828727001088000.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 0개를 복구함 / ERR: 손상된 ZIP 문서 — 중앙 디렉터리가 없고 본문 부품을 찾지 못함 | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-5089447305609216.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 5개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/workbook.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-5185049589579776.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 14개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/workbook.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-6123461607817216.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 12개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/workbook.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-6419366255919104.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 14개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/drawings/drawing1.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-POIXSSFFuzzer-6448258963341312.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 9개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/workbook.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5025401116950528.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 4개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/workbook.xml: deflate decoded size mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5542865479270400.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 10개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/_rels/workbook.xml.rels) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-5636439151607808.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 1개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음('_rels/.rels') | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6504225896792064.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 8개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/worksheets/sheet1.xml) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/clusterfuzz-testcase-minimized-XLSX2CSVFuzzer-6594557414080512.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 0개를 복구함 / ERR: 손상된 ZIP 문서 — 중앙 디렉터리가 없고 본문 부품을 찾지 못함 | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/crash-274d6342e4842d61be0fb48eaadad6208ae767ae.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: Bad magic number for central directory | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 9개를 복구함 / ERR: 손상된 ZIP 문서 — 본문 부품 일부가 없음(xl/workbook.xml: deflate extent/size/CRC mismatch) | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/deep-data.xlsx | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: XLSX package parse failed: File is not a zip file | 0자. WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 0개를 복구함 / ERR: 손상된 ZIP 문서 — 중앙 디렉터리가 없고 본문 부품을 찾지 못함 | ERR·빈 출력을 확인했다. |
| ZIP 본문 복구 | corpus/poi-src/test-data/spreadsheet/rde.imf.ru_sites_default_files_rde_documents_vodootvedenie_2020.xlsb.xls | 원본 로컬 바이트·CRC·본문 관계 및 프로브 진단 | 검증되지 않은 본문은 ERR와 빈 출력으로 거부해야 한다. | ERR: 지원하지 않는 ZIP 문서 형식 | 0자. ERR: 손상된 ZIP 문서 — 중앙 디렉터리가 없고 본문 부품을 찾지 못함 / WARN: ZIP 중앙 디렉터리가 없어 로컬 헤더에서 부품 176개를 복구함 | ERR·빈 출력을 확인했다. |

## 구현과 재현

복구는 PKWARE APPNOTE의 로컬 헤더(4.3.7), 데이터 서술자(4.3.9), 중앙 디렉터리(4.3.12), 종료 레코드(4.3.16) 필드와 바이트 관찰을 근거로 직접 구현했다. 다른 프로젝트 구현 코드는 구현 근거로 사용하지 않았다. stored·deflate만 허용하고 ZIP64·암호화·미지원 방식에서 멈춘다. 크기가 없는 stored 서술자는 경계를 찾지 않는다. 로컬 헤더 사이의 쓰레기를 건너뛰지 않고 같은 이름은 첫 항목만 쓴다.

입력 512 MiB·항목 10,000개·항목 해제 100 MiB·전체 해제 512 MiB·압축비 2,000배 한도와 기존 형식별 XML 한도를 적용한다. 서술자의 deflate 경계는 작은 출력 청크로 찾는다. 필수 부품은 실제 해제 길이·CRC뿐 아니라 deflate EOF와 정확한 압축 범위도 확인한다. 표준 `ZipExtFile`은 선언된 길이에서 멈춰 불완전 deflate를 허용할 수 있어 이 검사를 추가했다. 관계 그래프는 방문·예약 집합으로 중복 예약과 순환을 제한한다. 선택 관계는 알려진 OOXML URI만 인정하며, 알 수 없는 URI가 `image`로 끝난다고 선택 부품으로 취급하지 않는다. 관계 속성의 Unicode 접두사와 긴 공백도 검사한다.

신규 합성 테스트 88개가 통과했다. stored·deflate·서술자 서명 유무·중복 이름·ZIP64·암호화·가짜 삽입 항목·자원 상한·CRC·deflate 종료·필수 관계 누락·본문 완결 WARN·네 형식·잘못된 확장자·단일/다중 worker 배치를 검증했다. 실패를 먼저 확인한 뒤 구현했다. 전체 테스트는 5,601개 통과, 36개 건너뜀, 14개 예상 실패이며 Ruff와 로컬 경로 검사도 통과했다. 기존 테스트 단언을 바꾸지 않았고 런타임 의존성도 추가하지 않았다.

```bash
/usr/bin/python3 -m scripts.probe_zip_salvage corpus --source-root ORIGINAL_SOURCE --baseline .codex-work/zip-salvage-before.jsonl
/usr/bin/python3 -m scripts.probe_zip_salvage corpus --compare .codex-work/zip-salvage-before.jsonl --output .codex-work/zip-salvage-results-raw.json
/usr/bin/python3 -m scripts.probe_zip_salvage corpus --compare .codex-work/zip-salvage-before.jsonl --intact-samples --output .codex-work/zip-salvage-results-intact.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
ruff check dochan scripts tests
```

`ORIGINAL_SOURCE`는 변경 전 소스 스냅샷의 경로 인자다. 위 비교 명령은 현재 확인한 수용 기준 실패 때문에 종료 코드 1이 정상적인 기록이며, 이를 통과로 표기하지 않는다.
