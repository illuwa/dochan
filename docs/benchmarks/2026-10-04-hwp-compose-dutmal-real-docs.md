# HWP 글자 겹침·덧말과 HWPX 덧말 실물 검증

한컴 「한글문서파일형식 5.0 revision 1.3」 4.3.10.12와 4.3.10.13의 컨트롤 구조를 기준으로 읽었다. 동일 원본의 HWPX `composeText`, `mainText`, `subText`를 본문 문자열의 정답지로 삼았다. HWP와 HWPX 공개 짝은 수집 파일명이 아니라 `corpus/hwp-public/SOURCES.json`의 원본 URL로 판별했다. URL의 조회 문자열도 비교하고, 같은 로컬 파일을 가리키는 중복 출처는 한 번만 셌다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| HWP 글자 겹침 `tcps` | `corpus/press-pairs/156783561.hwp`와 `.hwpx`, 공개 `hwp2hwpx-from_5.hwp` ↔ `hwp2hwpx-from_7.hwpx`, `sample-compose-all-shapes`, `mel-001`, `table-vpos-01` | HWPX `composeText`, 공개 명세 4.3.10.12, 보도자료 PDF 텍스트 층 | 겹칠 문자를 인라인 위치에 넣고, 테두리 없는 PUA는 HWPX처럼 보존한다. | 원본 URL로 확인한 공개 짝 50/50곳이 일치했다. 이 가운데 `hwp2hwpx`의 15/15곳, 전체 테두리 샘플의 28/28곳, 테두리 없는 PUA 표본의 6/6곳이 포함된다. 보도자료 제목도 두 형식에서 일치했다. | 단위 테스트와 실물 짝 검증 통과. ✅ 제안. |
| HWP 덧말 `tdut` | 공개 `hwp2hwpx-from_8.hwp` ↔ `hwp2hwpx-from_11.hwpx`, `sample-dutmal-basic.hwp`와 `.hwpx` | 공개 명세 4.3.10.13의 WCHAR 배열과 HWPX 짝의 본문 | 본말 뒤에 덧말을 괄호로 붙인다. | 원본 URL로 확인한 공개 짝 5/5곳이 일치했다. | 단위 테스트와 실물 짝 검증 통과. ✅ 제안. |
| HWPX 덧말 `dutmal` | 공개 `hwp2hwpx-from_11.hwpx`, `sample-dutmal-basic.hwpx` | HWPX 원시 `mainText`·`subText`, 동일 원본 HWP의 `tdut` | `본말(덧말)`을 본문 위치에 넣는다. | HWP 짝 5/5곳과 일치했다. | 단위 테스트와 실물 짝 검증 통과. ✅ 제안. |

구형 HWP 5.0.0.6–5.0.3.3 표본의 `tcps`에는 글자 배열 뒤의 테두리·크기 필드가 없다. 공개 51개 파일에서 이 형태가 확인됐고, 합성 테스트에서도 경고 없이 글자를 보존한다. 테두리가 없는 최신 레코드의 전용 PUA 숫자 글리프는 HWPX가 보존하므로 그대로 낸다. 테두리 1의 원문자 숫자를 NFKC로 분해하는 분기는 합성 테스트만 있으며 직접 대조되는 공개 짝은 0건이다. 이 세부 표기는 별도 실물 근거가 생길 때까지 미확인이다. 같은 글리프 계열의 미관측 코드포인트로 숫자 복원 범위를 넓히지 않았다.

한컴 미리보기 `PrvText`는 겹침과 덧말을 생략한다. `본말(덧말)`은 dochan의 평탄화 출력 계약이다. HWPX 변경 추적의 삭제 범위에 든 덧말은 합성 테스트에서 최종본 투영으로 제거되지만, 이 경우의 실물 검증은 아직 없다.

다음 명령은 코퍼스 경로를 인자로 받고 문서별 출력 전문을 저장하지 않는다.

```bash
python -m scripts.probe_hwp_compose_pairs corpus/hwp-public/hwp corpus/hwp-public/hwpx corpus/hwp-public/SOURCES.json
python -m scripts.compare_hwp_pairs corpus/press-pairs
python -m scripts.compare_hwp_pairs test_pairs/
```

공개 보도자료 91쌍의 평균 토큰 일치율은 부모 커밋에서 0.9880, 수정 후 0.9881이었다(상승 1쌍, 하락 0쌍). 내부 실물 76쌍은 0.9997에서 0.9998로 올랐고(상승 3쌍, 하락 0쌍), 최소값은 0.9927에서 0.9957로 올랐다. 내부 실물의 파일명과 내용은 기록하지 않았다.

부모 커밋 `245f8f0`과 수정본으로 공개 HWP·HWPX·보도자료 7,533개를 각각 읽어 Markdown SHA-256과 `errors` 목록을 함께 비교했다. 277개는 Markdown만 달라졌고, 오류 목록만 달라진 문서와 두 항목이 함께 달라진 문서는 모두 0개였다. 공개 HWP 디렉터리 267개, HWPX 디렉터리 7개, 보도자료 3개의 Markdown이 달라졌다. 읽기 실패는 양쪽 모두 0개였다. 앞선 커밋 `e1b4232`와 수정본을 비교하면 구형 레이아웃 51개에서 빠지던 글자가 복구되며 `WARN: HWP inline control truncated or invalid`도 51개 모두 사라진다. 다른 47개의 Markdown 차이는 테두리 없는 PUA 보존에서 비롯된다. 문서별 Markdown 전문은 저장하지 않았다.
