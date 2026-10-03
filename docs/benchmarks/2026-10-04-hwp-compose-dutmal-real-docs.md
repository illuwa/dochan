# HWP 글자 겹침·덧말과 HWPX 덧말 실물 검증

한컴 「한글문서파일형식 5.0 revision 1.3」 4.3.10.12와 4.3.10.13의 컨트롤 레이아웃을 기준으로 구현했다. 동일 문서의 HWPX `composeText`, `mainText`, `subText`를 본문 문자열의 정답지로 삼았다. 한컴 미리보기 `PrvText`는 겹침 글자와 덧말을 생략하므로, 덧말을 `본말(덧말)`로 평탄화하는 방식은 dochan의 출력 계약이다. 덧말이 비면 본말만 낸다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| HWP 글자 겹침 `tcps` | `corpus/press-pairs/156783561.hwp`와 `.hwpx`, `corpus/hwp-public/{hwp,hwpx}/sample-compose-basic`, `sample-compose-all-shapes` | 공개 명세 4.3.10.12의 가변 길이 구조, HWPX `composeText`, 같은 문서 PDF의 사각형 안 숫자 | 보도자료의 해당 제목이 두 형식 모두 `### 1 최신 주간농사정보 알려줘`이고, 공개 샘플에서 테두리 글리프를 제외한 본문이 같다. | 보도자료 제목이 정확히 일치했고 두 샘플의 전체 평문도 일치했다. 같은 이름의 공개 짝 전체에서 겹침 문자열 138곳 중 117곳이 일치했다. 15곳은 짝 HWP에 컨트롤이 없었고 6곳은 HWPX 변환마다 전용 글리프를 숫자로 바꾸는 방식이 달랐다. | 대표 실물 통과. 전체 짝의 문자열 동등성은 미완이며 확장 판정은 보류한다. |
| HWP 덧말 `tdut` | `corpus/hwp-public/{hwp,hwpx}/sample-dutmal-basic` | 공개 명세 4.3.10.13의 본말·덧말 WCHAR 배열과 HWPX 동명 짝 출력 | 두 곳 모두 `본말(덧말)` 형식이며 짝 출력과 같다. | 컨트롤 2곳 중 2곳이 일치하고 전체 평문도 일치했다. 다른 공개 짝 `hwp2hwpx-from_11`에는 HWP `tdut` 컨트롤이 없어 HWPX의 3곳과 직접 대조할 수 없었다. | HWP 컨트롤이 있는 실물 표본 통과. |
| HWPX 덧말 `dutmal` | `corpus/hwp-public/hwpx/sample-dutmal-basic.hwpx`, `hwp2hwpx-from_11.hwpx` | HWPX 원시 `mainText`·`subText`와 동일 문서 HWP의 `tdut` 2곳 | 본말 뒤에 덧말을 괄호로 붙여 본문 자리에 넣는다. | 2곳에서 HWP 짝과 일치했다. 나머지 HWPX 3곳도 본말·덧말을 출력하지만 짝 HWP에는 `tdut`가 없다. | 구현과 HWP 짝 2곳 검증 통과. |

`sample-compose-all-shapes`의 28개 글자 겹침은 두 형식에서 모두 일치했다. 반면 다른 공개 짝 두 곳에서는 HWPX가 겹침 15곳을 가지고 있어도 HWP에 해당 컨트롤이 없고, 한 곳에서는 HWPX 덧말 3곳에 대응하는 HWP 컨트롤이 없다. 이러한 불일치는 없는 원시 데이터를 만들어 채우지 않았다. `mel-001`과 `table-vpos-01`의 전용 글리프 6곳은 다른 공개 짝의 숫자 변환 규칙과 서로 달라 일치시키지 않았다. 공개 짝 하나는 손상된 ZIP이라 제외했다.

코퍼스와 짝 비교는 다음 명령으로 재현한다. 경로는 인자로 전달하고 문서별 출력 전문은 저장하지 않는다.

```bash
python -m scripts.probe_hwp_compose_pairs corpus/hwp-public/hwp corpus/hwp-public/hwpx
python -m scripts.compare_hwp_pairs corpus/press-pairs
python -m scripts.compare_hwp_pairs test_pairs/
```

보도자료 91쌍의 평균 토큰 일치율은 수정 전 0.9880, 수정 후 0.9881이었다. 내부 실물 76쌍의 평균 토큰 일치율은 수정 전 0.9997, 수정 후 0.9998이었고 최소 일치율은 0.9927에서 0.9957로 올랐다. 내부 실물의 파일명과 내용은 기록하지 않았다.

공개 코퍼스와 보도자료의 7,533개 파일을 모두 같은 입력으로 두 번 읽어 Markdown SHA-256을 비교했다. 226개 파일의 해시가 바뀌었고, 모두 `tcps`, `tdut`, `dutmal` 가운데 하나를 실제로 담고 있었다. HWP 글자 겹침 210개, HWP 덧말 8개, HWPX 덧말 8개로 분류됐다. 확장자가 `.hwpx`인 공개 파일 3개는 실제 매직 바이트가 OLE/HWP였으므로 HWP 글자 겹침에 분류했다. 출력 전문은 저장하지 않고 해시·문자 수·오류 목록만 저장했으며, 읽기 실패 수는 전후 모두 0개였다.
