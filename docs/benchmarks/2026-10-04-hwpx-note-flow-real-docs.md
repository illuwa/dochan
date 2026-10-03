# HWPX 각주·미주 참조 문장 흐름 실물 검증

런 안의 `hp:footNote`와 `hp:endNote`는 참조 표지를 그 자리에 두고 정의 요소만 문단 뒤에 배치한다. 표와 수식은 기존 경계를 유지한다. 단위 테스트는 문장 중간 각주, 한 문단의 복수 각주, 각주와 그림·표의 순서, 표 셀·글상자·머리글, 미주, 변경 추적 세 투영을 검증한다.

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| HWPX 각주/미주·읽기 순서 | `corpus/hwp-public/hwpx/05_footnote_endnote.hwpx` | 원본 HWPX의 각주·미주 개체가 한 `hp:p`의 런 안에 있고, 각주 본문은 해당 개체의 `subList`에 있다. | `이 문장에는 각주가 있습니다[^1].`와 `첫 번째 각주[^2]와 두 번째 각주[^3]가 한 문단에 있습니다.`를 각각 한 문단으로 낸다. 각주·미주 7개의 본문과 번호를 보존한다. | 이전에는 표지 뒤의 마침표와 조사마다 문단이 갈라졌다. 수정 후 위 문장이 그대로 이어지고 전체 문단 수는 22→15이다. 정의 7개와 번호·본문이 같다. | 통과 |
| HWPX 각주/미주·읽기 순서 | `corpus/press-pairs/156783576.hwpx`와 같은 번호의 PDF 1쪽 | PDF 렌더에서 `공소청` 바로 뒤에 위첨자 표지가 있고 같은 문장이 `검사급`, `검사로`까지 이어진다. | 두 참조 뒤의 어절이 같은 문단에 남는다. | `공소청[^1] 검사급`, `공소청[^2] 검사로`로 이어진다. 문단 수는 42→40이고 각주 2개가 같다. | 통과 |
| HWPX 각주/미주·읽기 순서 | `corpus/press-pairs/156783577.hwpx`와 같은 번호의 PDF 3쪽 | PDF 렌더의 네 표지는 `사회적 지지율`, `주관적 삶의 만족도`, `분율`, `외로움 경험률` 뒤에 있으며 각 문장은 이어진다. | 네 표지 뒤의 조사와 서술부가 같은 문단에 남는다. | 네 문장이 모두 이어지고 문단 수는 552→548이다. 각주 4개가 같다. | 통과 |
| HWPX 각주/미주·읽기 순서 | `corpus/press-pairs/156784165.hwpx`와 같은 번호의 PDF 7·20쪽 | PDF 렌더에서 그림 설명의 `퍼센타일` 뒤와 20쪽 본문의 `지점` 뒤에 위첨자 표지가 붙고 뒤의 문장이 이어진다. | `퍼센타일[^1] 분포도`, `지점[^2] 활용`을 같은 문단으로 낸다. | 두 문장이 이어지고 문단 수는 5,753→5,751이다. 각주 2개가 같다. | 통과 |
| HWPX 각주/미주·읽기 순서 | `corpus/hwp-public/`, `corpus/press-pairs/`의 HWPX 2,046개 | 수정 전후 Markdown·JSON SHA-256, 각주 종류·번호·본문·순서, 참조 번호 순서, 공백 제외 본문, 표·이미지·머리글·수식·주석 개수, 오류 지문을 비교했다. | 바뀐 문서는 모두 각주·미주가 있고 골격 불변식이 유지된다. | 2,019개를 해석했고 27개는 전후 같은 예외였다. 각주 있는 60개 중 50개에서 Markdown·JSON이 각각 바뀌었다. 50개 모두 각주가 있으며 각주 총 1,192개의 종류·번호·본문·순서와 모든 참조·다른 개체·오류 지문이 동일하다. 문단은 896개 줄었다. 본문 공백만 달라진 7개는 공백 제외 글자가 모두 같다. | 해석 성공 문서 통과. 예외 27개는 미검증 |
| HWPX 각주/미주·읽기 순서 | `corpus/press-pairs/`의 HWP/HWPX 91쌍 | `python -m scripts.compare_hwp_pairs`의 수정 전후 파일별 지표 | 기존 HWP 짝의 일치율이 악화하지 않는다. | 91쌍의 파일별 모든 지표가 동일하며 평균 토큰 일치율은 0.9883이다. 위의 각주 보도자료 3개에는 HWP 파일이 없으므로 이 비교 대상이 아니며 PDF 렌더로 별도 검증했다. | 통과 |
| HWPX 각주/미주·읽기 순서 | 내부 HWP/HWPX 76쌍(이름 비공개) | `python -m scripts.compare_hwp_pairs`의 집계만 비교했다. | 짝의 일치율이 악화하지 않는다. | 75쌍의 파일별 지표는 같고 1쌍의 토큰 일치율만 0.9986→0.9987로 올랐다. 전체 평균은 0.9997→0.9997이고 오류 쌍은 0개다. | 통과 |

공개 PDF는 해당 쪽을 PDFium으로 렌더해 본문 표지와 문장 연결을 직접 확인했다. 렌더 파일은 측정 후 지웠다. 내부 표본의 이름과 내용은 이 문서와 코드에 기록하지 않았다.

## Markdown·JSON 변경 문서 전부

다음 50개 공개 문서는 Markdown과 JSON이 모두 바뀌었다. 표의 각주·미주 개수는 전후에 같으며, 문단 수 변화는 참조 뒤의 분할을 합친 결과다. 파일별 해시와 출력 길이는 `.codex-work/note-before-final.json` 및 `.codex-work/note-after-final.json`에 저장했다. 출력 본문과 이미지 바이트는 저장하지 않았다.

| 공개 표본 파일 | Markdown | JSON | 각주·미주 개수 | 문단 수 |
|---|---|---|---:|---:|
| `corpus/hwp-public/hwpx/05_footnote_endnote.hwpx` | 변경 | 변경 | 7→7 | 22→15 |
| `corpus/hwp-public/hwpx/3-09월_교육_통합_2022.hwpx` | 변경 | 변경 | 46→46 | 1895→1855 |
| `corpus/hwp-public/hwpx/3-09월_교육_통합_2023.hwpx` | 변경 | 변경 | 46→46 | 1577→1536 |
| `corpus/hwp-public/hwpx/3-09월_교육_통합_2024-구분선아래20구분선위20.hwpx` | 변경 | 변경 | 46→46 | 1895→1855 |
| `corpus/hwp-public/hwpx/3-10월_교육_통합_2022.hwpx` | 변경 | 변경 | 46→46 | 1645→1607 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2022.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2024-구분선없음구분선위20미주사이20구분선아래20.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2024-구분선위0미주사이0구분선아래0.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2024-구분선위0미주사이20구분선아래2.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2024-구분선위0미주사이7구분선아래2.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2024-구분선위0미주사이7구분선아래20.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2024-구분선위20미주사이0구분선아래20.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2024-구분선위20미주사이7구분선아래2.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/3-11월_실전_통합_2024-구분선위9미주사이8구분선아래7.hwpx` | 변경 | 변경 | 46→46 | 1840→1799 |
| `corpus/hwp-public/hwpx/SO-SUEOP.hwpx` | 변경 | 변경 | 223→223 | 1363→1163 |
| `corpus/hwp-public/hwpx/[7.24.금 조간] 기대수명 83.7년으로 역대 최고, 우리나라 보건의료 수준 양호.hwpx` | 변경 | 변경 | 2→2 | 1011→1009 |
| `corpus/hwp-public/hwpx/admrul-관세조사-운영-훈령.hwpx` | 변경 | 변경 | 6→6 | 3654→3654 |
| `corpus/hwp-public/hwpx/aift.hwpx` | 변경 | 변경 | 1→1 | 3070→3069 |
| `corpus/hwp-public/hwpx/auto-hwp-footnote-01.hwpx` | 변경 | 변경 | 9→9 | 59→51 |
| `corpus/hwp-public/hwpx/footnote-01.hwpx` | 변경 | 변경 | 9→9 | 59→51 |
| `corpus/hwp-public/hwpx/footnote-tbox-01.hwpx` | 변경 | 변경 | 2→2 | 9→7 |
| `corpus/hwp-public/hwpx/hwp-hwpx-parser-sample_notes.hwpx` | 변경 | 변경 | 5→5 | 210→205 |
| `corpus/hwp-public/hwpx/hwpx2md-footnotes.hwpx` | 변경 | 변경 | 2→2 | 5→4 |
| `corpus/hwp-public/hwpx/hwpx2md-kitchen_sink.hwpx` | 변경 | 변경 | 1→1 | 25→24 |
| `corpus/hwp-public/hwpx/hwpx_complete_guide.hwpx` | 변경 | 변경 | 3→3 | 233→230 |
| `corpus/hwp-public/hwpx/hwpxtpl-Basic_Para_07_Text_With_Footnote.hwpx` | 변경 | 변경 | 1→1 | 3→2 |
| `corpus/hwp-public/hwpx/hwpxtpl-Basic_Para_08_Text_With_Endnote.hwpx` | 변경 | 변경 | 1→1 | 3→2 |
| `corpus/hwp-public/hwpx/issue1853_caption_precedes_body_split.hwpx` | 변경 | 변경 | 6→6 | 744→743 |
| `corpus/hwp-public/hwpx/korea-7.28.화.조간 최근 10년간 고위험음주 남성 전 연령에서 감소, 여성은 30대 이상 모든 연령에서 증가.hwpx` | 변경 | 변경 | 4→4 | 464→461 |
| `corpus/hwp-public/hwpx/korea-mid-240229_&#039;23년_창업기업동향_발표(정책분석평가과).hwpx` | 변경 | 변경 | 1→1 | 1136→1135 |
| `corpus/hwp-public/hwpx/nts-241029 아시아-태평양 18개 국세청장들 한자리에, 서울에서 4일간 조세행정 공조 논의.hwpx` | 변경 | 변경 | 2→2 | 103→101 |
| `corpus/hwp-public/hwpx/pr_2095_issue1937_insert_uniform_browser_export.hwpx` | 변경 | 변경 | 44→44 | 2248→2242 |
| `corpus/hwp-public/hwpx/pr_2095_issue1937_page4_row_insert_browser_export.hwpx` | 변경 | 변경 | 44→44 | 2247→2241 |
| `corpus/hwp-public/hwpx/pr_2095_issue1937_table_mixed_offset_browser_export_fixed.hwpx` | 변경 | 변경 | 44→44 | 2248→2242 |
| `corpus/hwp-public/hwpx/pubinst-kma_20260721_보도자료_전지구_오존층_감시의_눈,_기상청이_한층_더_넓힌다.hwpx` | 변경 | 변경 | 1→1 | 58→57 |
| `corpus/hwp-public/hwpx/pubinst-mohw_[7.24.금_조간]_기대수명_83.7년으로_역대_최고,_우리나라_보건의료_수준_양호.hwpx` | 변경 | 변경 | 2→2 | 1011→1009 |
| `corpus/hwp-public/hwpx/pubinst-mois_2025_행정업무운영_편람(최종).hwpx` | 변경 | 변경 | 1→1 | 6402→6401 |
| `corpus/hwp-public/hwpx/pypandoc-hwpx-test-from-docx.hwpx` | 변경 | 변경 | 1→1 | 103→102 |
| `corpus/hwp-public/hwpx/pypandoc-hwpx-test-from-json.hwpx` | 변경 | 변경 | 1→1 | 103→102 |
| `corpus/hwp-public/hwpx/pypandoc-hwpx-test-from-md.hwpx` | 변경 | 변경 | 1→1 | 64→63 |
| `corpus/hwp-public/hwpx/rhwp-1790387_prep_final_report.hwpx` | 변경 | 변경 | 5→5 | 3821→3816 |
| `corpus/hwp-public/hwpx/rhwp-2025_행정업무운영_편람_최종.hwpx` | 변경 | 변경 | 1→1 | 6402→6401 |
| `corpus/hwp-public/hwpx/rhwp-nested_group_vectors.hwpx` | 변경 | 변경 | 1→1 | 153→152 |
| `corpus/hwp-public/hwpx/rhwp-pr_2095_issue1937_table_mixed_offset_browser_export.hwpx` | 변경 | 변경 | 44→44 | 2248→2242 |
| `corpus/hwp-public/hwpx/template.hwpx` | 변경 | 변경 | 3→3 | 1456→1454 |
| `corpus/hwp-public/hwpx/text_footnote_tail_overpagination.hwpx` | 변경 | 변경 | 89→89 | 4595→4523 |
| `corpus/hwp-public/hwpx/붙임4-1_신청용_연구개발계획서.hwpx` | 변경 | 변경 | 1→1 | 3649→3648 |
| `corpus/press-pairs/156783576.hwpx` | 변경 | 변경 | 2→2 | 42→40 |
| `corpus/press-pairs/156783577.hwpx` | 변경 | 변경 | 4→4 | 552→548 |
| `corpus/press-pairs/156784165.hwpx` | 변경 | 변경 | 2→2 | 5753→5751 |

7개 문서에서 참조 뒤에 이어진 공백 런이 이전의 별도 공백 문단에서 버려지던 것과 달리 보존됐다. 각 경우의 공백 제외 본문 SHA-256은 수정 전후 동일하다. 이는 문단을 합치는 과정에서 생긴 표시 공백 변화이며 각주 본문이나 다른 글자는 바뀌지 않았다.

검증 프로브는 `python -m scripts.probe_hwpx_note_flow --output 결과.json 코퍼스경로 보도자료경로`로 실행한다. 기준 소스에서 만든 결과를 `--reference 기준결과.json`으로 넘기면 두 출력의 해시와 골격 불변식을 비교한다. 확장자가 대문자인 HWPX 한 파일은 공개 코퍼스에 포함해 HWPX 파서와 출력 함수로 직접 측정했다. 기준 버전은 git archive 소스 스냅숏 한 개로 실행했다.

README의 HWPX `각주/미주`와 `읽기 순서`는 기존 ✅ 유지가 타당하다. 미해석 문서 27개에는 이 결론을 적용하지 않는다.
