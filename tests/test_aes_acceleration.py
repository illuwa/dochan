"""FIPS-197 (2001) C.1–C.3와 SP 800-38A F.1/F.2의 독립 기지 답안."""
import pytest

from dochan.utils import aes


PLAIN = bytes.fromhex("00112233445566778899aabbccddeeff")


@pytest.mark.parametrize("key_size,cipher", [
    (16, "69c4e0d86a7b0430d8cdb78070b4c55a"),
    (24, "dda97ca4864cdfe06eaf70a0ec0d7191"),
    (32, "8ea2b7ca516745bfeafc49904b496089"),
])
def test_fips197_appendix_c_known_answers(key_size, cipher):
    key = bytes(range(key_size))
    schedule = aes._key_expansion(key)
    rounds = key_size // 4 + 6
    cipher = bytes.fromhex(cipher)
    assert aes._encrypt_block(PLAIN, schedule, rounds) == cipher
    assert aes._decrypt_block(cipher, schedule, rounds) == PLAIN


MODE_PLAIN = bytes.fromhex(
    "6bc1bee22e409f96e93d7e117393172a"
    "ae2d8a571e03ac9c9eb76fac45af8e51"
    "30c81c46a35ce411e5fbc1191a0a52ef"
    "f69f2445df4f9b17ad2b417be66c3710"
)
MODE_VECTORS = [
    (
        "2b7e151628aed2a6abf7158809cf4f3c",
        "3ad77bb40d7a3660a89ecaf32466ef97"
        "f5d3d58503b9699de785895a96fdbaaf"
        "43b1cd7f598ece23881b00e3ed030688"
        "7b0c785e27e8ad3f8223207104725dd4",
        "7649abac8119b246cee98e9b12e9197d"
        "5086cb9b507219ee95db113a917678b2"
        "73bed6b8e3c1743b7116e69e22229516"
        "3ff1caa1681fac09120eca307586e1a7",
    ),
    (
        "8e73b0f7da0e6452c810f32b809079e562f8ead2522c6b7b",
        "bd334f1d6e45f25ff712a214571fa5cc"
        "974104846d0ad3ad7734ecb3ecee4eef"
        "ef7afd2270e2e60adce0ba2face6444e"
        "9a4b41ba738d6c72fb16691603c18e0e",
        "4f021db243bc633d7178183a9fa071e8"
        "b4d9ada9ad7dedf4e5e738763f69145a"
        "571b242012fb7ae07fa9baac3df102e0"
        "08b0e27988598881d920a9e64f5615cd",
    ),
    (
        "603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4",
        "f3eed1bdb5d2a03c064b5a7e3db181f8"
        "591ccb10d410ed26dc5ba74a31362870"
        "b6ed21b99ca6f4f9f153e7b1beafed1d"
        "23304b7a39f9f3ff067d8d8f9e24ecc7",
        "f58c4c04d6e5f1ba779eabfb5f7bfbd6"
        "9cfc4e967edb808d679f777bc6702c7d"
        "39f23369a9d9bacfa530e26304231461"
        "b2eb05e2c39be9fcda6c19078c6a9d1b",
    ),
]


@pytest.mark.parametrize("key,ecb,cbc", MODE_VECTORS)
def test_sp800_38a_ecb_cbc_known_answers(key, ecb, cbc):
    key, ecb, cbc = (bytes.fromhex(value) for value in (key, ecb, cbc))
    schedule = aes._key_expansion(key)
    rounds = len(key) // 4 + 6
    encrypted = b"".join(aes._encrypt_block(MODE_PLAIN[i:i + 16], schedule, rounds)
                         for i in range(0, 64, 16))
    decrypted = b"".join(aes._decrypt_block(ecb[i:i + 16], schedule, rounds)
                         for i in range(0, 64, 16))
    assert encrypted == ecb
    assert decrypted == MODE_PLAIN
    iv = bytes(range(16))
    # AES-192 remains an internal primitive; the public CBC API accepts 128/256.
    if len(key) in (16, 32):
        assert aes.aes_cbc_encrypt_no_pad(key, iv, MODE_PLAIN) == cbc
        assert aes.aes_cbc_decrypt_no_pad(key, iv, cbc) == MODE_PLAIN
    else:
        out = bytearray()
        encrypted = bytearray()
        previous = iv
        for i in range(0, 64, 16):
            xor = bytes(a ^ b for a, b in zip(MODE_PLAIN[i:i + 16], previous))
            previous = aes._encrypt_block(xor, schedule, rounds)
            encrypted.extend(previous)
        assert bytes(encrypted) == cbc
        previous = iv
        for i in range(0, 64, 16):
            block = cbc[i:i + 16]
            dec = aes._decrypt_block(block, schedule, rounds)
            out.extend(a ^ b for a, b in zip(dec, previous))
            previous = block
        assert bytes(out) == MODE_PLAIN


def test_aes_block_processing_does_not_repeat_finite_field_multiplication(monkeypatch):
    """The CPU exhaustion regression must not return inside the per-block loop."""
    schedule = aes._key_expansion(bytes(range(16)))

    def unexpected_multiplication(*args):
        pytest.fail("AES block processing repeated GF(2^8) multiplication")

    monkeypatch.setattr(aes, "_gmul", unexpected_multiplication)
    cipher = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    assert aes._decrypt_block(cipher, schedule) == PLAIN
    assert aes._encrypt_block(PLAIN, schedule, 10) == cipher


def test_aes_block_accepts_existing_word_lists_and_buffer_views():
    schedule = list(aes._key_expansion(bytes(range(16))))
    cipher = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    assert aes._decrypt_block(memoryview(cipher), schedule) == PLAIN
    assert aes._encrypt_block(memoryview(PLAIN), schedule, 10) == cipher


def test_aes_public_input_validation_is_preserved():
    with pytest.raises(ValueError):
        aes.aes128_ecb_decrypt(bytes(24), bytes(16))
    with pytest.raises(ValueError):
        aes.aes128_ecb_decrypt(bytes(16), bytes(15))
    for operation in (aes.aes_cbc_decrypt_no_pad, aes.aes_cbc_encrypt_no_pad):
        assert operation(bytes(24), bytes(16), bytes(16)) == b""
        assert operation(bytes(16), bytes(15), bytes(16)) == b""
        assert operation(bytes(16), bytes(16), bytes(15)) == b""
        assert operation(bytes(16), bytes(16), b"") == b""
