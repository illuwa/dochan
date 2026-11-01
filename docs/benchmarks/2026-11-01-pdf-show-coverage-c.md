# PDF C 글자 경로 4차 검증

기준은 `4ad1a29`의 읽기 전용 `base-round2`다. 보류 변경 `a08c1de`를
현재 C 인터프리터의 Fragment 생성 최적화 위에 수동 재적용했다.
커밋·푸시하지 않았고 README·CHANGELOG·reader 및 다른 소유 파일은 변경하지 않았다.
새 의존성은 없다. 기존 제한 API 3.9, 선택 빌드, 비가속 환경변수 경로를 유지한다.

## 동일성 계약과 수용 범위

- 기본 바이트 디코더와 최종 Fragment 8필드 유한성 필터를 복원했다.
  cp1252 미정의 5바이트가 포함되면 TJ 전체를 상태 변경 전에 Python으로 위임한다.
  유한성 필터는 Python 콜백과 Form 조각까지 종료 시점에 검사하며 객체 identity,
  order 및 WARN의 위치·문구를 보존한다. space_width는 기존과 같이 검사하지 않는다.
- 정확한 ToUnicodeCMap의 코드 길이 집합이 정수 `{1, 2}`일 때 표를 만든다.
  연산의 모든 문자열을 긴 코드 우선으로 사전 검사하고, 디코딩 소비 길이가
  WidthMap의 코드 단위와 일치할 때만 실행한다. 경계가 다르거나 잘린 2바이트,
  비정수 길이, 사용자 디코더/폭, 세로 경로는 위임한다.
  이 조건에서 전체 decode와 청크별 decode가 같으므로 문자 위치와 예산이 동일하다.
- link_metrics_reliable=False도 정확한 저장소 디코더/WidthMap이면 실행한다.
  C 표와 인터프리터는 False를 그대로 전달한다. Type3의 그래픽 해석이나
  링크 정확도를 새로 지원한다는 뜻이 아니라 기존 Python 추출 결과를 재현한다.
- 경고가 필요한 Encoding CMap의 범위는 확대하지 않았다. 해당 연산 전체가
  기존 Python에서 실행되어 경고의 문구·중복 제거·순서가 유지된다.
- 딕셔너리는 조회용으로 사용하며 순회 순서에 따른 출력 변경은 없다.
  부동소수 연산 순서, int/float, IEEE 비트 및 기존 -ffp-contract=off를 유지한다.

## 계측 방법

`.codex-work/measure.py --coverage`가 sys.setprofile의 `_show` 호출과
`_build_font_info` 반환을 연결한다. 메서드를 교체하면 인터프리터의 안전 가드가
C를 끄므로, 최종 호출 통계는 메서드 교체 없이 얻었다. 계측 시간은 속도 판정에서 제외했다.
`coverage-before.json`은 별도로 Python 경로 전체의 표 준비 가능성을 세며 실제 잔여 호출과 구분한다.

| Python 잔여 호출 종류 | 전 | 후 |
| --- | ---: | ---: |
| <lambda>:horizontal:reliable:subtype=TrueType | 59 | 59 |
| <lambda>:horizontal:reliable:subtype=Type1 | 937 | 937 |
| <lambda>:horizontal:unreliable:subtype=TrueType | 3 | 3 |
| <lambda>:horizontal:unreliable:subtype=Type0 | 7 | 7 |
| CIDDecoder:horizontal:unreliable:subtype=Type0 | 181 | 181 |
| Core14Decoder:horizontal:unreliable:subtype=Type1 | 2 | 0 |
| ToUnicodeCMap:horizontal:reliable:lengths=1,2:subtype=TrueType | 53 | 0 |
| ToUnicodeCMap:horizontal:reliable:lengths=1,2:subtype=Type0 | 2 | 0 |
| ToUnicodeCMap:horizontal:reliable:lengths=1,2:subtype=Type1 | 57 | 0 |
| ToUnicodeCMap:horizontal:unreliable:lengths=1,2:subtype=Type3 | 101,726 | 0 |
| ToUnicodeCMap:horizontal:unreliable:lengths=1:subtype=Type3 | 10 | 0 |
| _drop_decoder:horizontal:unreliable:subtype=Type0 | 1,435 | 1,435 |
| decode_encoded:horizontal:unreliable:subtype=Type0 | 2 | 2 |
| default_byte_decoder:horizontal:reliable:subtype=TrueType | 118 | 0 |
| default_byte_decoder:horizontal:reliable:subtype=Type1 | 1,044 | 0 |
| default_byte_decoder:horizontal:unreliable:subtype=TrueType | 283 | 1 |
| default_byte_decoder:horizontal:unreliable:subtype=Type1 | 17,306 | 0 |
| default_byte_decoder:horizontal:unreliable:subtype=Type3 | 12 | 0 |
| 합계 | 123,237 | 2,625 |

표본에 세로 및 사용자 WidthMap 호출은 없었다. 일반 테스트에서는 위임을 검증했다.

## 최종 소스 정확성 검증

| 검사 | 결과 |
| --- | --- |
| 이전 변경 TDD | 구현 전 36 실패 / 5 통과 → 복원 후 41 통과 |
| 혼합 길이 TDD | 구현 전 4 실패 / 43 통과 → 통과 |
| 비정수 길이 방어 | 실패 확인 후 Python 위임, 신규 파일 전체 48건 |
| 가속 전체 테스트 | 7,007 passed / 39 skipped / 14 xfailed |
| 비가속 전체 테스트 | 6,997 passed / 49 skipped / 14 xfailed |
| 공개 PDF 4종 해시 | 2,281건, 기준→가속/비가속 차이 0, 실패 0 |
| 일반 실물 차등 | 300문서 / 11,063피연산자 / 100,000변형, 차이 0 |
| 신규 경로 집중 차등 | 300문서 / 3,086피연산자 / 100,000변형, 차이 0 |
| 최종 ASan+UBSan | 일반 100,000 + 집중 100,000 + 유한성 100,000, 진단 0 |
| Xcode 3.9 빌드·엄격 제한 API 컴파일 | 통과 |
| ruff·공백 검사·로컬 경로 검사 | 통과 |

일반 차등은 native 53,417 / yield 46,583, 집중 차등은 native 99,968 /
yield 32이며 Bailout은 0이다. 모든 건을 C 완료라고 세지 않았다.
Fragment 전 필드의 타입·IEEE 비트·순서와 tm/tlm/tc/tw·예산·신뢰도를 비교한다.
일반 및 집중 sanitizer에도 같은 실행 건수가 기록됐다.
ASan은 Python 3.13 framework 실제 실행 파일에 런타임을 주입했다.
`detect_leaks=0`이므로 누수 검증은 아니다. C 파일과 연결 Python 파일의 최종 해시를
sanitizer 복사본과 비교했으며 `final-source-hashes.json`에 남겼다.

## 재현 자료

- 빌드: `DOCHAN_BUILD_ACCEL=1 /usr/bin/python3 setup.py build_ext --inplace --force`.
- 테스트: `/usr/bin/python3 -m pytest tests/ -q -p no:cacheprovider`,
  비가속은 `DOCHAN_DISABLE_ACCEL=1`을 붙인다.
- 공개 해시: `.codex-work/hashes.sh` 및 `collect_pdf.py`.
- 차등: `python -m scripts.probe_pdf_show_full <pdfjs> <press-pairs> --cases 100000`,
  집중 경로는 `.codex-work/fuzz-new.py <source> <pdfjs> <press-pairs> --cases 100000`.
- sanitizer: `.codex-work/final-sanitize.sh`와 `sanitizer-*-final.log`.
- 최종 테스트: `tests-native-post-final.log`, `tests-python-final.log`,
  `ruff-final.log`, `strict-final.log`. 초기 검증과 최종 검증 로그를 구별한다.
- 계측: `actual-before-final.json`, `actual-after-final.json`.
- 성능: `fix-bench-alternating.py`, `fix-filewise-inprocess.py`, `repeat-small.py`.
  계측을 끈 별도 프로세스의 전·후·후·전·전·후 3회 합계 중앙값을 사용한다.
  파일별 비교는 양쪽 예열 후 전·후·후·전(다음 파일은 역순), 각 2회 최솟값이다.
  매 timed 변환의 네 출력 해시를 기준과 비교하고 시간 밖에서 GC와 소스 전환을 한다.
  매 소스 전환에서 실제 Python/C 모듈 경로와 새 API 유무를 단언한다.

## 교대 3회 참고 실측

| Python | 기준 3회(초) | 변경 3회(초) | 중앙값 기준 → 변경(초) | 개선 |
| --- | --- | --- | --- | ---: |
| 3.9 | 7.022415 / 7.213802 / 9.785546 | 6.694951 / 6.313089 / 6.566834 | 7.213802 → 6.566834 | 8.97% |
| 3.12 | 5.103752 / 5.127814 / 5.170717 | 4.759554 / 4.692725 / 4.781376 | 5.127814 → 4.759554 | 7.18% |

두 버전의 관측 중앙값은 목표 6%를 넘었다. 다만 자체 테스트·퍼징을 끝낸 뒤에도
다른 Python 작업 및 Spotlight의 높은 CPU 사용이 측정 전후에 관측됐다.
`host-load-before.json`, `host-load-after-alternating.json`을 보존했다.
**무부하 조건은 충족하지 않았으므로 이 수치만으로 속도 합류를 승인할 수 없다.**
외부 프로세스를 중지하거나 장비 독점을 가정하지 않았다.

## 전수 파일별 회귀 판정

- 2,281건의 모든 timed 변환에서 네 출력 해시 차이 0.
- 원시 2회 최솟값 ≥1.2배: 전체 변환 14건, 파싱 22건, 합집합 22건.
- 10ms 미만 21건의 20회 교대 중앙값 재검사: 전체·파싱 회귀 0.
- 10ms 이상 원시 회귀 **1건**: `156783751.pdf` (전체 51.328 → 62.324ms, 1.214배; 파싱 1.282배).
- 해당 큰 파일의 추가 20회 진단에서는 전체 중앙값 비율 0.9833, 파싱 0.9646으로 재현되지 않았다.
  외부 부하에 따른 변동과 양립하지만 원인을 확정하지 않는다. 공통 규칙은 큰 파일에
  중앙값 대체 예외를 허용하지 않으므로 원시 회귀를 지우거나 합류 통과로 바꾸지 않았다.

| 원시 이상치 | 기준 전체(ms) | 변경 전체(ms) | 원시 전체 비율 | 원시 파싱 비율 | 20회 전체 중앙값 비율 |
| --- | ---: | ---: | ---: | ---: | ---: |
| issue12841_reduced.pdf | 0.800 | 0.970 | 1.213 | 1.228 | 0.978 |
| issue6889.pdf | 0.487 | 0.618 | 1.270 | 1.236 | 0.973 |
| 156783751.pdf | 51.328 | 62.324 | 1.214 | 1.282 | 0.983 |
| firefox_logo.pdf | 0.251 | 0.292 | 1.166 | 1.209 | 1.025 |
| bug1937438_af_from_latex.pdf | 2.077 | 3.444 | 1.658 | 1.699 | 1.001 |
| textshear.pdf | 0.247 | 0.310 | 1.253 | 1.257 | 0.985 |
| annotation_hidden_noview.pdf | 0.230 | 0.271 | 1.178 | 1.204 | 1.012 |
| issue1985.pdf | 0.216 | 0.266 | 1.233 | 1.246 | 0.988 |
| autoprint.pdf | 0.216 | 0.258 | 1.195 | 1.222 | 1.002 |
| bug1844576.pdf | 0.213 | 0.251 | 1.179 | 1.213 | 0.993 |
| issue17929.pdf | 0.242 | 0.293 | 1.212 | 1.237 | 1.003 |
| js-authors.pdf | 0.233 | 0.274 | 1.177 | 1.202 | 1.004 |
| bug1851498.pdf | 0.206 | 0.245 | 1.187 | 1.214 | 1.002 |
| red_stamp.pdf | 0.183 | 0.228 | 1.245 | 1.293 | 1.035 |
| issue5138.pdf | 0.280 | 0.335 | 1.196 | 1.213 | 0.987 |
| images_1bit_grayscale.pdf | 0.222 | 0.271 | 1.221 | 1.230 | 0.991 |
| transfer_maps.pdf | 0.219 | 0.261 | 1.193 | 1.201 | 0.996 |
| ccitt_EndOfBlock_false.pdf | 0.193 | 0.237 | 1.223 | 1.240 | 0.994 |
| issue17679.pdf | 0.249 | 0.315 | 1.267 | 1.270 | 1.003 |
| issue16038.pdf | 0.184 | 0.222 | 1.208 | 1.224 | 1.007 |
| bitmap-refine-tpgron.pdf | 0.166 | 0.233 | 1.406 | 1.331 | 1.011 |
| bitmap-symbol-symbolrefineseveral.pdf | 0.163 | 0.211 | 1.296 | 1.314 | 1.021 |

원자료: `fix-inprocess.json`, `repeat-small.json`, `repeat-large-diagnostic.json`.
큰 파일의 마지막 열은 진단용이며 합류 예외가 아니다. 원시 값과 모든 반복을 보존했다.

## 판정

출력 동일성과 최종 소스 검증은 통과했다. 관측 속도 개선은 3.9 −8.97%,
3.12 −7.18%로 목표를 넘었으나 **합류 보류**다. 다른 부하 없음 조건과
전수 큰 파일 원시 회귀 0 조건을 충족하지 못했다. 외부 부하가 사라진 환경에서
교대 3회와 전수 파일별 검사를 다시 수행해야 한다. 이는 코드에 남긴 미구현이 아니라
성능 합류 조건의 미충족이며, 이번 작업에서 커밋·합류·배포는 하지 않았다.
최종 `host-load-final.json`에서도 외부 Python 및 Spotlight 부하가 지속됐다.

`build/`, `dochan.egg-info/`, sanitizer 소스 복사본은 검증 후 제거했다.
실행 스크립트와 수치/로그 및 네 런타임 소스의 해시는 `.codex-work/`에 남겼다.
