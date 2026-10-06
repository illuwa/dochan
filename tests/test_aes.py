"""
tests/test_aes.py — 순수 파이썬 AES-128 복호화 테스트

배포용(distribution-copy) HWP 문서의 ViewText 섹션은 AES-128-ECB로
암호화되어 있어 복호화가 필요하다. 외부 암호화 의존성을 추가하지 않기 위해
dochan/utils/aes.py 에 최소 AES-128 복호화만 순정 구현한다.

테스트 벡터는 FIPS-197 Appendix B의 공식 예제(키/평문/암호문 삼중값)를
그대로 사용해 구현 정확성을 HWP 로직과 무관하게 독립적으로 검증한다.
"""
from dochan.utils.aes import aes128_ecb_decrypt


def test_aes128_ecb_decrypt_matches_fips197_appendix_b_vector():
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    ciphertext = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    expected_plaintext = bytes.fromhex("00112233445566778899aabbccddeeff")

    assert aes128_ecb_decrypt(key, ciphertext) == expected_plaintext


def test_aes128_ecb_decrypt_handles_multiple_blocks_independently():
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    ciphertext = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a") * 3
    expected_plaintext = bytes.fromhex("00112233445566778899aabbccddeeff") * 3

    assert aes128_ecb_decrypt(key, ciphertext) == expected_plaintext


def test_tables_are_built_on_first_use_not_at_import():
    # 암호화 문서가 아니어도 `import dochan` 마다 T-테이블을 만들면 모든 CLI 호출과
    # 배치 작업자 시작이 그만큼 느려진다.
    import subprocess
    import sys

    code = (
        "import dochan, dochan.utils.aes as aes\n"
        "assert aes._TABLES == {}, sorted(aes._TABLES)\n"
        "key = bytes(range(16))\n"
        "block = aes.aes_cbc_encrypt_no_pad(key, bytes(16), bytes(range(16, 32)))\n"
        "assert aes.aes_cbc_decrypt_no_pad(key, bytes(16), block) == bytes(range(16, 32))\n"
        "assert sorted(aes._TABLES) == [False, True]\n"
        "print('lazy')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)  # nosemgrep: dangerous-subprocess-use-audit
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "lazy"


def test_sbox_matches_brute_force_inverse_and_fips_197_values():
    from dochan.utils import aes

    def gf_mul(a, b):
        p = 0
        for _ in range(8):
            if b & 1:
                p ^= a
            a = ((a << 1) & 0xFF) ^ (0x1B if a & 0x80 else 0)
            b >>= 1
        return p

    expected = []
    for x in range(256):
        v = next((y for y in range(1, 256) if gf_mul(x, y) == 1), 0)
        s = v
        for _ in range(4):
            v = ((v << 1) | (v >> 7)) & 0xFF
            s ^= v
        expected.append(s ^ 0x63)
    assert aes.SBOX == bytes(expected)
    # FIPS-197 Figure 7
    assert (aes.SBOX[0x00], aes.SBOX[0x53], aes.SBOX[0xFF]) == (0x63, 0xED, 0x16)
    assert all(aes.INV_SBOX[aes.SBOX[i]] == i for i in range(256))


def test_sbox_construction_stays_cheap():
    # S-box 를 역원 전수 탐색으로 만들던 때는 import 마다 약 27ms 였다(전체 import 의 28%).
    import time

    from dochan.utils import aes

    best = float("inf")
    for _ in range(5):
        start = time.perf_counter()
        aes._build_sbox()
        best = min(best, time.perf_counter() - start)
    assert best < 0.005, best
