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
