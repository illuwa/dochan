# Contributing to dochan

dochan에 기여해주셔서 감사합니다!

## How to Contribute

### Bug Report

[GitHub Issues](https://github.com/illuwa/dochan/issues)에 버그를 제보해주세요:
- 사용한 Python 버전
- 입력 파일 형식 (HWP/HWPX)
- 에러 메시지 전문
- 가능하면 재현 가능한 파일 첨부

### Feature Request

Issues에 `[Feature]` 태그로 제안해주세요.

### Pull Request

1. Fork & Clone
```bash
git clone https://github.com/YOUR_USERNAME/dochan.git
cd dochan
pip install -e ".[dev]"
```

2. Branch 생성
```bash
git checkout -b feature/your-feature
```

3. 코드 수정 + 테스트
```bash
python -m pytest dochan/tests/
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
pip install -e ".[dev]"
python -m pytest dochan/tests/
```
