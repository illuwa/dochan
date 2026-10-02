# dochan lxml → 표준 라이브러리 XML 대체 평가

> 후속 조치: 4.4절의 XLSX 스트리밍 엔티티 확장 결함은 커밋 `4cc7edc` 에서 고쳤다(회귀 테스트
> `test_large_xlsx_streaming_does_not_expand_dtd_entities`). 대체 여부 결정은
> `docs/superpowers/plans/2026-10-02-improvement-backlog.md` 의 후속 작업 1번에 기록한다.

조사일 2026-10-03, 대상 워크트리 `illuwa/patch-2026-09-06`(HEAD `f7ceaa1`). 읽기 전용 조사이며 저장소 파일은 하나도 고치지 않았다. 실험 스크립트·원자료는 저장소 밖 임시 디렉터리에 두었고 저장소에는 넣지 않았다.

## 결론 먼저

판정은 **"전면 대체 가능(조건부)"** 이다. dochan 은 XPath·`tostring`·XSLT·스키마 같은 lxml 의 무거운 기능을 전혀 쓰지 않는다. lxml 에만 있는 API 는 `getparent`·`getnext`·`getprevious`·`iterancestors`·`iterwalk`·`nsmap`·`docinfo`·`recover` 정도이고, 쓰이는 곳도 약 25군데뿐이다. 공개 코퍼스 XML 파트 64,842개를 두 경로로 파싱해 정규화 트리를 비교했다. 둘 다 파싱한 파트 64,794개 중 64,793개가 같았고, 다른 1개는 lxml 이 recover 모드로 잘라 낸 `deep-table-cell.docx` 였다.

다만 공짜는 아니다. 표준 라이브러리로 가려면 dochan 이 다음 방어를 직접 만들어야 한다.

1. **DOCTYPE·엔티티 차단.** pyexpat 로 프롤로그만 검사하는 방식이 필요하다. 이 저장소의 테스트 환경인 Apple `/usr/bin/python3` 3.9.6 은 **expat 2.2.8** 을 링크하고 있어서, billion laughs 30MB 확장을 그대로 수행했다(RSS +727MB).
2. **깊이 상한.**
3. **큰 토큰 재파싱 대책.** 1MiB 이상 청크로 넣어야 한다.
4. **다중 바이트 인코딩 선언 대응.** EUC-KR·CP949 선언 XML 을 expat 이 거부한다.
5. **XLSX VML 손상 관용 처리.** recover 를 대신해야 하는 곳은 이 한 경로뿐이다.

성능은 파서 단독 기준으로 ET 가 lxml 보다 느리다. 30MB 시트에서 GC 를 켜면 3.2배, 끄면 1.4배이고, 코퍼스 전체 합계로는 2.2배다. 메모리는 시트형 XML 에서 ET 가 25% 적었지만, DOCX 형 XML 에서는 오히려 15% 많았다. dochan 변환 시간 중 XML 파싱이 차지하는 비중은 4~14% 로 측정됐다. 그래서 전체 변환이 얼마나 느려지는지는 포팅 전에는 **확인 못 함** 이고, 추정만 아래에 적었다.

(d) 이중 경로(lxml 은 extra, 표준 라이브러리가 기본)는 **권장하지 않는다**. 대체하기로 하면 단일 표준 라이브러리 경로로 한 번에 옮기는 것이 낫다. 근거는 5절에 있다.

조사 중 이전과 무관한 **현행 결함**도 하나 찾았다. 32MiB 를 넘는 XLSX 시트는 스트리밍 경로(`xlsx.py:534` `etree.iterparse`)로 읽는데, 이 경로는 `resolve_entities=False` 도 `_sanitize_dtd` 도 거치지 않는다. 그래서 내부 엔티티가 실제로 확장된다. 실측 결과는 4.4절에 있다.

---

## 1. lxml 사용처와 고유 기능

`grep -rn "lxml\|etree" dochan/` 에 걸린 런타임 모듈은 9개(75줄)다. etree 를 import 하지 않고 lxml 트리를 넘겨받아 lxml 전용 메서드를 쓰는 `hwpx/revisions.py` 를 더하면 10개가 된다. `ooxml/core.py` 와 `ooxml/math.py` 는 표준 ElementTree 와 같은 API 만 쓰므로 고칠 것이 없다.

| 모듈 | 쓰는 lxml 기능 | 표준 라이브러리 대응 | 난이도 |
|---|---|---|---|
| `ooxml/package.py` | `XMLParser(resolve_entities=False, no_network=True)`와 `huge_tree=True`, `recover=True` 의 3단 파서, `"Excessive depth"` 메시지로 폴백, **`etree.iterwalk(events=start-ns/start/end/comment/pi)`**, **`Element/SubElement(nsmap=...)`**(Strict→Transitional 재작성), `QName(root).namespace`, 주석·PI·엔티티 노드 `deepcopy` | 파서는 하나로 줄이고 프롤로그 검사와 깊이 검사를 붙인다. 네임스페이스 선언은 `iterparse(events=("start-ns",))` 로 잡는다(비용은 fromstring 과 같음, 3.3절). ET 는 접두사를 보존하지 않으므로 `nsmap=` 재작성은 확장 이름만 바꾸는 방식으로 바꾼다 | 높음(핵심) |
| `ooxml/docx.py` | **`getnext`/`getprevious`/`getparent`**(509~515행), **`iterancestors`**(910), **`getparent`**(1742, 1877~1878), `QName(node).localname`(1106, 1721), `XMLSyntaxError` 3곳 | 문서 루트마다 부모 맵을 한 번 만들거나 재귀 호출에 부모를 넘긴다. localname 은 `tag.rpartition("}")` 로 바꾼다 | 중간 |
| `ooxml/xlsx.py` | **`etree.iterparse(tag=..., huge_tree=True, recover=True)`** 스트리밍과 `getprevious`/`getparent` 정리(534~627), **VML `recover=True`**(671), **`getparent`** 루프(780~781), `iterfind(namespaces=)` | `XMLPullParser` 에 1MiB 이상 청크로 넣고, 부모 스택은 직접 관리하며 `clear()` 한다. VML 은 먼저 엄격 파싱하고 실패하면 `html.parser` 로 추출한다(3.4절) | 중상 |
| `ooxml/pptx.py` | **`choice.nsmap.get(prefix)`**(442, `mc:Choice Requires` 판정), `etree.Element`, `deepcopy`, `itertext` | 파싱할 때 잡은 접두사→URI 맵을 넘긴다. 나머지는 ET 에 그대로 있다 | 낮음~중간 |
| `ooxml/charts.py` | `Element`/`SubElement(..., val=...)`, `deepcopy`, `iterfind(namespaces=)`, `XMLSyntaxError` | ET 에 그대로 있다 | 낮음 |
| `hwpx/parser.py` | `XMLParser(resolve_entities=False, no_network=True)`(84), `load_dtd=False, huge_tree=False, recover=False` 파서(1350), **`getroottree().docinfo.doctype`**(1356), **`iterancestors`**(748), `itertext`, 비문자열 tag(**`_Entity`**·주석·PI) 건너뛰기와 tail 보존(1440) | 프롤로그 검사가 docinfo 를 대신한다. 조상 판정은 부모를 넘기는 방식으로 바꾼다. ET 에는 `_Entity` 노드가 없다(엔티티는 확장되거나 오류가 난다) | 낮음~중간 |
| `hwpx/charts.py` | `XMLParser(... load_dtd=False, huge_tree=False, recover=False)`, `docinfo.doctype` | 프롤로그 검사 | 낮음 |
| `hwpx/revisions.py` | **`getparent`** 2곳(193, 210), tail 처리 | 재귀 `walk` 에 부모 인자를 넘긴다 | 낮음 |
| `pdf/annotations.py` | `XMLParser(load_dtd=False, ...)`, `docinfo.doctype`, **`iterancestors`**(깊이 32 판정), **`iterdescendants`**, `QName.localname`, `itertext` | 프롤로그 검사, 스택 순회로 깊이를 잰다. `iter()` 에서 자기 자신을 빼면 iterdescendants 가 된다 | 낮음 |
| `crypto/ooxml.py` | `XMLParser(resolve_entities=False, load_dtd=False, no_network=True)`, `fromstring`, `find` | 이미 UTF-8 디코딩 뒤 문자열로 DOCTYPE/ENTITY 를 거부하고 있다. 그대로 ET 로 바꾸면 된다 | 낮음 |

표준 라이브러리에 직접 대응이 없는 기능은 네 가지다.

- **getparent 계열**: docx 4곳, xlsx 2곳, revisions 2곳, hwpx/parser 1곳, annotations 1곳.
- **nsmap**: pptx 의 `Requires` 판정과 package 의 Strict 재작성.
- **recover**: XLSX VML, 그리고 깊이 초과 시 마지막 폴백.
- **`_Entity` 노드**: HWPX 텍스트 수집.

이번 검색에서 쓰는 곳을 찾지 못한 기능도 확인했다. `xpath()`/`XPath`, `tostring`, `.sourceline`, `itersiblings`, `strip_tags`, `cleanup_namespaces`, `remove_blank_text`, `.prefix` 는 어디에도 쓰이지 않는다. `find`/`findall`/`iterfind` 경로식에는 술어(`[...]`)나 `..` 가 없고, 네임스페이스 맵에 `None` 키도 없다. 따라서 ET 의 ElementPath 와 그대로 호환된다.

동작 차이도 두 가지 확인했다(`hooks_probe.py`). 첫째, 주석과 PI 를 ET 는 기본으로 버리고 앞뒤 텍스트를 합친다. `<t>ab<!--c-->cd<?pi z?>ef<s>g</s>h</t>` 에서 ET 는 `text='abcdef'`, lxml 은 `text='ab'` 에 주석과 PI 노드가 따로 붙는다. 하지만 `itertext()` 결과는 둘 다 `'abcdefgh'` 로 같다. 둘째, ET 는 다중 바이트 인코딩 선언을 처리하지 못한다. EUC-KR·CP949·Shift_JIS 로 선언된 XML 은 `ValueError: multi-byte encodings are not supported` 를 내고, lxml 은 정상으로 읽는다. 코덱으로 디코딩해서 `str` 로 넣으면 ET 도 읽는다. 공개 코퍼스 XML 파트의 인코딩 선언은 모두 UTF-8 이거나 선언 없음(BOM 포함)이었다.

개발 도구인 `scripts/` 에서도 11개 파일이 `from lxml import etree` 를 쓴다(`etree.` 호출 약 46줄). `verify_ooxml_docx.py` 가 17줄로 가장 많고, 그 밖에 `hwpx_inventory.py`, `probe_*` 계열, `benchmark_competitors.py`, `check_doc_font_bookmark_polish.py` 가 있다. 이 가운데 `hwpx_inventory.py`, `verify_ooxml_docx.py`, `probe_hwpx_features.py` 는 `tests/test_hwpx_inventory.py`, `test_docx_verification.py`, `test_docx_order.py` 가 import 한다. 그래서 이 세 스크립트는 런타임과 함께 옮기거나, lxml 을 `dev` extra 로 내려 테스트 의존성으로 남겨야 한다. `compare_hwp_pairs`·`compare_office_pairs` 는 lxml 을 직접 import 하지 않는다. `uv.lock` 에서는 dochan 의 직접 의존성으로 lxml 이 잠겨 있다(278행).

테스트 쪽에서는 13개 파일이 lxml 을 직접 import 하고, `etree.`/`ET.` 호출은 약 77곳이다. 대부분 픽스처를 만드는 `fromstring`/`Element` 라서 기계적으로 바꿀 수 있다. XML 보안 관련 단언은 10개 파일에 있다. 그중 `test_hwpx_charts.py` 는 `etree.XMLParser` 와 `etree.Resolver` 를 몽키패치해서 검증하므로 다시 설계해야 한다.

---

## 2. 보안: 표준 라이브러리 expat 의 기본 동작

### 2.1 공식 문서

Python 3.9 문서의 "XML vulnerabilities" 표에서 `etree` 열은 다음과 같다.

| 공격 | etree |
|---|---|
| billion laughs | Vulnerable (1) |
| quadratic blowup | Vulnerable (1) |
| external entity expansion | Safe (2) |
| DTD retrieval | Safe |
| decompression bomb | Safe |
| large tokens | Vulnerable (6) |

각주 (1)은 expat 2.4.1 이상이면 billion laughs 와 quadratic blowup 에 취약하지 않지만, 시스템 라이브러리에 의존할 수 있어 표에는 취약으로 남겨 둔다는 내용이다. `pyexpat.EXPAT_VERSION` 을 확인하라고 한다. 각주 (2)는 ElementTree 가 외부 엔티티를 확장하지 않고 엔티티를 만나면 `ParserError` 를 낸다는 내용이다. 각주 (6)은 expat 2.6.0 이상이면 큰 토큰 재파싱에 따른 이차 시간 DoS 에 취약하지 않다는 내용이다.

현행 3.14.8 문서는 표 대신 서술로 바뀌었다. 요지는 세 가지다. expat 자체는 로컬 파일 접근이나 네트워크 연결을 하지 않는다. expat 2.7.2 미만은 billion laughs, quadratic blowup, large tokens, 과도한 동적 메모리 사용에 취약할 수 있다. Python 은 expat 사본을 번들하지만, 실제로 번들본을 쓸지 시스템 expat 을 쓸지는 빌드 설정에 달려 있다. 3.13 문서 페이지에서는 가져오기 도구로 표를 찾지 못했다.

pyexpat 문서에 적힌 API 추가 시점은 다음과 같다.

- `SetReparseDeferralEnabled`: 3.13 에 추가됐고, 이전 릴리스 일부에 보안 수정으로 백포트됐다. 그래서 문서는 `hasattr` 로 확인하라고 한다.
- `SetBillionLaughsAttackProtection*`: "Added in version 3.14.6". 기본값은 활성화 임계 8MiB, 최대 증폭 100이지만 expat 에 따라 다르다.
- `SetAllocTracker*`: "Added in version 3.14.1". 기본값은 64MiB, 증폭 100이다.

CPython 각 브랜치가 번들한 expat 버전은 GitHub `Modules/expat/expat.h` 의 브랜치 최신본을 2026-10-03 에 조회한 값이다. 3.9 브랜치는 **2.7.3**, 3.10·3.11·3.12·3.13 브랜치는 **2.8.5** 였다. 개별 패치 릴리스(예: 3.12.4)가 어떤 버전을 번들했는지는 **확인 못 함** 이다. CI 가 쓰는 `actions/setup-python`(ubuntu-latest) 빌드가 번들 expat 을 쓰는지 시스템 expat 을 쓰는지도 **확인 못 함** 이다. 리눅스 배포판 Python 의 expat 버전도 **확인 못 함** 이다.

### 2.2 이 맥에서 관찰한 결과 (`sec_probe.py`)

`ET.fromstring` 에 방어 코드 없이 그대로 넣었다. 아래는 이 맥에 깔린 빌드에서 본 결과이고, "CPython 3.x 의 일반적인 동작"을 뜻하지 않는다.

| 인터프리터 | expat | billion laughs(7단, 30MB) | quadratic(100KB×1000) | 외부 엔티티 `file:///etc/hosts` | 외부 DTD / 매개변수 엔티티(http) | 내부 엔티티 | 깊이 100,000 |
|---|---|---|---|---|---|---|---|
| **3.9.6 Apple `/usr/bin/python3`** | **2.2.8** | **확장함, 0.58s, RSS +727MB** | **확장함(100MB)** | ParseError(undefined entity) | 가져오지 않고 무시, 파싱 성공 | 확장함 | 파싱 성공 |
| 3.10.20 (uv) | 2.8.1 | 증폭 한도로 ParseError | ParseError | ParseError | 무시 | 확장 | 성공 |
| 3.11.17 (brew) | 2.7.4 | ParseError | ParseError | ParseError | 무시 | 확장 | 성공 |
| 3.12.12 (uv) | 2.6.3 | ParseError | ParseError | ParseError | 무시 | 확장 | 성공 |
| 3.13.14 (uv) | 2.8.1 | ParseError | ParseError | ParseError | 무시 | 확장 | 성공 |
| 3.14.8 (brew) | 2.7.4 | ParseError | ParseError | ParseError | 무시 | 확장 | 성공 |

pyexpat 보호 API 가 있는지도 인터프리터마다 달랐다. `SetReparseDeferralEnabled` 는 3.9.6 에만 없었다. `SetBillionLaughsAttackProtection*` 은 3.11.17, 3.13.x, 3.14.8 에는 있고 3.10.20, 3.12.12 에는 없었다. `SetAllocTracker*` 는 3.12.12 와 3.9.6 에 없었다. 버전 번호만 보고 판단할 수 없으므로 `hasattr` 로 확인해야 한다.

비교를 위해 현행 lxml 6.1.1 / libxml2 2.14.6 에 dochan 의 파서 설정을 넣어 같은 입력을 돌렸다(`sec_probe_lxml.py`). billion laughs 와 quadratic 은 증폭 한도로 `XMLSyntaxError` 가 났다. 외부 엔티티와 내부 엔티티는 확장되지 않고 `_Entity` 노드로 남았다. 외부 DTD 는 로드하지 않았다. 깊이는 기본 256, huge_tree 2048 에서 멈췄다. recover 모드에서는 깊이 2047 에서 잘린 트리가 반환됐다.

**핵심 위험**: CLAUDE.md 가 테스트 실행 환경으로 지정한 Xcode python3.9 가 바로 expat 2.2.8 이다. 표준 라이브러리 경로를 쓰면 프로젝트 자신의 테스트 환경에서 증폭 보호가 전혀 없다. 따라서 방어는 expat 버전에 기대지 않는 방식이어야 한다.

### 2.3 dochan 이 직접 넣어야 할 방어 (실측으로 검증한 설계)

**① DOCTYPE 거부는 pyexpat 프롤로그 검사로 한다.** `pyexpat.ParserCreate()` 에 `StartDoctypeDeclHandler` 와 `EntityDeclHandler` 를 걸어 거부 예외를 내게 하고, `StartElementHandler` 에서는 "루트 도달" 예외를 내서 멈춘다. XML 문법상 doctypedecl 은 반드시 루트 요소보다 앞에 오므로, 프롤로그 검사를 통과한 문서는 본 파싱 중에 DOCTYPE 을 만날 수 없다. 측정 결과 7단 폭탄도 0.0000s 에 거부했다. 인코딩 판별은 expat 자신이 하므로 UTF-16 DOCTYPE 도 잡는다. 본 파싱 비용 대비 추가 비용은 무시할 수준이다.

**② `TreeBuilder.doctype()` 훅은 방어가 되지 않는다.** C 가속 `XMLParser` 는 target 의 `doctype()` 이 예외를 내도 expat 을 멈추지 않는다. 예외는 문서를 끝까지 파싱한 뒤에야 올라오고, 그 사이 엔티티 확장에 CPU 를 그대로 쓴다. 3.9.6/expat 2.2.8 에서 단수별로 재 보았다(`hook_scale.py`).

| 폭탄 단수 | 확장 크기 | 예외가 올라오기까지 |
|---|---|---|
| 6단 | 3MB | 0.05s |
| 7단 | 30MB | 0.46s |
| 8단 | 300MB | 4.48s |

시간이 확장 크기에 비례해 늘고, 10단이면 약 450초로 추정된다. 메모리는 늘지 않았다(RSS 11MB). 반면 pyexpat 을 직접 쓰면 핸들러가 예외를 내는 즉시 `XML_StopParser` 로 멈춘다.

**③ 바이트 정규식 정화(`_sanitize_dtd`)만으로는 부족하다.** UTF-16 으로 인코딩된 `<!DOCTYPE ... <!ENTITY e "EXPANDED">` 는 `_sanitize_dtd` 를 지나도 바이트가 그대로였다. 그 결과를 ET 에 넣으면 `'EXPANDED'` 로 확장됐다. 같은 입력을 현행 lxml 에 넣으면 `_Entity` 노드로 남아 안전하다. `crypto/ooxml.py` 주석이 지적한 우회가 `package.py` 에도 똑같이 적용된다는 뜻이다. 따라서 OOXML 은 호환을 위해 기존 정화를 유지하되, 그 뒤에 ①의 프롤로그 검사를 반드시 둬야 한다.

**④ 깊이 상한은 직접 구현해야 한다.** ET 는 깊이 제한이 없다. 다만 C TreeBuilder 가 반복형이어서 깊이 200,000 도 충돌 없이 파싱·순회·해제됐다(3.9/3.11/3.13 확인). `ET.tostring` 은 RecursionError 를 냈고, `copy.deepcopy` 는 3.13 에서만 RecursionError 를 냈다. 세그폴트는 없었다. 깊이 검사 방법에 따라 비용이 달랐다(30MB 시트, 3.9 기준).

| 방법 | 소요 시간 | 비고 |
|---|---|---|
| 파싱 후 반복형 스택 순회 | +약 0.2s | |
| `XMLPullParser` start/end 이벤트 카운터 | 1.47s | fromstring 의 2.4배, RSS +664MB |

그래서 사후 순회를 쓰거나, dochan 의 기존 구조 깊이 가드(`MAX_STRUCTURE_DEPTH=64` 등)와 합치는 편이 낫다.

**⑤ 큰 토큰은 1MiB 이상 청크로 넣는다.** 24MiB 속성값 하나를 스트리밍으로 읽어 보았다.

| 파서 | 청크 | 소요 시간 |
|---|---|---|
| `ET.iterparse` (3.9.6/expat 2.2.8) | 16KiB 고정 | **12.4s** |
| `ET.iterparse` (3.11/expat 2.7.4) | 16KiB 고정 | 0.07s |
| lxml | — | 0.04s |
| `XMLPullParser` (3.9.6) | 1MiB | 0.26s |
| `XMLPullParser` (3.9.6) | 8MiB | 0.08s |

dochan 은 스트리밍 경로에서 파트를 최대 100MiB(`MAX_PART_SIZE`)까지 열 수 있다. 그래서 expat 2.6 미만에서는 `ET.iterparse` 를 그대로 쓰면 안 되고, 청크를 크게 넣는 래퍼가 필요하다. 24MiB 텍스트 노드(문자 데이터)는 어느 쪽이든 문제가 없었다(0.03s).

**⑥ 인코딩을 처리한다.** 다중 바이트 인코딩 선언을 감지하면 Python 코덱으로 디코딩한 뒤 `str` 로 넣는다.

**⑦ 기존 상한은 그대로 둔다.** 파트 크기(`MAX_XML_PART_SIZE`), `b"<"` 개수, ZIP 압축비 상한은 파서와 무관하므로 유지한다.

**⑦-2 HWPX 의 DOCTYPE 정책을 정해 둔다.** 현행 lxml 은 DOCTYPE 이 든 HWPX 섹션을 `_Entity` 노드를 남긴 채 읽는다. 프롤로그 검사만 넣으면 이런 섹션은 통째로 실패한다. 공개 HWPX 12,075 파트에 DOCTYPE 이 0개였으므로 어느 쪽이든 실물 영향은 없다. 그래도 포팅 과정에서 우연히 정해지지 않도록, OOXML 과 같이 `_sanitize_dtd` 로 정화한 뒤 프롤로그 검사를 하는 방식으로 통일하기를 권한다.

**xml.sax 나 pyexpat 직접 사용을 전체 파싱 경로로 쓰지 않는 이유.** 둘 다 밑에서 같은 expat 을 쓰므로 보안 특성이 ET 와 같다. Apple 3.9 의 expat 2.2.8 노출도 그대로 남는다. 게다가 이벤트마다 Python 콜백을 부른다. 그래서 C 가속 `XMLPullParser` 의 start/end 이벤트 경로(30MB 시트 1.47s, `fromstring` 은 GC 켬 0.62s / 끔 0.28s)보다 빠를 수 없다. pyexpat 직접 사용은 ①의 프롤로그 검사처럼 짧은 용도에만 쓴다.

**⑧ 네트워크는 추가 조치가 필요 없다.** ET 는 `ExternalEntityRefHandler` 를 설정하지 않아 외부 자원을 가져오지 않는다(위 표의 http DTD 와 매개변수 엔티티 모두 즉시 반환). 프롤로그 거부를 하면 이 경로 자체가 닫힌다.

---

## 3. 손상 입력 관용성 (recover)과 코퍼스 동일성

### 3.1 recover 를 쓰는 곳

recover 를 쓰는 곳은 세 군데다.

- **XLSX VML 파트**(`xlsx.py:671`, `read_xml_part(vml_path, recover=True)`). 근거는 `docs/benchmarks/2026-06-20-ooxml-improvement-loop.md` 1078행이다. Apache POI `BrNotClosed.xlsx` 의 VML 버튼 텍스트 상자에 닫히지 않은 HTML 식 `<br>` 이 있어서, 엄격 파싱하면 통합 문서 전체가 실패했다. 회귀 테스트는 `tests/test_xlsx_reader.py::test_reads_xlsx_with_malformed_vml_button_markup` 이다.
- **깊이 초과 시 마지막 폴백**(`package.py:279`). 근거는 같은 문서 1179·1269행이다. POI `deep-table-cell.docx` 가 깊이 초과로 실패하던 것을 "bounded recovery parsing" 으로 고쳤다. 측정해 보니 이 파일의 `word/document.xml` 은 최대 깊이 **15,005** 였다. 그래서 256 → 2048 → recover 사다리의 마지막 단까지 실제로 내려간다.
- **XLSX 대형 시트 스트리밍**(`xlsx.py:539`)의 `recover=True`. 이 경로를 정당화하는 실물 근거는 테스트·문서·주석 어디에서도 찾지 못했다(**확인 못 함**).

이 밖에 `test_ooxml_strict.py::test_strict_parser_recovery_and_utf16` 이 `read_xml_part(..., recover=True)` 로 잘린 XML 이 읽히는지 확인한다. 이 테스트는 API 계약을 확인할 뿐 실물 근거는 아니다.

### 3.2 공개 코퍼스 동일성 (`corpus_parity.py`, `corpus_parity.json`)

비교 방법은 다음과 같다. 현행 dochan 경로는 OOXML 이면 `_sanitize_dtd` 후 safe → huge → recover 사다리를 타고, VML 이면 recover 를 쓰며, HWPX 면 제어문자를 제거한 뒤 재시도한다. 표준 라이브러리 경로는 같은 전처리 뒤 프롤로그 검사와 `ET.fromstring` 을 쓴다. 둘 다 성공한 파트는 정규화 트리를 비교했다. 정규화 트리는 요소 시작·끝, 정렬한 속성, 병합한 텍스트만 남기고 주석·PI 는 빼고 tail 은 이은 것이다. Python 3.9.6, expat 2.2.8, lxml 6.1.1 로 돌렸다.

| 코퍼스 | 아카이브 | XML 파트 | 둘 다 성공·동일 | 차이 | lxml 만 성공 | ET 만 성공 | 둘 다 실패 |
|---|---|---|---|---|---|---|---|
| poi-src (docx/xlsx/pptx/m) | 555 | 12,370 | 12,365 | 1 | 3 (VML) | 0 | 1 |
| lo-src (docx/pptx/m) | 2,105 | 40,397 | 40,356 | 0 | 13 (VML) | 1 | 27 |
| hwp-public (hwpx) | 1,674 | 12,075 | 12,072 | 0 | 0 | 0 | 3 |
| tika-test-docs | 0 (6개 모두 ZIP 아님, 암호 표본) | — | — | — | — | — | — |

각 칸의 내용은 다음과 같다.

- **차이 1건**은 `deep-table-cell.docx` 다. lxml recover 는 요소 8,181개, `w:t` 681개(마지막 "Nested level 680")에서 잘렸고, ET 는 요소 60,002개, `w:t` 5,000개를 전부 읽었다. dochan 은 구조 깊이 상한 64에서 먼저 자르므로 최종 출력 차이는 작을 것으로 보이지만, 포팅 전에는 **확인 못 함** 이다.
- **lxml 만 성공한 VML 16건** 중 dochan 출력에 영향을 주는 것은 `BrNotClosed.xlsx` 1건뿐이다. 나머지 15건은 PPTX 의 ActiveX VML(`<![if gte mso 9]>` 조건부 주석)인데, `pptx.py` 는 VML 파트를 읽지 않는다. XLSX VML 은 공개 코퍼스에 42개 있고, 41개가 엄격 파싱으로 읽혔다.
- **ET 만 성공한 1건**은 `lo-src/sd/qa/unit/data/pptx/tdf89927.pptx!customXml/item3.xml` 이다. lxml 은 `'$ListId:Shared Documents;' is not a valid URI` 로 거부했고, ET 는 네임스페이스 URI 검사를 하지 않아 받아들였다. `grep -rni customxml dochan/` 에서는 Strict 네임스페이스 매핑 한 줄만 나왔고, customXml 파트를 읽는 코드는 찾지 못했다.
- **둘 다 실패한 31건**은 POI `xlsx-corrupted.xlsx`, LO `tdf164903.docx` 처럼 `.xml` 이름이 붙은 비XML 파트, 그리고 `encrypt.hwpx` 다. 두 파서가 같은 결과를 냈으므로 회귀가 아니다.
- **DOCTYPE 이 든 파트**는 poi-src 에만 8개 있었다(`ExternalEntityInText.docx`, `54764.xlsx`, `54764-2.xlsx`, `poc-xmlbomb.xlsx`, `poc-xmlbomb-empty.xlsx`). 모두 `_sanitize_dtd` 를 거친 뒤 두 경로가 같은 트리를 냈다. HWPX 12,075개 파트에는 DOCTYPE 이 0개였다. `_Entity` 노드에 의존하는 실물은 공개 코퍼스에 없다는 뜻이다.
- **주석이 든 파트**는 15개(lxml 기준)였고, 모두 정규화 비교에서 같았다.

### 3.3 Strict 네임스페이스와 nsmap 대체 비용

`ET.iterparse(BytesIO(data), events=("start-ns",))` 로 루트와 모든 네임스페이스 선언을 함께 받는 비용은 `fromstring` 과 같았다. 30MB 시트에서 0.277s 대 0.274s, 10MB 문서에서 0.108s 대 0.106s 다(3.9). 이것으로 Strict 감지와 pptx `Requires` 판정에 필요한 접두사 맵을 얻을 수 있다. 같은 접두사가 문서 안에서 다른 URI 로 다시 묶인 경우만 요소별 범위를 따로 추적해야 한다. 이 경우와 Strict 재작성처럼 드문 경로에만 start/end 이벤트를 쓰는 느린 경로를 남기면 된다.

여기에는 함정이 하나 있다. `iterparse` 는 16KiB 고정 청크로 읽으므로 ⑤의 큰 토큰 문제가 그대로 생긴다. 전체 버퍼를 한 번에 넘기는 래퍼가 필요하다.

### 3.4 VML 대안

표준 라이브러리 `html.parser.HTMLParser` 로 `v:imagedata` 속성을 추출해 보았다. LO `activex_picture.pptx` 에서는 `o:relid` 17개를 정상으로 뽑았다. `BrNotClosed.xlsx` 에는 `v:imagedata` 가 없어 빈 결과가 나왔는데, 현행 결과와 같다. dochan 은 이미 docx 에서 `HTMLParser` 를 쓰고 있다.

주의할 점이 하나 있다. HTMLParser 는 접두사 문자열 `v:`/`o:` 에 의존하고 네임스페이스를 해석하지 않는다. 그래서 먼저 ET 로 엄격 파싱하고, 실패할 때만 HTMLParser 로 내려가는 2단 구성을 권한다. 공개 XLSX VML 42개 중 41개가 1단에서 처리된다.

---

## 4. 성능 (합성 벤치마크, 자식 프로세스마다 측정)

입력은 저장소 밖 임시 디렉터리에서 합성했다.

| 파일 | 크기 | 내용 |
|---|---|---|
| `sheet30.xml` | 30MiB | 59,672행 × 10셀, 요소 143만 개 |
| `document.xml` | 10.3MiB | DOCX 형, 요소 54.7만 개 |
| `sheet100.xml` | 100MiB | 195,693행 |
| `bigtoken.xml` / `bigattr.xml` | 24MiB | 큰 텍스트 노드 / 큰 속성값 하나 |

시간은 3~5회 중 최소값이다. 메모리는 자식 프로세스의 `ru_maxrss` 증가분이라 libxml2 의 할당까지 포함한다. 원자료는 `bench_py39.txt`, `bench_py311.txt`, `bench_nogc.txt` 에 있다.

### 4.1 트리 파싱 (Python 3.9.6, expat 2.2.8, lxml 6.1.1)

| 변형 | sheet30 시간 | sheet30 RSS | document 시간 | document RSS |
|---|---|---|---|---|
| lxml `fromstring`(dochan 안전 파서) | **0.196s** | +611MB | **0.055s** | +114MB |
| ET `fromstring` (GC 켬) | 0.624s | **+458MB** | 0.191s | +131MB |
| ET `fromstring` (파싱 중 GC 끔) | 0.278s | +458MB | 0.108s | +131MB |
| ET + 프롤로그 검사 + 깊이 순회 (GC 켬/끔) | 0.853s / 0.502s | +462MB | 0.277s / 0.195s | +135MB |
| ET `XMLPullParser` 깊이 카운터 | 1.47s | +664MB | 0.526s | +209MB |
| 파싱 + 전체 순회(`get`, `text`): lxml / ET | 0.462s / 0.856s | | 0.128s / 0.251s | |
| 모든 요소 부모 조회: lxml `getparent` / ET 부모 맵 | 0.40s / 1.10s | +611 / +598MB | 0.12s / 0.94~1.05s | +114 / +161MB |

Python 3.11.17(expat 2.7.4, lxml 5.4.0)에서 5회 최소값을 재면, sheet30 은 lxml 0.188s, ET 0.531s(GC 끔 0.288s), 가드 포함 0.750s(GC 끔 0.501s)였다. document 는 lxml 0.051s, ET 0.177s(GC 끔 0.109s)였다. 부모 맵은 3.11 에서 0.27s(document)로 3.9 보다 훨씬 빨랐다. 3.9 에서는 GC 가 큰 비용으로 보인다.

이 숫자에서 읽을 수 있는 점은 네 가지다.

- ET 파싱 비용의 상당 부분은 순환 GC 다. 파싱 구간만 `gc.disable()` 하면 lxml 의 1.4~2배까지 줄어든다. 다만 `gc.disable()` 은 프로세스 전역 설정이다. dochan 은 라이브러리이므로 호스트 프로그램의 다른 스레드까지 영향을 받는다. 그래서 기본값으로 쓰기는 어렵다. 대안은 파싱 직후 `gc.freeze()` 로 트리를 GC 대상에서 빼는 방법(효과는 실측하지 않음)이다. 아니면 GC 를 켠 채 받아들이고 순회에서 빨라지는 몫으로 상쇄한다.
- 순회 자체는 ET 가 더 빠르다. lxml 은 프록시 객체를 생성하는 비용이 있다. sheet30 에서 순회 증분은 lxml +0.27s, ET +0.23s 였다.
- 부모 조회는 ET 가 확실히 느리다. 부모 맵은 필요한 문서에서만 지연 생성하는 편이 낫다.
- 메모리는 시트형 XML 에서 ET 가 25% 적었다(+458 대 +611MB). DOCX 형 XML 에서는 15% 많았다(+131 대 +114MB).

### 4.2 대형 시트 스트리밍 (sheet100)

| 변형 | 3.9.6 | 3.11.17 | 메모리 |
|---|---|---|---|
| lxml `iterparse(tag=row)` + `clear` + 앞 형제 삭제(현행 방식) | 3.57~4.04s | 1.41~1.50s | 평탄 |
| ET `iterparse(start,end)` + 부모 스택에서 제거 | 7.01~7.34s | 2.45~2.50s | 평탄 |
| ET `iterparse(end)` + `clear`만 | 5.23~5.82s | 1.85~1.89s | 평탄(+17MB) |

ET 가 1.3~2배 느렸다.

### 4.3 실물 기준

코퍼스 64,842 파트의 파싱 시간 합계(3.9.6, GC 켬, 프롤로그 검사 포함)는 lxml 8.84s, ET 19.43s 로 **2.2배** 차이였다.

dochan 의 현행 변환 시간 중 lxml `fromstring` 이 차지하는 비중은 형식별로 무작위 200파일씩 재서 구했다(`parse_share.py`, 저장소 코드는 런타임 래핑만 했다).

| 형식 | XML 파싱 비중 |
|---|---|
| docx | 9% |
| pptx | 14% |
| xlsx | 4% |
| hwpx | 13% |

여기서 하나 더 눈에 띄었다. 현행 `_normalize_strict_tree` 의 `iterwalk` 비용이 파싱보다 컸다. Strict 가 아닌 파트에서도 모든 노드를 돌기 때문이다(docx 0.46s, pptx 0.23s, xlsx 0.72s, 전체의 10~20%). ET 경로에서는 `start-ns` 캡처로 Strict 감지가 사실상 공짜다. 관계 Type 정규화를 `.rels` 파트로 한정하면 이 비용을 상쇄할 여지가 있다.

**전체 변환 영향 추정**: 파싱 비중 4~14% 에 2.2배를 곱하면 +5~17% 다. 순회가 빨라지는 몫과 iterwalk 를 줄이는 몫을 빼면 0에 가까울 수도 있다. 실측은 포팅한 뒤에만 가능하므로 현재는 **확인 못 함** 이다.

### 4.4 현행 결함 재현 (합성 `entity_stream.xlsx`)

시트에 `<!DOCTYPE worksheet [<!ENTITY e "ENTITY_EXPANDED">]>` 와 `&e;` 를 넣고 `XLSXReader` 로 읽었다.

| 경로 | 셀 결과 | 설명 |
|---|---|---|
| 일반 경로 | `[]` | 정화되어 참조가 제거된다 |
| 스트리밍 경로 | `['ENTITY_EXPANDED']` | `MAX_XML_PART_SIZE` 를 10바이트로 패치해 강제 |

lxml 6 의 `iterparse` 기본값이 내부 엔티티를 해석하기 때문이다. 상한은 libxml2 의 증폭 한도뿐이다. 실험해 보면 4단(30KB) 폭탄은 확장되고, 5단 이상은 recover 모드에서 오류 없이 그 행이 통째로 사라진다. lxml 을 유지하더라도 `resolve_entities=False` 를 추가하거나 DOCTYPE 거부를 넣어 고쳐야 한다.

---

## 5. 결론

### (a) 판정: 전면 대체 가능(조건부)

이유는 네 가지다.

- lxml 고유 기능은 적고 국소적이다(1절).
- 공개 코퍼스에서 트리가 사실상 동일했다(3.2절).
- recover 의존은 출력에 영향을 주는 실물 1건(`BrNotClosed.xlsx`)뿐이고, 표준 라이브러리 `html.parser` 로 대체할 수 있음을 확인했다.
- 깊이 초과 문서는 ET 가 오히려 끝까지 읽는다.

조건은 2.3절의 방어 ①~⑥을 공용 모듈 하나에 모아 모든 파싱 지점이 거치게 하는 것이다. 가장 중요한 것은 pyexpat 프롤로그 검사와 1MiB 이상 청크 입력이다. 이 조건 없이 단순히 `ET.fromstring` 으로 바꾸는 것은 **불가**다. Apple 3.9 의 expat 2.2.8 에서 엔티티 폭탄이 그대로 통과한다.

### (b) 순서와 작업량(대략)

| 단계 | 대상 | 변경 규모(대략) |
|---|---|---|
| 0 | 공용 모듈 신설(예: `dochan/xmlsafe.py`): 프롤로그 검사, GC 일시 정지, 깊이 검사, 인코딩 폴백, 큰 청크 pull 래퍼, `start-ns` 캡처, 부모 맵 헬퍼, `local_name`, `ParseError` 별칭, VML 관용 추출기 | 신규 150~250줄 + 보안 테스트 신규 100~150줄 |
| 1 | `crypto/ooxml.py`, `pdf/annotations.py`, `hwpx/charts.py` (자체 파서를 가진 말단) | 각 5~15줄 |
| 2 | `hwpx/parser.py`, `hwpx/revisions.py` | 20줄 + 10줄 |
| 3 | `ooxml/package.py`(파서 사다리 → 단일 경로, Strict 정규화 재작성), `ooxml/charts.py`, `ooxml/pptx.py`(nsmap), `ooxml/docx.py`(부모·형제 탐색 4곳) | 80~120 + 10 + 15 + 30~40줄 |
| 4 | `ooxml/xlsx.py` (스트리밍, VML, 부모 탐색) | 50~80줄 |
| 5a | `scripts/` 11파일(약 46줄). 테스트가 import 하는 3파일은 필수이고 나머지는 선택이다. 옮기지 않을 스크립트를 위해 lxml 을 `dev` extra 로 둘 수는 있다 | 30~60줄 |
| 5 | 테스트 13파일 약 77곳의 기계적 치환, 보안 테스트(10파일, 특히 `test_hwpx_charts.py` 의 lxml 몽키패치) 재설계 | 100~150줄 |
| 6 | `pyproject.toml` 의존성 제거, `uv.lock` 재잠금, `docs/THIRD_PARTY.md`·README·CHANGELOG | 소량 |

합계는 런타임 약 10파일(+1 신규)에서 400~550줄, 테스트에서 200~300줄, 스크립트에서 30~60줄이다. 1~2단계가 끝나면 HWPX 계열만으로 먼저 검증할 수 있다. 소요 기간은 검증 반복을 포함해 수일 규모로 보지만, 이것은 추정이다.

### (c) 위험과 검증 계획

위험은 다음과 같다.

- **보안**: expat 2.2.8(Apple 3.9). `doctype()` 훅의 착시(2.3 ②). UTF-16 정화 우회(2.3 ③). 큰 토큰(2.3 ⑤).
- **기능**: 다중 바이트 인코딩 선언. HWPX `_Entity` 노드 동작 차이(공개 실물 0건). `deep-table-cell.docx` 출력 변화. VML 관용 경로의 접두사 의존.
- **성능**: 파싱 1.4~3.5배, 스트리밍 1.3~2배. 부모 맵이 3.9 에서 비싸다.
- **깊은 트리 재귀**: lxml 은 깊이 2048 에서 잘라 주었지만 ET 는 끝까지 읽는다. 그래서 깊은 하위 트리를 `deepcopy` 하는 `pptx.py:495`, `charts.py:576·649`, `package.py` Strict 경로에서 3.13 기준 RecursionError 가 날 수 있다. 실행이 멈추지는 않지만, 해당 파트를 잃을 수 있다. 공용 모듈의 깊이 상한을 이 경로들보다 앞에 둬야 한다.
- **CI**: CI 의 expat 버전을 확인하지 못했다.

검증은 다음 순서로 한다.

1. **보안 테스트를 먼저 이식한다(TDD).** billion laughs, quadratic, `file:`/`http:` 외부 엔티티, 외부 DTD, 매개변수 엔티티, UTF-16 DOCTYPE, 깊이 10만, 24MiB 속성 토큰, EUC-KR 선언을 다룬다. 3.9~3.13 전 버전과 **Apple 3.9.6/expat 2.2.8** 에서 모두 돌리고, 시간 상한 단언을 둔다.
2. **트리 동일성을 확인한다.** 이번 `corpus_parity.py` 를 회귀 도구로 써서 64,842 파트에서 차이가 위에 적은 알려진 목록뿐인지 본다.
3. **출력 동일성을 확인한다.** poi-src·lo-src·tika·hwp-public 전체의 Markdown/JSON 을 전후로 바이트 비교한다. 예상되는 차이는 `deep-table-cell.docx` 와 `BrNotClosed.xlsx` 정도이고, 나머지 차이는 전부 원인을 설명해야 한다.
4. **HWP↔HWPX 정답지를 확인한다.** HWPX 파서가 정답지 역할을 하므로 `python -m scripts.compare_hwp_pairs test_pairs/` 전후 결과가 같아야 한다.
5. **성능 회귀를 확인한다.** `parse_share.py` 와 같은 무작위 표본의 변환 시간을 전후로 잰다.
6. **lxml 이 없는 환경에서 돌린다.** `sys.modules["lxml"] = None` 을 주입해 전체 테스트를 실행하고, CI 에서도 lxml 없이 설치·테스트한다.

### (d) 이중 경로(lxml extra + 표준 라이브러리 기본)는 비추천

이유는 다섯 가지다.

1. 보안 계약을 두 파서에 대해 따로 구현하고 따로 증명해야 한다. lxml 은 `_Entity` 노드를 남기고 recover 로 자르며 깊이 2048 에서 멈추는데, ET 는 확장하거나 오류를 내고 깊이 제한이 없다. 의미론이 서로 다르다.
2. 모든 보안 테스트와 코퍼스 동일성 검사가 영구히 두 번씩 돌아야 한다.
3. 설치 환경에 따라 같은 문서의 출력이 달라진다. `deep-table-cell.docx` 와 VML 처리가 그 예이고, dochan 의 "정답지 기반 검증" 원칙과 충돌한다.
4. 기본 경로가 표준 라이브러리인 이상 Apple 3.9 expat 2.2.8 에 대한 방어는 어차피 직접 만들어야 한다. 그 방어를 만든 뒤 lxml 이 더해 주는 것은 속도 2배 남짓뿐이다.
5. 이중 경로는 "의존성 최소화"라는 목표를 절반만 달성한다. extra 라도 지원 표면은 그대로 남는다.

판단은 이렇다. 대체한다면 **단일 표준 라이브러리 경로로 전면 이전**한다. 이전 시점은 olefile 대체가 끝난 뒤가 맞다. 파싱 속도 저하(실측 파서 기준 2배 안팎, 전체 변환 영향은 확인 못 함)를 받아들일 수 없다면 lxml 을 유지하는 것이 이중 경로보다 낫다. 어느 쪽을 택하든 4.4절의 스트리밍 엔티티 확장 결함은 따로 고쳐야 한다.

---
