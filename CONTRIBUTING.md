# Contributing to dochan

dochan에 기여해주셔서 감사합니다!

## How to Contribute

### Bug Report

[GitHub Issues](https://github.com/illuwa/dochan/issues)에 버그를 제보해주세요:
- 사용한 Python 버전
- 입력 파일 형식 (HWP/HWPX/DOC/PPT/XLS/DOCX/PPTX/XLSX/PDF)
- 에러 메시지 전문
- 가능하면 재현 가능한 파일 첨부

### Feature Request

Issues에 `[Feature]` 태그로 제안해주세요.

### 라이선스·구현 원칙

dochan 은 고유 구현을 지향한다. 구현 근거는 공식 명세와 바이트 관찰만 쓰고, 다른 프로젝트의 코드를 옮기지 않는다.
새 런타임 의존성은 받지 않는다. 자세한 기준은 `AGENTS.md` 의 라이선스 원칙과 `docs/THIRD_PARTY.md` 를 본다.

### Pull Request

1. Fork & Clone
```bash
git clone https://github.com/YOUR_USERNAME/dochan.git
cd dochan
python -m pip install "uv==0.12.3"
uv sync --locked --extra dev
```

2. Branch 생성
```bash
git checkout -b feature/your-feature
```

3. 코드 수정 + 테스트
```bash
uv run --locked --extra dev ruff check dochan scripts tests
uv run --locked --extra dev python -m pytest tests/
```

Maintainers with the local `secaudit` tool installed also run the bounded
tracked-file gate before merging:

```bash
uv run --locked --extra dev python scripts/run_tracked_security_audit.py
```

4. PR 제출

### Code Style

- Python 3.9+ 호환
- docstring은 한국어 또는 영어
- 테스트 추가 권장

## Development Setup

```bash
git clone https://github.com/illuwa/dochan.git
cd dochan
python -m pip install "uv==0.12.3"
uv sync --locked --extra dev
uv run --locked --extra dev ruff check dochan scripts tests
uv run --locked --extra dev python -m pytest tests/
```
