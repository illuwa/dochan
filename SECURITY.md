# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

보안 취약점을 발견하셨다면 **공개 Issue로 올리지 마시고** 아래로 연락해주세요:

**Email**: illuwa@gmail.com

48시간 내에 응답하겠습니다.

## Security Measures

dochan은 신뢰할 수 없는 문서도 안전하게 처리하도록 설계되었습니다:

- Zip Bomb 방어 (zlib/ZIP 해제 크기 제한)
- XXE 차단 (XML 외부 엔티티 비활성화)
- Path Traversal 방지
- 메모리 제한 (표 크기, 재귀 깊이)
- 입력 검증 (FileHeader, 스트림명, 바이너리 바운드 체크)
