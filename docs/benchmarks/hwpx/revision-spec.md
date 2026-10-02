# A03 HWPX 변경 추적: 실물 XML 조사와 최소 gold

조사일: 2026-09-19. **삽입·삭제 실물 확보, 문단 서식 변경 참조 확보.**
아래 gold는 ZIP 안의 XML을 직접 읽어 도출했다. dochan 파서·변환 출력,
미리보기 텍스트, 화면 렌더링은 정답 생성에 사용하지 않았다.
관찰 사실, 공식 공개 모델의 정의, 아직 확인하지 못한 의미를 구분한다.

## 1. 표본 식별·공개 출처·라이선스

로컬 경로는 저장소 루트 기준이다. 공개 URL은 커밋에 고정했다.
두 표본 모두 조사일에 공개 파일을 메모리로 받아 로컬 바이트와 일치함을 확인했다.

| ID | 로컬 경로 | 크기(bytes) | SHA-256 |
| --- | --- | ---: | --- |
| R1 | `corpus/hwp-public/hwpx/hwpxlib-ChangeTrack.hwpx` | 13027 | `05e6384795611406b29302cf62326b6d1f0a9399d2fbc201fcbe459aa730e356` |
| R2 | `corpus/hwp-public/hwpx/admrul-관세조사-운영-훈령.hwpx` | 502198 | `27c559e41150a166213dffb33d2e496e6cc4d50d18a6fc159c4fe77eacf5dff8` |

- R1: neolord0/hwpxlib의 [공개 ChangeTrack 표본](https://raw.githubusercontent.com/neolord0/hwpxlib/f9fd2255ac0fc57414e0b657d115e7de51d31c65/testFile/reader_writer/ChangeTrack.hwpx).
  저장소 [Apache-2.0 선언](https://github.com/neolord0/hwpxlib/blob/f9fd2255ac0fc57414e0b657d115e7de51d31c65/license.txt)을 직접 확인했다.
  라이선스 파일 SHA-256: `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`.
  직접 확인 범위는 해당 커밋의 저장소 라이선스 선언이며, 개별 표본의
  모든 권리나 제3자 자료의 권리까지 보증하지 않는다.
  corpus의 `reader_writer__ChangeTrack.hwpx`는 같은 SHA-256의 사본이므로 독립 표본으로 세지 않는다.
- R2: genonai/admrul_data의 [공개 훈령 파일](https://raw.githubusercontent.com/genonai/admrul_data/bed62240952688bb62e4822f83dbf3dd98d82f84/%ED%96%89%EC%A0%95%EA%B7%9C%EC%B9%99/%EA%B4%80%EC%84%B8%EC%A1%B0%EC%82%AC%20%EC%9A%B4%EC%98%81%EC%97%90%20%EA%B4%80%ED%95%9C%20%ED%9B%88%EB%A0%B9/%EC%9B%90%EB%AC%B8/3.%20%EA%B4%80%EC%84%B8%EC%A1%B0%EC%82%AC%20%EC%9A%B4%EC%98%81%EC%97%90%20%EA%B4%80%ED%95%9C%20%ED%9B%88%EB%A0%B9_%EC%A0%84%EB%AC%B8.hwpx).
  `corpus/hwp-public/SOURCES.json`은 `Public Domain (KR 저작권법 §7(2) 비보호저작물 - 국가·지자체 고시·공고·훈령)`으로 분류하며
  [저작권법 제7조](https://www.law.go.kr/법령/저작권법/제7조)를 근거로 연결한다.
  이는 **수집 인덱스의 권리 분류**이며 이번 조사에서 원 게시기관·개별 파일의 권리까지 재확정하지 않았다.
  R2는 본문을 인용하지 않고 구조 메타데이터만 사용한다.

R1의 작성자 이름·수정 시각 원값과 R2 본문·작성자 정보는 싣지 않는다.
R1 gold에는 개인을 식별하지 않는 짧은 테스트 문구만 사용한다.

| 표본 | ZIP 내부 파트 | 압축 해제한 원본 바이트의 SHA-256 |
| --- | --- | --- |
| R1 | `Contents/header.xml` | `fe35bb6c5dc1c240806a8c12be4db8446e08efd79cc7bf7cea7c42134b137d85` |
| R1 | `Contents/section0.xml` | `d37c17279f99e142afdc60683a8025eb57da94324bc57ed100b4466a4724741a` |
| R2 | `Contents/header.xml` | `16841b863f29bbd2d4cd76e311542b6009d352fde8d0c19716b31ac31e6b99e4` |
| R2 | `Contents/section0.xml` | `46b32267cc058977dfd6748a515933879dae92ad73631c23b718d65552b3881d` |

## 2. 실제 namespace와 참조 경로

prefix는 편의 표기이며 식별자는 URI와 local name의 쌍이다.

| prefix | 실제 URI | 사용 위치 |
| --- | --- | --- |
| `hh` | `http://www.hancom.co.kr/hwpml/2011/head` | header의 변경 목록·작성자·서식 |
| `hs` | `http://www.hancom.co.kr/hwpml/2011/section` | section 루트 |
| `hp` | `http://www.hancom.co.kr/hwpml/2011/paragraph` | 문단·run·텍스트·변경 마커 |
| `opf` | `http://www.idpf.org/2007/opf/` | `Contents/content.hpf`의 manifest/spine |

R1의 `META-INF/container.xml`은 패키지 파트를 `Contents/content.hpf`로 가리킨다.
HPF manifest의 `id=header`, `id=section0`은 각각 `Contents/header.xml`,
`Contents/section0.xml`을 가리킨다. 이 표본에는 별도 revision XML 파트가 없다.
`version.xml`의 생성기는 `Hancom Office Hangul`, `xmlVersion=1.4`,
`appVersion=9, 1, 1, 5656 WIN32LEWindows_Unknown_Version`이다.

### R1 header

| XPath | 관찰한 속성·개수 |
| --- | --- |
| `/hh:head/hh:refList/hh:trackChanges` | `itemCnt="2"`, 자식 2개 |
| `…/hh:trackChange[@id='1']` | `type="Insert"`, `authorID="1"`, `hide="0"`, `date` 존재 |
| `…/hh:trackChange[@id='2']` | `type="Delete"`, `authorID="1"`, `hide="0"`, `date` 존재 |
| `/hh:head/hh:refList/hh:trackChangeAuthors` | `itemCnt="1"`, 자식 1개 |
| `…/hh:trackChangeAuthor` | `id="0"`, `mark="1"`, `name` 존재(원값 비공개) |
| `/hh:head/hh:trackchageConfig` | `flags="56"` |

`trackchageConfig`는 실물의 철자 그대로다. `trackchangeConfig`로 고쳐서 기록하지 않는다.
`date` 두 값은 `YYYY-MM-DDTHH:MM:SSZ` 형태다. 실제 시각은 gold 대상에서 제외한다.
`authorID=1`과 유일한 author의 `id=0`은 직접 일치하지 않는다.
**1-based 순번인지, 다른 참조 규칙인지, 잘못 저장된 값인지 미확정**이다.
임의로 1을 빼서 작성자를 확정하지 않는다.

### R1 section: 범위 마커와 mixed content

대상은 `/hs:sec/hp:p[@id='2764991984']/hp:run/hp:t`이다.
다음은 해당 `hp:t`의 전체 mixed content이며 namespace 선언만 생략했다.

```xml
<hp:t>변경<hp:deleteBegin Id="2" TcId="2"/> 추적<hp:deleteEnd Id="2" TcId="2" paraend="0"/> <hp:tab width="3112" leader="0" type="1"/><hp:insertBegin Id="1" TcId="1"/>인간은<hp:insertEnd Id="1" TcId="1" paraend="0"/></hp:t>
```

- 네 마커는 `hp:t`의 **빈 자식 요소**다. `<insert>텍스트</insert>` 같은 wrapper가 아니다.
- 속성은 대소문자를 구별한다: 마커 `Id`·`TcId`, header `id`·`authorID`, 끝 마커 `paraend`.
- 문서 순서는 Delete 2 → Insert 1이며 header 등록 순서와 다르다.
- `Id`가 같은 begin/end를 관찰했고, `TcId`는 같은 값의 header `trackChange@id`와 연결된다.
  이 표본에서는 `Id == TcId`여서 두 식별자의 일반적인 독립성·유효 범위를 증명하지 못한다.
- `t.text`는 `변경`, `deleteBegin.tail`은 선행 공백을 포함한 ` 추적`,
  `deleteEnd.tail`은 공백 하나, `insertBegin.tail`은 `인간은`이다.
  `.text`만 읽거나 `itertext()`로 범위를 없애면 변경 이벤트 또는 탭을 잃는다.
- 끝 마커는 둘 다 `paraend="0"`이다. `paraend=1`일 때 문단 경계 처리는 이 표본으로 확정하지 않는다.

## 3. XML에서 독립 도출한 R1 최소 gold

문단 끝 개행을 추가하지 않고 공백을 보존한다. 이 gold의 텍스트 투영에서는
`hp:tab` 하나를 U+0009로 표현한다. 이는 벤치마크 정규화 규칙이며 탭 너비의 렌더링 검증이 아니다.
`all`은 삽입·삭제 범위 모두, `accepted`는 삭제 제외·삽입 포함,
`rejected`는 삭제 포함·삽입 제외로 정의한다. 한글 UI의 보기 모드와 동일하다고 단정하지 않는다.

```json
{
  "sample": "hwpxlib-ChangeTrack.hwpx",
  "sha256": "05e6384795611406b29302cf62326b6d1f0a9399d2fbc201fcbe459aa730e356",
  "part": "Contents/section0.xml",
  "paragraph_id": "2764991984",
  "events_document_order": [
    {"kind": "Delete", "Id": "2", "TcId": "2", "paraend": "0", "text": " 추적"},
    {"kind": "Insert", "Id": "1", "TcId": "1", "paraend": "0", "text": "인간은"}
  ],
  "text": {
    "all": "변경 추적 \t인간은",
    "accepted": "변경 \t인간은",
    "rejected": "변경 추적 \t"
  },
  "author_resolution": "unconfirmed"
}
```

선행·후행 공백을 `strip()`하지 않는다. 두 이벤트의 `TcId`는 header의 type과 함께 검증한다.
작성자 연결이 미확정이어도 범위·텍스트를 버리거나 작성자 이름을 gold에 끼워 넣지 않는다.

## 4. 서식 변경: R2의 구조 증거

R2 header에는 `Insert=271`, `Delete=157`, `ParaShape=19`로 총 447개
`hh:trackChange`가 있다. section0의 `hp:p@paraTcId` 22개는 모두 존재하는
`ParaShape` 이벤트를 참조한다. 이벤트 수와 참조 횟수는 같지 않다.

개인정보·본문을 제외한 최소 연결 gold:

```json
{
  "sample": "admrul-관세조사-운영-훈령.hwpx",
  "sha256": "27c559e41150a166213dffb33d2e496e6cc4d50d18a6fc159c4fe77eacf5dff8",
  "track_change_counts": {"Insert": 271, "Delete": 157, "ParaShape": 19},
  "paragraph_reference_count": 22,
  "example": {
    "section": "Contents/section0.xml",
    "paragraph_selector": "hp:p[@paraTcId='196']",
    "paraPrIDRef": "14",
    "trackChange_id": "196",
    "trackChange_type": "ParaShape",
    "parashapeID": "13",
    "referenced_paraPr_13_exists": true
  }
}
```

관찰 경로는 `hp:p@paraTcId=196 → hh:trackChange@id=196 → @parashapeID=13
→ hh:refList/hh:paraProperties/hh:paraPr@id=13`이다. 현재 문단의
`paraPrIDRef=14`와 다른 서식 13을 가리킨다는 사실까지 확인했다.
**13이 변경 전 서식인지, 적용·취소 때 13/14를 어떻게 선택하는지는 미확정**이다.

R2의 마커 개수는 insert begin/end `1226/1228`, delete begin/end `505/506`이다.
이 불일치만으로 파일 손상을 단정하지 않는다. 문단 경계·겹침·범위 복원은 별도 규격 검증 대상이며,
R1의 단일 문단 알고리즘을 R2 전체에 적용해 정답이라고 주장하지 않는다.

## 5. 공식 정의로 교차 확인한 범위와 미확정 의미

공식 한컴 모델은 커밋 `1453388472c703a4b299a0834f425cdac16644b9`에서 읽었다.
공개 구현은 스키마·표준 전문을 대체하지 않는다.

| 근거 | 확인한 내용 | 남은 한계 |
| --- | --- | --- |
| [한컴의 표준 스키마 해설](https://tech.hancom.com/python-hwpx-parsing-2/) | `t`의 mixed content와 네 `TrackChangeTag` 요소 | 해설의 2021 namespace를 실물 2011 URI와 자동 동치 처리하지 않음 |
| [trackchangetag.cpp L51–69](https://github.com/hancom-io/hwpx-owpml-model/blob/1453388472c703a4b299a0834f425cdac16644b9/OWPML/Class/Para/trackchangetag.cpp#L51) | `Id`, `TcId`, 끝 마커만 `paraend` 직렬화 | 범위 중첩·문단 경계의 의미 미확정 |
| [trackchange.cpp L80–122](https://github.com/hancom-io/hwpx-owpml-model/blob/1453388472c703a4b299a0834f425cdac16644b9/OWPML/Class/Head/trackchange.cpp#L80) | `type/date/authorID/hide/id`, 조건부 `charshapeID`·`parashapeID` | 작성자 순번 규칙·서식의 전후 의미 미확정 |
| [enumdef.h L2112–2118](https://github.com/hancom-io/hwpx-owpml-model/blob/1453388472c703a4b299a0834f425cdac16644b9/OWPML/Class/enumdef.h#L2112) | `UnKown`, `Insert`, `Delete`, `CharShape`, `ParaShape`의 실제 문자열 | `CharShape` 실물 gold 미확보 |
| [PType.cpp L210–225](https://github.com/hancom-io/hwpx-owpml-model/blob/1453388472c703a4b299a0834f425cdac16644b9/OWPML/Class/Para/PType.cpp#L210), [RunType.cpp L121–133](https://github.com/hancom-io/hwpx-owpml-model/blob/1453388472c703a4b299a0834f425cdac16644b9/OWPML/Class/Para/RunType.cpp#L121) | `hp:p@paraTcId`, run의 `charTcId`; run reader에 `paraTcId` fallback도 존재 | fallback을 새 표준 규칙으로 일반화하지 않음 |

`flags=56`, `hide`, `mark`의 UI 의미·bit 정의, 변경 승인/취소 이력,
이동·표 구조 변경, 작성자·시간 정규화, `paraend=1`, 교차·미완결 범위는 **미확정**이다.
R1의 텍스트 이벤트 읽기와 R2의 참조 보존은 구현 근거가 확보되었지만,
서식 변경의 accepted/rejected 투영은 아직 지원 확정 대상이 아니다.

## 6. 조사·검증 재현 범위

1. 초기 조사 시점의 `corpus/hwp-public/hwpx` 1,687개 파일 중 ZIP 1,685개를 읽고,
   비압축 크기 32 MiB 이하인 `.xml` 파트 10,467개에서 변경 태그를 탐색했다.
   상한을 넘는 XML 파트 1개는 제외했다. 이는 모든 형식·모든 파트의 부재 증명이 아니다.
2. 변경 마커가 있는 파일 4개를 발견했으며, R1 사본을 제외하면 3종이다.
   본문 gold는 공개 테스트 표본 R1만 사용하고 R2는 구조 검증에 한정했다.
3. 선정 ZIP/파트의 SHA-256, QName, 마커 순서·tail, header 참조,
   R2 서식 참조를 표준 라이브러리 `zipfile`·`xml.etree.ElementTree`로 독립 검증했다.
   문서의 JSON gold를 다시 읽어 XML에서 계산한 값과 비교했다.
4. 일반 회귀 테스트·dochan 출력 정확도·한글 UI 표시·전체 XSD 적합성을 검증한 것은 아니다.
   이 문서는 구현이 비교하는 조사 자료이며 조사 자체에 지원 완료 체크를 부여하지 않는다.

현재 API 검증은 [revision-validation.md](revision-validation.md)에 기록한다.
이 문서의 두 JSON 블록은 `tests/test_hwpx_revisions.py`가 직접 읽으므로
표본명·SHA-256·gold 구조와 값, 블록 순서를 유지한다.

```bash
python -m pytest tests/test_hwpx_revisions.py -q -k real --tb=short
```

위 명령은 파일 SHA-256과 R1의 세 모드 텍스트, R2의 부분 지원 진단·XML 보존을
검사한다. 조사 당시의 모든 구조 집계를 재계산하는 명령은 아니다. corpus가 없는
환경은 실물 테스트를 skip하며 검증 성공으로 세지 않는다.

재검증 시 먼저 파일 SHA-256이 위 값과 같은지 확인하고, 지정 파트·QName으로
gold를 비교한다. 원본 ZIP이나 개인정보를 저장소 문서에 복사하지 않는다.
