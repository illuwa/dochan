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
- pytest 와 의존성(lxml, olefile, pyyaml, Pillow, pytesseract)은 Python 3.9 환경에
만 설치돼 있다. `pytest`(=Xcode python3.9)를 쓰고, homebrew `python3`(3.14, pytest
  없음)를 쓰지 말 것.

## 검증 정책

- 새 기능/버그픽스는 TDD: 실패 테스트 → 실패 확인 → 구현 → 통과 → 커밋.
- **거짓 체크 금지**: README `Supported Elements` 표의 ✅ 는 (1) 단위 테스트 +
  (2) 실물 문서 검증을 모두 통과한 항목에만 부여한다. 검증 못 한 것은 ⬜ 로 남긴다.
- 실물 검증 자원: 동일 문서 HWP/HWPX/PDF 쌍은 `test_pairs/`(dev/personal 쪽),
  공개 HWP/HWPX 코퍼스 7,188개는 `corpus/hwp-public/`(gitignore, 재다운로드는
  `scripts/download_public_hwp_corpus.py`). HWPX 파서 결과를 정답지로 삼는다.

## 릴리스

`RELEASING.md` 참조. 요약: `pyproject.toml`·`dochan/__init__.py` 버전 상향 →
`CHANGELOG.md` 확정 → `python -m build` + `twine check` → `git tag vX.Y.Z` 푸시
(→ `.github/workflows/pypi-release.yml` 이 PyPI 게시).

## 커밋

- 사용자가 요청할 때만 커밋/푸시한다. main 에 직접 커밋 전 확인.
- 커밋 메시지는 한국어 conventional commits. 자동 생성되는 `.secaudit/` 는 커밋 금지.
- 코어는 MIT/permissive 만. 외부 변환 엔진·AGPL/GPL 의존성 추가 금지 (native-only).
