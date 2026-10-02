# legacy Office 공용 기반 실물 검증

2026년 10월 2일 로컬 Apache POI 공개 코퍼스를 읽기 전용으로 조사했다. DOC·PPT·XLS 리더 본체와 README는 수정하지 않았다. 이 문서의 통과는 공용 파서 기능의 통과이며, 각 형식의 Supported Elements 칸을 ✅로 바꿀 근거는 아니다. 리더 연결과 문서 모델·Markdown 출력 검증은 후속 작업이 수행해야 한다.

구현은 [MS-ODRAW]의 OfficeArtRecordHeader, OfficeArtFBSE, OfficeArtBlip 계열, OfficeArtMetafileHeader, OfficeArtFSP, OfficeArtFOPT, OfficeArtFChildAnchor 구조와 원시 스트림 바이트를 기준으로 작성했다. POI 구현 코드를 읽거나 번역하지 않았다. POI 테스트에서는 표본명과 기대값만 확인했다. 네트워크를 사용하지 않았다.

## 검증 결과

POI 테스트 경로는 코퍼스 루트 아래의 상대 경로이다. `scratchpad`는 `poi-scratchpad/src/test/java/org/apache/poi`, `hssf`는 `poi/src/test/java/org/apache/poi/hssf`를 뜻한다.

| 칸 또는 공용 기능 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| PPT BLIP 저장소·JPEG/PNG/WMF/PICT/EMF | `pictures.ppt` | `scratchpad/hslf/usermodel/TestPictures.java:182-230`와 `clock.jpg`, `tomcat.png`, `santa.wmf`, `cow.pict`, `wrench.emf` | 5개이며 순서대로 jpg/png/wmf/pict/emf이다. | 5개를 복원했다. 각각의 페이로드 SHA-256이 독립 그림 파일과 일치했다. WMF의 placeable 헤더 22바이트와 PICT 파일 헤더 512바이트는 비교 정답에서 제외했다. | 공용 기능 통과이다. |
| PPT foDelay 지연 스트림 | `pictures.ppt` | PowerPoint Document의 FBSE 5개와 Pictures의 레코드 오프셋·페이로드를 직접 대조했다. | FBSE 색인 순서의 지연 BLIP 5개가 Pictures 직접 디코딩과 일치한다. | 5개가 모두 일치했다. | 공용 기능 통과이다. |
| DOC 내장 BLIP | `two_images.doc` | `scratchpad/hwpf/usermodel/TestPictures.java:76-90` | jpg 1개와 png 1개이다. | 두 종류와 개수가 모두 일치했다. | 공용 기능 통과이다. |
| DOC EMF 압축 해제 | `vector_image.doc` | `scratchpad/hwpf/usermodel/TestPictures.java:132-152`와 `vector_image.emf` | EMF 1개가 독립 파일의 전체 바이트와 일치한다. | EMF 1개의 SHA-256이 일치했다. 별도로 바이트가 없는 FBSE 1개도 색인을 보존했다. | 공용 기능 통과이다. |
| DOC 대체 텍스트 | `Picture_Alternative_Text.doc` | `scratchpad/hwpf/usermodel/TestPictures.java:357-362` | `This is the alternative text for the picture.`이다. | spid 1025의 wzDescription이 완전히 일치했다. PNG 1개도 복원했다. | 공용 기능 통과이다. |
| DOC BStore·지연 BLIP | `pictures_escher.doc` | `scratchpad/hwpf/converter/TestWordToHtmlConverter.java:98-100`의 PNG 두 개와 1Table FBSE/WordDocument 원시 레코드 | PNG 2개이다. | FBSE 2개가 WordDocument의 BLIP를 참조했고 PNG 2개를 복원했다. | 공용 기능 통과이다. |
| DOC 전체 그림 개수와 OfficeArt 경계 | `testPictures.doc` | `scratchpad/hwpf/usermodel/TestPictures.java:99-123`와 Data의 PICF/FBSE 원시 바이트 | POI 전체 그림은 7개이며 OfficeArt FBSE는 6개이다. | OfficeArt jpg 3개, png 2개, wmf 1개를 복원했다. PICF 오프셋 177169의 레코드는 길이 144바이트이고 FBSE가 없는 구형 저장 그림이다. | OfficeArt 6/6은 통과이다. 전체 그림 6/7은 미완료이며 리더 칸은 ⬜를 유지한다. |
| XLS MsoDrawingGroup·그림 형식 | `SimpleWithImages.xls` | `hssf/usermodel/TestHSSFPictureData.java:49-74`의 JPEG/PNG 크기 단언과 BIFF 0x00EB/CONTINUE 원시 재조립 | 원시 BStore 4개가 jpg/png/wmf/emf이며 JPEG는 192×176, PNG는 300×300이다. | 4개를 복원했고 JPEG/PNG 크기가 모두 일치했다. 주석 처리된 POI 개수 단언은 근거로 쓰지 않았다. | 공용 기능 통과이다. |
| XLS Macintosh 그림 | `53446.xls` | `hssf/usermodel/TestHSSFPictureData.java:85-103` | PNG 1개이며 크기는 78×76이다. | PNG 1개를 복원했고 크기가 일치했다. | 공용 기능 통과이다. |
| DIB→BMP | `23884_defense_FINAL_OOimport_edit.ppt` | Pictures의 DIB recType 0xF01F, recInstance 0x7A8, 헤더·픽셀 원시 바이트와 Pillow 판독 | DIB 1개를 BMP 파일로 읽을 수 있다. | BMP 94바이트를 복원했고 Pillow가 8×8 그림으로 판독했다. 전체 Pictures BLIP 86개와 지연 BStore에서 복원한 페이로드의 다중집합도 일치했다. | 공용 기능 통과이다. |
| TIFF BLIP | 없음 | 합성 레코드 테스트만 수행했다. | recInstance 0x6E4/0x6E5의 UID·tag를 건너뛴다. | 두 instance의 단위 테스트는 통과했다. 로컬 PPT Pictures 조사에서 TIFF BLIP 실물은 발견하지 못했다. | 실물 미검증이다. |
| 그룹·자식·패트리아크, FOPT, 앵커·클라이언트 원시 바이트 | 위 DOC/PPT/XLS 표본 | 실물의 SpContainer/FSP/FOPT 및 동일 버퍼 원시 바이트를 확인했다. 세부 API 계약은 `tests/test_officeart.py`의 합성 트리·속성 테스트에서 확인했다. | 형식별 해석 전에 레코드 구조와 속성을 보존한다. | 도형 트리를 추출했고 DOC 대체 텍스트를 별도 기대값으로 검증했다. 모든 도형 위치·텍스트박스의 형식별 의미까지 실물 정답과 비교하지는 않았다. | 파서 구조는 확인했다. 형식별 의미는 미검증이다. |
| 손상·크기·깊이·개수 상한 | 합성 바이트 | `test_global_depth_record_and_length_limits`, `test_metafile_uncompressed_bad_lengths_and_inflate_limit`, `test_bstore_truncated_entry_and_total_image_budget` | 예외 없이 해당 컨테이너를 멈추고 경고를 남긴다. | 단위 테스트에서 모두 통과했다. | 실물 손상 입력의 별도 기대값 검증은 미검증이다. |

9개 공개 Office 문서에서 총 108개 BLIP를 디코딩했다. FBSE는 134개이며, 바이트가 없는 항목도 보존했다. 프로브가 생성한 OfficeArt 경고는 0개이다. BLIP가 없는 FBSE를 문서 실패로 취급하지 않았다. JPEG·PNG·EMF·WMF·PICT·DIB는 실물로 확인했고 TIFF는 미검증이다.

## 재현 방법

저장소 루트에서 다음 명령을 실행한다. 코퍼스 경로를 인자로 받으며 표본은 저장소에 복사하지 않는다.

```sh
/usr/bin/python3 -m scripts.probe_officeart \
  corpus/poi-src/test-data \
  --output .codex-work/officeart-probe.json
/usr/bin/python3 -m pytest tests/test_officeart.py -q \
  -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

DOC 프로브는 호스트 구조 사이의 완전한 OfficeArt 컨테이너/FBSE 헤더를 탐색한다. 채택한 레코드 범위를 건너뛰어 내장 BLIP를 중복 집계하지 않는다. 이 탐색은 실물 관찰용 어댑터이며 FIB·PICF 기반 DOC 리더 구현이 아니다. PPT는 Pictures를 직접 파싱하고 PowerPoint Document의 FBSE와 대조한다. XLS는 BIFF MsoDrawingGroup와 바로 뒤 CONTINUE를 재조립한다. 프로브가 후속 리더 통합 코드를 대신하지 않는다.

## 최종 API

`dochan.office_binary.officeart`에서 다음 API를 제공한다. `errors`에는 호출자의 `doc.errors`를 넘길 수 있다. 경고 문자열은 `WARN: OfficeArt ...`이며 예외로 문서 전체를 실패시키지 않는다.

| API | 반환과 계약 |
|---|---|
| `parse_header(data, offset=0)` | 완전한 8바이트 헤더이면 `RecordHeader(rec_ver, rec_instance, rec_type, rec_len)`를 반환하고 잘렸으면 `None`을 반환한다. |
| `parse_records(data, offset=0, length=None, limits=None, errors=None)` | `List[Record]`를 반환한다. offset은 전달 버퍼 기준이다. `Record.header`, `offset`, `data: memoryview`, `children`을 제공한다. 컨테이너 payload를 복사하지 않는다. |
| `walk_records(records)` | 전위 순회의 레코드 반복자를 반환한다. |
| `decode_blip(record, limits=None, errors=None)` | `(image_format, bytes)` 또는 `None`을 반환한다. 형식은 `jpg`, `png`, `bmp`, `tiff`, `emf`, `wmf`, `pict`이다. |
| `read_bstore(records, delayed_stream=None, limits=None, errors=None)` | `List[BlipEntry]`를 반환한다. 항목은 `index`, `bt_win32`, `bt_macos`, `uid`, `size`, `c_ref`, `fo_delay`, `cb_name`, `name`, `image`을 제공한다. 1부터 시작하는 pib 색인과 실패 항목을 보존한다. delayed_stream은 호출자가 선택한 WordDocument/Pictures 버퍼이다. offset 0도 유효하다. |
| `parse_properties(record, errors=None)` | 속성 ID별 `Property(id, value, is_blip_id, is_complex, data)` 사전을 반환한다. complex 데이터는 고정 테이블 뒤에서 순서대로 소비한다. 잘리면 이후 속성으로 바이트를 잘못 넘기지 않는다. |
| `read_shapes(records, errors=None)` | 중첩 `List[Shape]`를 반환한다. `spid`, `flags`, `shape_type`, `is_group`, `is_child`, `is_patriarch`, `properties`, `property_tables`, `pib`, `name`, `description`, `textbox_id`, `child_anchor`, `client_anchor`, `client_data`, `client_textbox`, `children`, `record`를 제공한다. |

FOPT 0xF00B, 보조 FOPT 0xF121, 3차 FOPT 0xF122의 개별 표를 보존한다. 편의용 `properties`는 나중 표의 같은 ID가 앞선 값을 덮어쓴다. `pihlShape` 0x0382는 일반 속성으로 보존하고 형식별 하이퍼링크 해석은 하지 않는다. `wzName`과 `wzDescription`은 UTF-16LE로 읽으며 끝의 NUL을 제거한다. FChildAnchor는 signed 32비트 좌표 네 개이고 ClientAnchor/ClientData/ClientTextbox는 원시 바이트이다.

EMF/WMF/PICT는 metafile 페이로드를 반환한다. WMF placeable 헤더나 Macintosh PICT 파일 헤더를 임의로 합성하지 않는다. DIB는 CORE/INFO 계열 헤더, 팔레트, bitfield 마스크를 고려한 BMP 파일 헤더를 붙인다. 모든 OfficeArt 속성의 complex 배열 내용을 의미 단위로 해석하는 API는 제공하지 않는다.

기본 `Limits`는 깊이 32, 전체 레코드 100,000개, 스트림 128 MiB, 개별 레코드 64 MiB, 개별 출력 이미지 32 MiB, BStore 전체 출력 이미지 128 MiB이다. 이 값은 악성 입력 방어용 정책이며 파일 형식 명세의 최대값이라는 주장을 하지 않는다. 압축 해제는 선언된 cbSize와 실제 출력 길이를 확인하고 출력 한도보다 한 바이트까지만 생산해 초과 여부를 판정한다. 깊이는 호출자가 크게 설정하더라도 64를 넘지 않는다.
