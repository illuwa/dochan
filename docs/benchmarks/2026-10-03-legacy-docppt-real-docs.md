# DOC·PPT 세부 기능의 공개 실물 검증

2026년 10월 3일 `legacy-docppt` 초기 작업에서 확인한 결과이다. 리뷰 뒤의 최종 판정과 공용 작성기 검증은 [리뷰 반영 기록](2026-10-02-legacy-docppt-fix-real-docs.md)에 있으며, 아래 짝 비교 근거도 그 결과로 정정했다. 초기 작업의 단계별 회귀 수치는 당시 비교 기준 `f7ceaa1`에 대한 기록이다. README와 CHANGELOG는 수정하지 않았다. 공개 코퍼스 원본을 읽기 전용으로 사용했고 테스트에는 직접 조립한 바이트만 넣었다. POI·LibreOffice 구현 코드는 사용하지 않았다. 이번 실행에는 Microsoft 명세의 로컬 사본이 없었으므로 기존 파서 계약과 공개 문서의 원시 레코드로 확인할 수 있는 범위만 구현했다.

## 칸별 판정

| 칸 | 표본 파일 | 정답 근거 | 기대 | 실제 | 판정 |
|---|---|---|---|---|---|
| PPT 마스터 기본 서식 | POI `slide_master.ppt` | 4003 레코드의 마스터별 type0/1/5/6 CF 마스크와 값이다. 첫 마스터의 type0은 밑줄·40pt이고 둘째 마스터의 type0은 기울임·48pt이다. 둘째 마스터 type5는 mask=0x60003, 굵게·기울임 해제·20pt이고 type6은 mask=0x70007, 굵게·밑줄·32pt이다. | 각 슬라이드가 자신이 참조한 마스터·텍스트 종류·문단 수준의 속성을 사용해야 한다. | 제목 `Slide Masters`는 밑줄·40pt, `Slide Masters (cont’d)`는 기울임·48pt, TitleMaster 제목은 굵게·밑줄·32pt, 부제는 굵게·20pt로 복원했다. | 원시 값과 일치했다. |
| PPT 글꼴 크기·위첨자 | POI `WithMaster.ppt` | type0 기본 크기 44pt, type1 기본 크기 32pt 및 `nd` 런의 baseline 속성이다. PPTX의 slideLayout1.xml 부제 defRPr에는 b=1, i=1이 있다. | 제목과 부제의 기본 크기를 상속하고 `2nd`의 `nd`에 위첨자를 적용해야 한다. | 제목 10→44pt, 부제 10→32pt, `nd` 위첨자 False→True이다. 기존 굵게·기울임은 유지했다. | 원시 값과 일치했다. |
| PPT 기본 CF 우선순위 | POI `alterman_security.ppt` | DocumentContainer→Environment→4004의 mask=0x400082에는 기울임이 있지만 Environment type4와 마스터 type0/1은 기울임 해제를 명시한다. | 최하위 CF 기본값이 마스터의 명시적 해제를 덮지 않아야 한다. | 문서 기본 CF, 같은 텍스트 유형의 Environment 기본, 마스터 기본, 특수 텍스트 유형, 개별 런 순으로 처리했다. 리뷰에서 Environment Other(type4)를 다른 유형으로 승격하던 처리를 제거했다. | 실물 바이트 관찰과 합성 우선순위 테스트를 통과했다. |
| PPT CF9 확장 길이 | POI `45776.ppt`, `56260.ppt`, `bug55732.ppt`, `bug58718_008495.ppt`, LO `tdf169705.ppt` | 4012 확장 레코드의 CF9 mask=0x100000 다음에 4바이트 pp10ext가 있고 이어서 SI mask와 다음 문단이 나온다. | 확장 필드를 건너뛴 뒤 뒤쪽 문단 서식을 계속 읽어야 한다. | 다섯 파일의 `unsupported auto-number CF/SI extension` 경고가 사라졌고 기존 출력 내용·서식은 유지했다. | 관찰한 CF9 범위는 통과했다. |
| PPT SI 확장 길이 | LO `tdf77747.ppt` | 4012 레코드의 SI mask=0x40 뒤에는 2바이트 bidi 값이 있고 다음 PF9가 이어진다. | bidi를 소비한 뒤 다음 문단을 읽어야 한다. | 경고가 사라졌고 출력 내용·서식은 유지했다. | 관찰한 SI 범위는 통과했다. |
| PPT 미확인 확장 | 손상 POI `2cade576206d5bf9a89479446973deeda5a9b549.ppt` 등 | 기존 일반 CF/PF 허용 비트와 알 수 없는 필드의 길이는 이번 정상 실물에서 추가로 입증하지 못했다. | 모르는 필드 길이를 추측해 뒤쪽 런을 잘못 해석하지 않아야 한다. | 일반 CF의 예약 비트 거절과 완성된 앞쪽 런 보존을 유지했다. 손상 파일의 PF 경고 하나는 남는다. | 항목 2 전체는 ⬜ 유지이다. |
| DOC 연결 글상자 체인 | 공개 DOC 492개, 조사 대조군 POI `Bug41898.doc` | FTXBXS 43문서의 활성 비종결 레코드 572개에서 cTxbx=1, itxbxsDest=0xffffffff를 관찰했다. | 다중 연결 체인을 찾아 DOCX 짝 또는 원시 도형 순서와 대조해야 한다. | 실물 체인은 0개였다. 동일 이야기 textId를 공유하는 도형의 기존 중복 방지는 합성 본문·머리말 테스트 두 개로 확인했다. | 실물 없음·⬜ 유지이다. 이야기 사이 목적지 연결은 새로 구현하지 않았다. |
| DOC 직접 WMF | LO `sw/qa/extras/layout/data/forcepoint92.doc` | FIB A5DC/nFib101/flags8, BTE 184/188, uint16 FKP PN, FC894의 그림 문자, CHPX pic_location=6576, PICF cbHeader58/mm8/lcb9498을 따라갔다. WMF mtSize=4686 WORD와 전체 레코드·EOF를 검사했다. | CP126 위치의 9,372바이트 WMF를 복원해야 한다. | 그림 0→1개이다. SHA-256 `d5eab2e08b5044de3e9be5bf22ed02ebdc5c50acd0af9868b4ee18552156ddb3`가 원시 바이트와 일치한다. | 직접 WMF 범위는 1/1 통과이다. |
| DOC 구형 그림의 남은 범위 | POI `Bug50955.doc`, LO `ofz21385-1.doc`, `forcepoint-44.doc` | 유효 원시 WMF 후보가 있지만 복합 저장이거나 정상 본문 앵커를 입증하지 못한 손상 파일이다. | CP와 그림 참조를 확인한 경우에만 원래 위치에 놓아야 한다. | 서명 검색으로 그림을 임의 배치하지 않았다. 직접 DIB의 정상 참조 표본도 찾지 못했다. | 복합 저장·직접 DIB는 미구현이므로 항목 4 전체는 ⬜ 유지이다. |
| DOC 위쪽 캡션 | 공개 DOC 431개, LO `TableWithAboveCaptions.docx` | DOC Caption/SEQ 후보 9파일 15문단의 다음 문단과 객체를 조사했다. DOCX 표본은 TOP `Table 1`이나 DOC 짝이 없다. | 표·그림 바로 위의 DOC 캡션 실물을 확인해야 한다. | DOC 결합 7개는 모두 BOTTOM이었다. 위쪽 DOC 표본과 비교 가능한 짝은 없었다. | 실물 없음·⬜ 유지이다. |
| DOC XOR 난독화 | POI·LO·Tika 공개 파일 7,232개 | 확장자 무관 파일 magic, OLE 최상위·중첩 WordDocument, 원시 FIB에서 오프셋 0x0A 플래그를 읽었다. | fObfuscated가 켜진 실제 파일을 찾아야 한다. | 유효 FIB 488개 중 0개였다. 구형 FIB 46개의 fEncrypted도 모두 꺼졌다. 손상 OLE 14개는 판정 불가이다. | 확인 가능한 범위에서 실물 없음·⬜ 유지이다. |

## PPT/PPTX 짝 비교의 정정

기존 Dochan PPTX 출력의 `530/550` 런(96.36%) 및 `17,074/17,363` 문자 수치는 신규 굵게·기울임 상속의 정답 증거로 폐기한다. 비교 대상에서 그 속성이 달라진 문자가 없으며 정답 리더의 상속 누락도 있었기 때문이다. 아래 수치는 독립 XML 해석과 문자별 재측정으로 정정한 결과이다. 원래 기준은 `f7ceaa1`, 리뷰 직전은 `253d3c6`, 최종은 이번 리뷰 반영본이다.

## 문자 기준의 변화

다음 수치는 공백을 포함한 전체 문단에서 각 문자의 속성을 비교한 결과이다. 런 경계의 추가·병합은 변화로 세지 않는다.

| 속성 | 원래 기준 → 리뷰 직전 | 원래 기준 → 최종 |
|---|---:|---:|
| 글꼴 크기 | 78,984자, 110파일 | 78,764자, 108파일 |
| 굵게 False → True | 17,315자 | 17,315자 |
| 굵게 True → False | 54자 | 54자 |
| 기울임 False → True | 1,015자 | 1,015자 |
| 밑줄 False → True | 44자 | 44자 |
| 위첨자 False → True | 147자 | 147자 |
| 아래첨자 False → True | 105자 | 105자 |
| 서식 속성 하나 이상 변경된 파일 | 113개 | 111개 |

리뷰 직전과 최종을 직접 비교하면 글꼴 크기만 2,469자, 7파일에서 달라졌다. 합성 라벨의 본문 상속 제거와 Environment Other 유형 상속 범위 축소에 따른 변화이다. 나머지 다섯 속성과 본문은 동일했다. 원래 기준과 최종의 크기 차이가 220자 줄어든 것은 두 방향 변경을 상쇄한 단순 합이 아니라, 각 최종 문자값을 원래 기준과 다시 대조한 결과이다.

## 독립 PPTX XML 정답

공개 같은 이름 PPT/PPTX 짝 9개 중 비공백 문자를 대응시킬 수 있는 짝은 5개였다. 슬라이드 번호와 앞뒤 공백을 제거한 문단 본문 전체가 같을 때 대응시키고, 반복 문단은 순서대로 한 번씩 사용했다. XML 정답은 `p:sp`의 기본·마스터·레이아웃·문단·런 속성을 직접 해석한다. 표 셀, 노트, 테마의 암시적 속성은 이 정답 분모에 포함하지 않는다. 암호화 PPTX 한 개는 ZIP XML을 직접 읽을 수 없었다. 이 분모는 기존 Dochan PPTX 리더를 정답으로 삼은 `530/550` 런 비교와 다르다.

| 속성 | 원래 기준 | 리뷰 직전 | 최종 |
|---|---:|---:|---:|
| 굵게 | 12,479/12,479 | 12,479/12,479 | 12,479/12,479 |
| 기울임 | 12,479/12,479 | 12,479/12,479 | 12,479/12,479 |
| 밑줄 | 12,479/12,479 | 12,479/12,479 | 12,479/12,479 |
| 글꼴 크기 | 8,602/12,207 | 10,982/12,207 | 10,982/12,207 |
| 위첨자 | 12,477/12,479 | 12,479/12,479 | 12,479/12,479 |
| 아래첨자 | 12,479/12,479 | 12,479/12,479 | 12,479/12,479 |

글꼴 크기 일치율은 70.47%에서 89.96%로 개선되었다. 굵게·기울임·밑줄은 위 짝의 전체 문단에서도 변경 문자가 0개였다. 따라서 높은 일치율은 신규 상속 변경이 옳다는 외부 정답 증거가 아니며 이 세 칸은 미검증으로 남긴다. 그 외 공개 파일의 원시 마스터 레코드와 일치한다는 증거는 외부 짝 검증과 구별해서 기록한다. 새 아래첨자 변경도 짝 정답의 일치율 상승으로 입증하지 못했다.

원 리뷰의 독립 해석기를 그대로 재실행하면 크기 `8,602 → 10,969 / 12,194`가 정확히 재현된다. 원 해석기는 문단 `a:pPr/a:defRPr` 계층을 생략했다. 이번 해석기는 이 계층을 런 직접 속성보다 낮은 우선순위에 반영했다. `customGeo.pptx`의 6번 슬라이드 `Strands` 7자와 `Topics` 6자의 문단 기본 `sz="1800"`이 추가로 확인되므로, 크기 분모와 최종 일치 문자가 각각 13자 증가했다. 나머지 속성 지표는 같았다.

## 공개 코퍼스 전체 회귀 비교

HEAD 소스를 별도 작업 디렉터리에 보존하고 같은 공개 목록으로 각각 변환했다. 파서 변경을 분리해 ① PPT 상속만, ② PPT 상속과 확장, ③ DOC 그림만, ④ 최종 통합본을 검사했다. 항목 3·5·6은 런타임을 바꾸지 않았으므로 해당 항목 자체의 HEAD 대비 차이는 없다. 각 실행은 DOC 492개와 PPT 221개, 총 713개를 포함한다. 파일별 40초 제한을 적용했고 프로브 예외와 시간초과는 없었다.

| 실행 | DOC/PPT 문서 수 | 기존 실패→현재 실패 | 새 실패 | Markdown 변경 | 본문 단어 손실 후보 |
|---|---|---|---:|---:|---:|
| PPT 마스터만 | 492/221 | 68/28→68/28 | 0 | PPT 29개 | 0 |
| PPT 마스터+확장 | 492/221 | 68/28→68/28 | 0 | PPT 29개 | 0 |
| DOC 그림만 | 492/221 | 68/28→68/28 | 0 | DOC 1개 | 0 |
| 최종 통합 | 492/221 | 68/28→68/28 | 0 | DOC 1개, PPT 29개 | 0 |

마스터 단계에서는 PPT 113개의 런 서식 해시가 달라졌다. 이 해시는 텍스트, 굵게, 기울임, 밑줄, 크기, 위첨자, 아래첨자를 포함한다. 본문 텍스트와 그림 해시는 그대로이다. 손상된 마스터를 새로 읽으면서 `crash-1.ppt`에 수준 수 상한 경고, `hang-18.ppt`와 `cf5f6fde99a8b3ea5a4946c258b7abad6f30b0c5.ppt`에 탭 수 상한 경고가 추가됐다. 문서 단위 실패는 추가되지 않았다.

확장 단계만 비교하면 위 표에 적은 여섯 파일의 경고만 사라진다. 해당 실물은 뒤쪽 번호 정보가 현재 출력에 차이를 만들지 않았으며, 뒤쪽 번호가 실제로 복원되는 경우는 합성 테스트로 별도 확인했다. 실물에서 경고가 없어졌다는 결과를 새 시각적 번호 출력의 실물 증거로 과장하지 않는다. 일반 CF/PF 예약 비트와 관찰되지 않은 TextSpecialInfo 속성은 계속 안전하게 중단한다.

DOC 그림 단계에서 `forcepoint92.doc`는 확인한 WMF와 자산 참조가 추가됐고 `ofz21385-1.doc`는 잘못된 PICF 참조 경고만 추가됐다. 구형 그림 후보가 있다는 이유만으로 손상 문서에 이미지를 붙이지 않았다.

## 구현 경계와 재현

TextMasterStyleAtom은 최대 5수준을 읽고 기본 종류와 5~8 특수 종류의 수준 인덱스를 구별한다. 해당 속성이 마스크에 없으면 상속하고 명시적 0이면 해제한다. CF baseline은 부호 있는 16비트 값으로 읽어 기존 TextRun의 superscript/subscript에 반영한다. 마스터 객체 표시 플래그는 글자 서식 상속을 끄는 조건으로 사용하지 않는다. Environment의 일반 기본값과 마스터의 Other 텍스트 스타일을 구분해 서로 다른 유형으로 서식이 번지지 않도록 했다.

일반 CF에서 예약된 0x100000 비트를 CF9의 pp10ext와 혼동하지 않는다. CF9의 4바이트와 SI bidi의 2바이트는 서로 다른 레코드 문맥에서만 읽는다. 절단 입력은 완성된 앞쪽 값을 남기고 doc.errors 경고로 처리한다. 새로운 글꼴 렌더링 엔진이나 출력 형식을 추가하지 않았다.

DOC 그림은 단일 바이트의 연속 본문을 쓰는 비복합 Word 6/95에 한정한다. 리뷰에서 텍스트 품질 선택과 독립적으로 FIB→BTE→CHPX→PICF를 따라가도록 수정했으며 기존 문단·표 셀 안에서 그림 문자를 Image로 치환한다. WMF 바이트·개수 상한 외에 서로 다른 FKP 페이지, CHPX 100,000개, 검사 문자 1,000,000개, 재귀 32단계 제한을 적용한다. 이 수치는 악성 입력의 자원 제한이며 파일 형식을 추론하기 위한 임의 조건이 아니다.

실물 프로브는 다음과 같이 실행한다. 코퍼스 경로는 인자로 전달하며 파일을 복사하지 않는다.

```bash
/usr/bin/python3 -m scripts.probe_legacy_ppt_styles CORPUS --output .codex-work/ppt-pairs.json --record-sample CORPUS/poi-src/test-data/slideshow/slide_master.ppt
/usr/bin/python3 -m scripts.probe_doc_legacy_chains CORPUS/poi-src/test-data CORPUS/lo-src CORPUS/tika-test-docs > .codex-work/doc-chain-probe.json
/usr/bin/python3 -m scripts.probe_doc_legacy_images CORPUS/poi-src/test-data CORPUS/lo-src CORPUS/tika-test-docs
/usr/bin/python3 -m scripts.probe_doc_legacy_evidence CORPUS/poi-src CORPUS/lo-src CORPUS/tika-test-docs --captions --output .codex-work/doc-evidence.json
/usr/bin/python3 scripts/compare_office_fix2.py --source-root SOURCE --lists .codex-work/public-docppt.txt --output OUTPUT --baseline .codex-work/baseline-v2/results.json
/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider --basetemp=.codex-work/pytest-tmp
```

초기 작업에서 기존 테스트 단언, 공유 모델·출력·reader.py·conversion.py·batch.py·cli.py는 수정하지 않았다. 리뷰 반영에서는 공용 Markdown 작성기의 강조 줄바꿈과 표 셀 그림 누락을 추가로 수정했고, 그 영향은 별도 리뷰 기록에서 검증했다. 새 런타임 의존성은 없다. `scripts/compare_office_fix2.py`에는 크기·위첨자처럼 Markdown만으로 관찰할 수 없는 모델 변화, 그림 바이트, 경고 변화까지 비교하도록 추가했다.

연결 체인은 공식 FTXBXS 설명과 활성 실물, 구형 그림은 복합 piece table·직접 DIB 정상 참조, 위쪽 캡션과 XOR는 해당 DOC 실물이 남은 검증 자원이다. 이번 결과로 이 미검증 칸에 ✅를 제안하지 않는다.

## 변경된 공개 문서 전체 목록

총 118개 파일의 내용·런 서식·그림·경고 중 하나 이상이 달라졌다. 아래 경로는 지정 공개 corpus 루트의 상대 경로이다. 나머지 595개는 측정한 출력과 경고가 같았다. 모든 713개의 본문 텍스트 해시는 HEAD와 같았다.

| 공개 파일 | 바뀐 항목 | 사유 |
|---|---|---|
| `lo-src/sd/qa/unit/data/fdo64586.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/hanging-indent.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/indent_multiple_spacings.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/novell6655408.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/pass/crash-1.ppt` | 경고 | 손상 마스터의 수준·탭 수 상한 경고를 추가했다. |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-18.ppt` | 런 서식, 경고 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. 손상 마스터의 수준·탭 수 상한 경고를 추가했다. |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-22.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/pass/hang-8.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf116899.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf119629.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf126761.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf136911.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf143315-WordartWithoutBullet.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf166030.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf168736-1.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf168736-2.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf168786.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf169705.ppt` | Markdown, 런 서식, 경고 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. 확장 CF9 또는 SI bidi를 소비해 기존 경고를 없앴다. |
| `lo-src/sd/qa/unit/data/ppt/tdf49856.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/ppt/tdf77747.ppt` | 경고 | 확장 CF9 또는 SI bidi를 소비해 기존 경고를 없앴다. |
| `lo-src/sd/qa/unit/data/ppt/tdf79082.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/pptx/tdf108926.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sd/qa/unit/data/tdf124708.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `lo-src/sw/qa/core/data/ww6/pass/ofz21385-1.doc` | 경고 | 잘못된 PICF 참조를 경고했다. 본문과 자산은 그대로이다. |
| `lo-src/sw/qa/extras/layout/data/forcepoint92.doc` | Markdown, 그림 | 본문·문단을 보존하고 검증된 WMF 그림과 자산 한 개를 복원했다. |
| `poi-src/test-data/slideshow/119877_all type background_save_by_AOO.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/2100a8d44da546f97ab7795c500a58bed6cb655d.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/23884_defense_FINAL_OOimport_edit.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/2cade576206d5bf9a89479446973deeda5a9b549.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/37625.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/38256.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/41246-1.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/41246-2.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/42474-2.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/42485.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/42486.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/42520.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/43781.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/44770.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/45537_Footer.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/45537_Header.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/45543.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/45776.ppt` | Markdown, 런 서식, 경고 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. 확장 CF9 또는 SI bidi를 소비해 기존 경고를 없앴다. |
| `poi-src/test-data/slideshow/47261.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/49648.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/51731.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/52244.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/52599.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/53446.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/54111.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/54332a.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/54332b.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/54722.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/54880_chinese.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/56260.ppt` | 런 서식, 경고 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. 확장 CF9 또는 SI bidi를 소비해 기존 경고를 없앴다. |
| `poi-src/test-data/slideshow/57272_corrupted_usereditatom.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/60f557c0a46bcb0068b1c3e15589dac383307bc8.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/62d2ecd89aeb715b07072d4f8a8734f4dbeb5c10.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/6afff8111a22b118d1ed4eba5007c153de0b0ad7.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/7ffe3cabb976ebc593dfe2f9461bdeac980a626c.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/ParagraphStylesShorterThanCharStyles.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/PictureTypeZero.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/SampleShow.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/SimpleMacro.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/Single_Coloured_Page.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/Single_Coloured_Page_With_Fonts_and_Alignments.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/WithComments.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/WithLinks.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/WithMaster.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/alterman_security.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/badzip.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/basic_test_ppt_file.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/br.com.diversas.palestras_Nelson_20-_20Temas_20Diversos_20XXXVI_pmrg_462538ba7a204-programa_alianca_12-04-2007.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/br.com.tvcamboriu.www_pps_Pensar_5b1_5d.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug-41015.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug45088.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug45124.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug47261.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug52297.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug55732.ppt` | 경고 | 확장 CF9 또는 SI bidi를 소비해 기존 경고를 없앴다. |
| `poi-src/test-data/slideshow/bug55902-mixedFontChineseCharacters.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug57820-initTableNullRefrenceException.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug58144-headers-footers-2003.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug58144-headers-footers-2007.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug58159_headers-and-footers.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug58516.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug58718_008495.ppt` | Markdown, 런 서식, 경고 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. 확장 CF9 또는 SI bidi를 소비해 기존 경고를 없앴다. |
| `poi-src/test-data/slideshow/bug58718_008524.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug58718_008558.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug58733_671884.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug60345_Jankovic_final_Retreat_2002.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug60345_paperfigures.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug60345_suba.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug60993.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug61881.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug62092.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bug69697.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/bullets.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/cf5f6fde99a8b3ea5a4946c258b7abad6f30b0c5.ppt` | 런 서식, 경고 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. 손상 마스터의 수준·탭 수 상한 경고를 추가했다. |
| `poi-src/test-data/slideshow/clusterfuzz-testcase-minimized-POIHSLFFuzzer-6028723156746240.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/customGeo.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/empty_textbox.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/headers_footers_2007.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/iisd_report.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/incorrect_slide_order.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/master_text.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/missing-moveto.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/missing_core_records.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/next_test_ppt_file.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/npe.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/numbers.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/ole2-embedding-2003.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/ppt_with_embeded.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/ppt_with_png.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/slide_master.ppt` | Markdown, 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/testPPT_oleWorkbook.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/text-margins.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |
| `poi-src/test-data/slideshow/text_shapes.ppt` | 런 서식 | 마스터 기본값·명시 CF 마스크·baseline을 런에 반영했다. |

## 초기 작업 테스트 결과

전체 테스트는 **3,302 passed, 24 skipped, 14 xfailed**였다. 전체 Ruff 검사와 `git diff --check`도 통과했다. 건너뛴24개와 기존 예상 실패14개는 성공으로 세지 않았다.

최종 전체 비교는 `.codex-work/baseline-v2/results.json`과 `.codex-work/final2/results.json`, 항목별 비교는 `ppt-master-final`, `ppt-extension-final`, `doc-image-final3` 디렉터리에 보존했다. 검사용 원본 문서는 저장소에 넣지 않았다.
