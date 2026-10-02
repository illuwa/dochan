# HWP·HWPX 리뷰 반영 실물 검증

2026년 10월 2일 `illuwa/w-hwp`에서 두 리뷰를 합쳐 검증했다. 공개 코퍼스는 읽기 전용으로 사용했고, README와 CHANGELOG는 수정하지 않았다. 원래 검증 문서의 비밀번호·양식 상태·스타일 기본값·차트 캡션 기대값도 정정했다.

## 칸별 판정과 실물 증거

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| HWP 변경 추적 | `korea-mid-30-7_(즉시보도_통전지)농촌진흥청_승용마,_제주_자치경찰단_기마대에_첫_도입(축산원).hwp`와 HWPX 짝 | 원시 DocInfo·ViewText 범위와 HWPX 마커를 대조하고, final 투영을 BodyText와 별도로 비교했다. | 메타데이터·각 모드 문단과 final 투영이 같아야 한다. | 변경 종류 10/10·작성자 1/1, 각 모드 원시 문단 79/79·모델 문단 49/49가 같았다. final 투영과 BodyText는 49문단·1,620자로 정확히 같았다. | 텍스트 비교는 통과했다. HWP 진단은 0개이나 HWPX 짝에는 missing-begin 진단이 모드별 1개 있으므로 오류 없는 완전한 정답 문서라고 부르지 않는다. |
| HWP 변경 추적 | `고용노동부_2019-03-04_3.5 소규모 사업장 사망사고 안전점검으로 예방해요(안전보건공단).hwp` | final ViewText 투영과 같은 컨테이너의 BodyText를 비교했다. | 두 경로가 같아야 한다. | 37문단·1,244자가 정확히 같고 두 경로 진단은 0개였다. | final 교차 검증은 통과했다. original의 별도 정답은 없다. |
| HWP 변경 추적 | `rhwp-1130000-201900011_D0150004-1-002_2017년기준_시장구조조사.hwp` | 동일한 레코드 상한으로 ViewText final 투영과 BodyText를 비교했다. | 완전하게 읽힌 두 경로가 같아야 한다. | ViewText는 39,420문단·334,235자, BodyText는 49,509문단·386,964자였으며 두 경로 모두 200,000 레코드 상한 ERR가 있었다. | 불완전하다. 공개 변경 추적 전체 3문서 중 완전 일치는 2/3이다. original의 HWPX 정답 표본은 앞의 1쌍뿐이다. HWP 변경 추적 칸은 ⬜ 유지를 제안한다. |
| HWPX 변경 추적 | `hwpxlib-ChangeTrack.hwpx` | 기존 고정 XML gold를 재검증했다. | preserve/final/original의 고정 문구가 같아야 한다. | 세 모드 3/3이 일치했고 진단은 0개였다. | 기존 텍스트 투영 범위의 ✅ 제안을 유지한다. |
| HWP 컨트롤/스마트 태그 텍스트 | `form-002.hwp`와 `form-02.hwp` 및 각 HWPX 짝 | ButtonSet의 Value와 HWPX value·caption을 비교했다. | 체크·라디오 상태를 포함한 표시값이 같아야 한다. | 양식은 180/180·5/5, 모델 문단은 514/514·4/4가 같았다. | 이 두 쌍은 통과했다. 공개 양식은 11문서·235개를 읽었다. `form-01`의 콤보는 4/5만 같아 전체 칸은 ⬜를 유지한다. |
| HWP 누름틀 | 아래 공개 보도자료 4개 | 필드 CTRL_HEADER 속성 bit 15가 모두 켜져 있고, 안내문 삽입 여부를 관찰했다. | 입력된 본문에 안내문을 추가하지 않아야 한다. | 8개 누름틀에서 안내문 삽입은 0개이고 문서 진단도 0개였다. | 리뷰의 오삽입을 제거했다. |
| HWP 누름틀 양성 | `field-01-memo.hwp`, `field-01.hwp`, `rhwp-field-01.hwp` | bit 15가 꺼져 있고 start~end 원시 WCHAR가 필드 끝 컨트롤뿐인 경우를 관찰했다. | 원시 조건을 만족하는 빈 누름틀만 안내문을 낸다. | 각각 6·8·8개로 총 3문서·22개가 남았다. | 원시 조건의 양성 사례다. 세 문서 모두 HWPX 짝이 없으므로 안내문 정답 검증은 미검증이다. |
| HWPX 컨트롤/스마트 태그 텍스트 | `SimpleEdit.hwpx`, `hwp2hwpx-from_12.hwpx` | 첫 문서의 passwordChar="X"와 두 문서의 입력 컨트롤을 확인했다. | 첫 문서는 비밀번호를 내지 않고 두 번째는 일반 입력을 보존한다. | 첫 문단 목록은 빈 목록이고 두 번째는 `테스트`였다. | 정정한 기대값으로 2/2가 일치했다. |
| HWPX 체크박스 | `rhwp-36341511_masked.hwpx` | 원시 XML의 체크박스 value를 순서대로 읽었다. | 26개 중 선택된 13개는 `[x]`, 나머지는 `[ ]`여야 한다. | 26/26개 상태와 순서가 일치했다. | 상태 표시는 통과했다. 콤보 선택값 실물 검증이 남아 전체 칸은 ⬜를 유지한다. |
| HWP·HWPX 스타일 | `sample-outline-list.hwp`, `sample-mixed-lists-with-outline.hwp`와 HWPX 짝 | HWPX 개요 제목 수준과 직접 글자서식을 비교했다. | 제목 수준 1~3과 기존 직접 서식이 같아야 한다. | 2쌍·21/21문단의 제목·굵게·기울기 서명이 같고 진단은 0개였다. | 제목·유효 참조 계약에서 ✅ 제안을 유지한다. 직접 글자모양이 없는 문단의 스타일 기본값은 적용하지 않는다. 부모 스타일 체인 자체를 뜻하면 —를 제안한다. |
| HWP 문단 정렬 | `(260723)보도자료-국민이_직접_참여하는_소나무_관리_토론회，_제2차_공론의_장_마련.hwp`와 HWPX 짝 | 문단 모양 2의 props=0x18c와 HWPX CENTER(3)를 대조했다. | 정렬은 속성 bit 2~4여야 한다. | 기존 low3는 4, bit 2~4는 3이었다. 같은 문서 52개 전체는 30/52에서 52/52로 일치했다. | 실물 근거를 확인한 뒤 비트 위치를 수정했다. |
| HWPX 차트 | `2차원원형.hwpx`, `꺽은선형.hwpx`, `14_chart.hwpx`, `charts.hwpx` | 원시 차트 캐시·명시 제목과 공통 OOXML 캡션 계약을 비교했다. | 제목을 보존하고 차트 캡션은 첫 유효 계열 표에 한 번만 낸다. | 네 차트 검증이 모두 통과했다. `charts.hwpx` 첫 차트 캡션은 3회에서 1회로 줄었다. | 통과했다. 중복 idx 제목 캐시의 무효값 배제는 합성 테스트로 검증했다. |
| HWP 암호화 문서 | `alhangeul-macos-hwpspec.hwp`, `openhwp-한글문서파일형식_배포용문서_revision1.2.hwp` 등 공개 배포용 집계 | 독립 raw-deflate·CRC32·실제 길이 계산과 모델 읽기를 재실행했다. | 모든 알려진 trailer가 일치하고 본문을 읽어야 한다. | 공개 27파일(고유 20문서)·65/65섹션 검사값이 일치했고 27/27파일의 본문이 비어 있지 않으며 진단은 0개였다. | 배포용 범위에서 ✅ 제안을 유지한다. 암호 보호 해독과 미압축 실물은 미지원·미검증이다. |

보도자료 4개는 `nts-241226학자금체납자 2,634명 채무조정을 통해 65억 원 의무상환액을 면제받았습니다.hwp`, `nts-20260108 1월26일(월)까지 부가가치세 확정신고 하세요. 민생지원을 위해 소상공인 납부기한 2개월 직권연장.hwp`, `korea-20260726_보도자료_기상청 인사발령(4급 승진).hwp`, `pubinst-kma_20260726_보도자료_기상청_인사발령(4급_승진).hwp`다.

정렬 비교의 넓은 탐색에서는 문단 모양 ID 집합이 같은 474쌍·32,485개를 비교했다. low3 일치는 21,880개, bit 2~4 일치는 31,991개였다. 모든 문단 모양이 일치한 쌍은 7쌍에서 440쌍으로 늘었다. 같은 이름과 ID만으로 내용 동일성을 보장할 수 없으므로 나머지 34쌍을 파서 오류라고 단정하지 않는다. 수정의 직접 근거는 원시 바이트와 모든 모양이 일치한 공개 쌍이다.

## 구현 판정과 제한

preserve는 HWPX처럼 삽입·삭제 텍스트를 모두 보존하는 ViewText 경로다. final은 BodyText를 재투영 없이 읽는다. original은 ViewText의 삽입 범위를 투영한다. 제외해야 할 범위와 확장 컨트롤이 겹치면 컨트롤을 조용히 남기지 않고 `ERR: HWP revision partial [control]`을 한 번 기록한다. 개체 변경을 완전 지원한다고 주장하지 않는다.

누름틀은 bit 15가 꺼지고 원시 본문이 정확히 8 WCHAR 필드 끝 컨트롤뿐일 때만 안내문을 넣는다. 양식 표시값이 추가된 본문도 확인한다. 체크·라디오 표시는 두 형식과 DOCX에서 같은 마커를 쓰며 임의 공백을 추가하지 않는다. 비밀번호 입력 내용은 두 형식 모두 숨긴다.

알 수 없는 배포용 trailer를 경고만 내고 통과시키자는 권고는 이번에는 적용하지 않았다. 알려진 CRC·길이·패딩이 손상된 경우는 합성 테스트에서 거부하며, 공개 표본은 검증한 두 trailer 형식으로 읽힌다. 미지 형식을 구별할 실물 근거 없이 검사값 오류를 무시하지 않는다. 기존 알고리즘의 참고 출처 기록은 HEAD에서 복원했으며 새 구현 출처라고 덧붙이지 않았다.

## 재현 명령

```bash
/usr/bin/python3 -m scripts.probe_hwp_features /Users/illuwa/dev/personal/dochan/corpus/hwp-public
/usr/bin/python3 -m scripts.probe_hwp_review /Users/illuwa/dev/personal/dochan/corpus/hwp-public
/usr/bin/python3 -m scripts.probe_hwpx_features /Users/illuwa/dev/personal/dochan/corpus/hwp-public/hwpx
/usr/bin/python3 -m scripts.probe_hwp_styles /Users/illuwa/dev/personal/dochan/corpus/hwp-public
/usr/bin/python3 -m scripts.probe_hwp_distribution /Users/illuwa/dev/personal/dochan/corpus/hwp-public/hwp
/usr/bin/python3 -m scripts.compare_hwp_pairs /Users/illuwa/dev/personal/dochan/test_pairs/
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

내부 76쌍의 수정 전후 집계는 평균 토큰 비율 0.9997, 최저 0.9927, HWPX/HWP 표 796/795, 표 구조 일치율 0.9987, 평균 셀 포함률 0.9991, 중첩 51/51, 서식 일치율 1.0, 오류 쌍 0으로 같았다. 내부 이름과 본문은 기록하지 않았다.

최종 전체 테스트는 **1,925 passed, 24 skipped, 14 xfailed**였다. `git diff --check`도 통과했다. 배포용 섹션은 슬롯형 64개·packed형 1개이며 원시 문단 71,435개 중 엄격 포함은 71,432개, 링크 주석만 제외한 포함은 71,435개였다.

공개 기능 스캔은 5,363파일 중 29개의 읽기 실패와 5개 부분 레코드 진단을 기록했다. 누름틀은 읽힌 범위에서 228문서·4,387개였고 구식 명령 641개는 typed 파서 범위 밖이었다. 별도 정렬 비교는 잘못된 ZIP 1쌍을 제외했으며 해당 HWP의 누름틀 스캔은 계속했다. HWPX 기능 프로브는 14/14가 통과했다. `scourt-개인회생절차 개시결정안내문(2020.3.1.시행)(D5519).hwp`의 최종 제목 집계는 H1 4개·H2 1개·일반 문단 9개로 H4 이상은 없고 진단은 0개였다.
