# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅        |
| < 1.0   | ❌        |

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
- 암호화 문서: 암호는 `password=` 키워드나 CLI 표준 입력(`--password-stdin`, `DOCHAN_PASSWORD`)으로만 받고,
  명령줄 인자로는 받지 않으며 오류·경고·출력·로그에 암호 값을 쓰지 않는다. 키 유도 반복 횟수·복호화 크기·시간에 상한을 둔다
- 압축·암호 해제 결과도 같은 ZIP/스트림 상한을 다시 거친다(복호화한 OOXML 패키지 포함)
