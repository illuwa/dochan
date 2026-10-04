# HWPX 문단 안 떠 있는 표의 읽기 순서 조사

공개 HWPX 2,440개를 `python -m scripts.probe_hwpx_float_table --output 결과.json 코퍼스경로...`로 조사했다. `corpus/hwp-public/hwpx/`에서 1,675개, `corpus/press-pairs/`에서 346개, 두 보류 묶음에서 각각 207개와 212개였다. ZIP 또는 섹션 XML이 손상된 4개는 조사에서 빠졌고, 2,436개를 판독했다. 한 원본 `<hp:p>` 안에서 표 앞뒤에 모두 비공백 글자가 있는 위치는 18문서 56곳이었다. `<hp:pos treatAsChar="0">`인 떠 있는 표는 6문서 8곳, `treatAsChar="1"`은 12문서 48곳이었다. 이 수치는 표 셀과 글상자 안의 문단도 각각 원래 문단으로 세되, 해당 문단의 직접 런에 있는 글자만 앞뒤 판정에 사용한 결과다.

떠 있는 표 8곳의 `textWrap`은 `SQUARE` 2곳, `TOP_AND_BOTTOM` 2곳, `IN_FRONT_OF_TEXT` 4곳이었다. `vertRelTo`는 모두 `PARA`, `horzRelTo`는 `COLUMN` 7곳과 `PARA` 1곳이었다. 글자처럼 취급하는 48곳은 `SQUARE` 32곳과 `TOP_AND_BOTTOM` 16곳이며, `vertRelTo=PARA` 48곳, `horzRelTo=PARA` 44곳과 `COLUMN` 4곳이었다. 공개 보도자료 세 묶음에서 떠 있는 표는 0곳이었다. 내부 HWPX 80개를 별도로 조사했을 때 같은 조건의 표는 0곳이었다. 내부 파일명과 본문은 이 기록에 남기지 않았다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
| --- | --- | --- | --- | --- | --- |
| HWPX 읽기 순서, 떠 있는 표 | `corpus/hwp-public/hwpx/3-09월_교육_통합_2023.hwpx` | 같은 이름의 HWP 리더 출력은 표 앞뒤 글자를 한 문단으로 낸다. | 떠 있는 표 뒤에서도 문장이 이어진다. | HWPX는 문단, 표, 문단 순서로 나눈다. | 결함 재현. 수정 미검증 |
| HWPX 읽기 순서, 떠 있는 표 | `corpus/hwp-public/hwpx/3-10월_교육_통합_2022.hwpx` | 같은 이름의 HWP 리더 출력은 표 앞뒤 글자를 한 문단으로 낸다. | 떠 있는 표 뒤에서도 문장이 이어진다. | HWPX는 문단, 표, 문단 순서로 나눈다. | 결함 재현. 수정 미검증 |
| HWPX 읽기 순서, 떠 있는 표 | `corpus/hwp-public/hwpx/36392900_결재문서본문_일일굴착복구공사현황보고.hwpx` | 원시 HWPX의 `treatAsChar=0`, `textWrap=TOP_AND_BOTTOM`; 같은 이름의 HWP 짝은 없다. | 별도 정답 확보가 필요하다. | 표 앞뒤 문단이 분리된다. | 미검증 |
| HWPX 읽기 순서, 떠 있는 표 | `corpus/hwp-public/hwpx/pubinst-mois_2025_행정업무운영_편람(최종).hwpx` 2곳 | 원시 HWPX의 `treatAsChar=0`, `textWrap=IN_FRONT_OF_TEXT`; 같은 이름의 HWP 짝은 없다. | 별도 정답 확보가 필요하다. | 두 위치 모두 표 앞뒤 문단이 분리된다. | 미검증 |
| HWPX 읽기 순서, 떠 있는 표 | `corpus/hwp-public/hwpx/rhwp-2025_행정업무운영_편람_최종.hwpx` 2곳 | 원시 HWPX의 `treatAsChar=0`, `textWrap=IN_FRONT_OF_TEXT`; 같은 이름의 HWP 짝은 없다. | 별도 정답 확보가 필요하다. | 두 위치 모두 표 앞뒤 문단이 분리된다. | 미검증 |
| HWPX 읽기 순서, 떠 있는 표 | `corpus/hwp-public/hwpx/template.hwpx` | 원시 HWPX의 `treatAsChar=0`, `textWrap=TOP_AND_BOTTOM`; 같은 이름의 HWP 짝은 없다. | 별도 정답 확보가 필요하다. | 표 앞뒤 문단이 분리된다. | 미검증 |
| HWPX 읽기 순서, 글자처럼 취급하는 표 | 공개 HWPX 12문서 48곳 | 원시 HWPX의 `<hp:pos treatAsChar="1">` | 현행 인라인 배치를 유지한다. | 파서 변경 없이 현행 배치가 유지된다. | 회귀 대상이며 별도 출력 정답은 미검증 |

미리보기 `Preview/PrvText.txt`에서 떠 있는 표 앞뒤 글자가 바로 이어진 사례는 0/8곳이었다. 미리보기가 해당 페이지를 싣지 않거나 수식과 표를 생략하는 사례가 있어, 이 숫자는 현행 분할이 맞다는 증거가 아니다. 특히 `SQUARE` 2곳은 같은 이름의 HWP 출력으로 결함을 확인했지만, 다른 배치 세부형은 원시 속성 외에 독립 정답이 없다. 공개 보도자료에는 떠 있는 표가 없으므로 같은 번호 PDF로 확인할 표본도 없다.

요청한 20곳 이상의 떠 있는 표 읽기 순서 검증은 현재 공개 코퍼스의 전체 양성 8곳보다 많아 수행할 수 없다. 근거가 부족한 배치형을 임의로 합치지 않기 위해 파서를 변경하지 않았다. 이 조사로 HWPX `읽기 순서`의 해당 세부 사례는 통과했다고 판정할 수 없다. README의 기존 체크는 이 워크트리에서 고치지 않았으며, 오케스트레이터가 이 결함과 기존 검증 범위를 함께 검토해야 한다. 전체 출력은 저장하지 않았고, 조사 JSON에는 건수·속성·짧은 문맥과 미리보기 일치 여부만 남겼다.
