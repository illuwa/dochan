# AGENTS.md — dochan 에이전트 공용 지침

> 이 파일은 Claude·Codex·Hermes·Pi 등 모든 코딩 에이전트가 참조하는 단일 정본이다.
> `CLAUDE.md` 는 이 파일로의 심볼릭 링크다 (한 곳만 고치면 모두 반영).

## 테스트 실행 (중요)

**항상 `python -m pytest tests/` 로 실행한다.**

```bash
python -m pytest tests/            # 전체
python -m pytest tests/test_pdf_reader.py -q   # 단일 파일
```

- `python -m` 은 현재 디렉토리를 `sys.path` 에 넣어 레포의 `dochan/` 과 `scripts/`
  패키지를 모두 잡는다. 따라서 `PYTHONPATH=.` 를 붙일 필요가 없다.
- 그냥 `pytest tests/` 로 실행하면 (a) site-packages 에 설치된 dochan 이 레포
  소스를 가리거나, (b) 벤치마크 테스트가 `No module named 'scripts'` 로 실패한다.
- pytest 와 의존성(lxml, pyyaml, Pillow, pytesseract)은 Python 3.9 환경에
만 설치돼 있다. `pytest`(=Xcode python3.9)를 쓰고, homebrew `python3`(3.14, pytest
  없음)를 쓰지 말 것.
- OLE 컨테이너는 자체 `dochan/cfb.py`로 읽는다. `olefile`은 로컬 비교 검증용이며
  런타임과 일반 테스트에는 필요하지 않다.

## 검증 정책

- 새 기능/버그픽스는 TDD: 실패 테스트 → 실패 확인 → 구현 → 통과 → 커밋.
- **거짓 체크 금지**: README `Supported Elements` 표의 ✅ 는 (1) 단위 테스트 +
  (2) 실물 문서 검증을 모두 통과한 항목에만 부여한다. 검증 못 한 것은 ⬜ 로 남긴다.
- 실물 검증 자원: 동일 문서 HWP/HWPX/PDF 쌍은 `test_pairs/`(dev/personal 쪽),
  공개 HWP/HWPX 코퍼스 7,188개는 `corpus/hwp-public/`(gitignore, 재다운로드는
  `scripts/download_public_hwp_corpus.py`). HWPX 파서 결과를 정답지로 삼는다.
- HWP(바이너리) 파서를 고치면 같은 문서의 HWPX 를 정답으로 `python -m scripts.compare_hwp_pairs test_pairs/`
  로 전후 비교한다 (PDF 는 `scripts/compare_pdf_pairs.py`). 저장소 밖 내부 실물 문서는 파일명·내용을
  코드·테스트·문서·커밋에 절대 올리지 않는다.
- Office·PDF 공개 실물 코퍼스(모두 `corpus/` 아래, gitignore, 저장소에 복사 금지):
  Apache POI test-data(`corpus/poi-src`, doc·ppt·xls ↔ OOXML 같은 이름 짝 + POI 테스트 기대값),
  LibreOffice 테스트 문서(`corpus/lo-src`, docx·pptx·doc·ppt + `.cxx` 기대값), pdf.js 테스트 PDF(`corpus/pdfjs-src`),
  Apache Tika 암호 표본(`corpus/tika-test-docs`). legacy ↔ OOXML 짝 비교는 `python -m scripts.compare_office_pairs`.
  공개 파일명은 벤치마크 문서에 인용해도 된다. 독립 정답지(xlrd)와 OCR 검증(Python 3.10+)은 저장소 밖 venv 에서만 쓴다.
- 칸별 실물 검증 기록은 `docs/benchmarks/` 에 남긴다(표본 파일·정답 근거·기대·실제·판정).

## 라이선스 원칙

- dochan 은 고유 구현을 지향하는 단독 프로젝트다. 구현 근거는 공식 명세([MS-*], ECMA-376/ISO 29500, ISO 32000,
  한컴 공개 명세)와 바이트 관찰만 쓴다. 다른 프로젝트(POI·LibreOffice·pdf.js·pyhwp·hwplib 등)의 코드는 보거나 옮기지 않는다.
- 피할 수 없는 사실 데이터(Adobe Core 14 AFM 폭, Adobe Glyph List, [MS-XLS] Ftab)는 원 출처에서 생성 스크립트로 만들고
  `NOTICE` 와 `docs/THIRD_PARTY.md` 에 출처·라이선스·해시를 남긴다. 새 런타임 의존성은 추가하지 않는다.

## 릴리스

`RELEASING.md` 참조. 요약: `pyproject.toml`·`dochan/__init__.py` 버전 상향 →
`CHANGELOG.md` 확정 → `python -m build` + `twine check` → `git tag vX.Y.Z` 푸시
(→ `.github/workflows/pypi-release.yml` 이 PyPI 게시).

## 커밋

- 사용자가 요청할 때만 커밋/푸시한다. main 에 직접 커밋 전 확인.
- 사전 커밋 보안 게이트(secaudit)는 워크트리 전체를 스캔한다. 출력 요약 도구가 실패를 숨길 수 있으니 커밋 후
  `git log` 로 실제 커밋을 확인한다. subprocess 목록 인자 호출은 `# nosemgrep: dangerous-subprocess-use-audit`,
  XML 은 lxml `XMLParser(resolve_entities=False, load_dtd=False, no_network=True)` 를 쓴다.
- CI 는 Python 3.9–3.13 에 Pillow 없이 돈다(`ruff check dochan scripts tests` 포함). Pillow 는 테스트에서 선택적으로만 쓴다.
- 커밋 메시지는 한국어 conventional commits. 자동 생성되는 `.secaudit/` 는 커밋 금지.
- 코어는 MIT/permissive 만. 외부 변환 엔진·AGPL/GPL 의존성 추가 금지 (native-only).
