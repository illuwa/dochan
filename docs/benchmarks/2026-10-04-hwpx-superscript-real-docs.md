# HWPX 위·아래 첨자 (`<hh:supscript/>`·`<hh:subscript/>`)

## 판정

HWPX 리더가 charPr 의 위 첨자(`<hh:supscript/>`)·아래 첨자(`<hh:subscript/>`)를 읽지 않아, 같은 문서의 HWP 출력은 `파악됐다<sup>*</sup>` 인데 HWPX 는 `파악됐다*` 였다.
이제 두 요소를 런 서식으로 읽는다(HWP 글자 모양 속성 비트 15·16 과 같은 뜻, 모델 필드 `superscript`·`subscript` 와 Markdown `<sup>`·`<sub>` 계약은 기존 그대로).

| 칸 | 표본 | 정답 근거 | 결과 |
| --- | --- | --- | --- |
| HWPX 글자 서식(위·아래 첨자) | 공개 정책브리핑 보도자료 HWP·HWPX 짝 91쌍(`corpus/press-pairs`, 공공누리 제1유형) | 같은 문서 HWP 출력의 `<sup>`·`<sub>` 개수 | 개수가 같은 짝 45 → 90/91(남은 1쌍은 배포용 암호화 HWPX 156783589) |
| 회귀 | 공개 HWPX 2,045개(`corpus/hwp-public` + 보도자료) | 수정 전 Markdown SHA-256 | 바뀐 702개는 모두 header 에 `supscript`·`subscript` 가 있는 문서다(그런 문서 794개). 없는 문서의 변경 0 |

보도자료 156784175 의 `파악됐다*`(charPr 39, 위 첨자)는 같은 보도자료 HWP 출력과 같은 `<sup>*</sup>` 가 된다. 단위 테스트 `tests/test_hwpx_superscript.py`.
