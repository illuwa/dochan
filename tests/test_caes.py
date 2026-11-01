"""Optional native AES contract and Python differential checks."""
import os
import random
import struct

import pytest

from dochan.utils import aes
from test_aes_acceleration import MODE_PLAIN, MODE_VECTORS


def test_backend_contract():
    assert aes.AES_BACKEND in ("c", "python")
    if os.environ.get("DOCHAN_DISABLE_ACCEL") == "1":
        assert aes.AES_BACKEND == "python"


@pytest.mark.parametrize("size", (16, 24, 32))
def test_block_differential(size):
    rng = random.Random(size)
    for _ in range(80):
        key = bytes(rng.randrange(256) for _ in range(size))
        block = bytes(rng.randrange(256) for _ in range(16))
        keys = aes._key_expansion(key)
        rounds = size // 4 + 6
        expected = aes._encrypt_block_python(block, keys, rounds)
        assert aes._encrypt_block(block, keys, rounds) == expected
        assert aes._decrypt_block(expected, keys, rounds) == block
        assert aes._decrypt_block_python(expected, keys, rounds) == block


@pytest.mark.parametrize("size", (0, 1, 15, 17, 32))
def test_invalid_block_retains_struct_error(size):
    keys = aes._key_expansion(bytes(16))
    for operation in (aes._encrypt_block, aes._decrypt_block):
        with pytest.raises(struct.error):
            operation(bytes(size), keys, 10)


@pytest.mark.parametrize("size", (16, 32))
@pytest.mark.parametrize("blocks", (0, 1, 2, 17))
def test_cbc_differential(size, blocks):
    key, iv = bytes(range(size)), bytes(range(16))
    data = bytes(range(16)) * blocks
    cipher = aes._aes_cbc_encrypt_no_pad_python(key, iv, data)
    assert aes.aes_cbc_encrypt_no_pad(key, iv, data) == cipher
    assert aes.aes_cbc_decrypt_no_pad(key, iv, cipher) == data
    assert aes._aes_cbc_decrypt_no_pad_python(key, iv, cipher) == data
    assert aes.aes128_ecb_decrypt(key[:16], data) == aes._aes128_ecb_decrypt_python(key[:16], data)


def test_non_bytes_use_python_contract():
    key, iv, data = bytearray(16), memoryview(bytes(16)), bytearray(32)
    assert aes.aes_cbc_encrypt_no_pad(key, iv, data) == aes._aes_cbc_encrypt_no_pad_python(key, iv, data)


def test_native_rejects_malformed_lengths():
    native = pytest.importorskip("dochan.utils._caes")
    for key in (b"", bytes(15), bytes(17), bytes(33)):
        with pytest.raises(ValueError):
            native.crypt(key, bytes(16), bytes(16), 0, 1)
    for block, keys, rounds in ((bytes(15), bytes(176), 10),
                                (bytes(16), bytes(175), 10),
                                (bytes(16), bytes(176), -1),
                                (bytes(16), bytes(176), 14)):
        with pytest.raises(ValueError):
            native.block(block, keys, rounds, 0)


@pytest.mark.parametrize("error", (ImportError, RuntimeError))
def test_only_import_error_falls_back(monkeypatch, error):
    import builtins
    import importlib

    original = builtins.__import__

    def intercepted(name, globals=None, locals=None, fromlist=(), level=0):
        if fromlist == ("_caes",):
            raise error("native loader sentinel")
        return original(name, globals, locals, fromlist, level)

    with monkeypatch.context() as patch:
        patch.delenv("DOCHAN_DISABLE_ACCEL", raising=False)
        patch.setattr(builtins, "__import__", intercepted)
        try:
            if error is ImportError:
                importlib.reload(aes)
                assert aes.AES_BACKEND == "python"
                assert aes.aes_cbc_encrypt_no_pad(bytes(16), bytes(16), bytes(16))
            else:
                with pytest.raises(RuntimeError, match="native loader sentinel"):
                    importlib.reload(aes)
        finally:
            patch.setattr(builtins, "__import__", original)
            importlib.reload(aes)
    importlib.reload(aes)


@pytest.mark.parametrize("key,ecb,cbc", MODE_VECTORS)
def test_native_sp800_38a_modes_all_key_sizes(key, ecb, cbc):
    native = pytest.importorskip("dochan.utils._caes")
    key, ecb, cbc = (bytes.fromhex(value) for value in (key, ecb, cbc))
    iv = bytes(range(16))
    for chaining, expected in ((0, ecb), (1, cbc)):
        assert native.crypt(key, iv, MODE_PLAIN, 0, chaining) == expected
        assert native.crypt(key, iv, expected, 1, chaining) == MODE_PLAIN
        for decrypt in (0, 1):
            assert native.crypt(key, iv, b"", decrypt, chaining) == b""


@pytest.mark.parametrize("key_size", (16, 24, 32))
@pytest.mark.parametrize("bad_size", (0, 1, 15, 17, 31, 33))
def test_native_rejects_bad_iv_and_data_lengths(key_size, bad_size):
    native = pytest.importorskip("dochan.utils._caes")
    for chaining in (0, 1):
        for decrypt in (0, 1):
            with pytest.raises(ValueError):
                native.crypt(bytes(key_size), bytes(bad_size), bytes(16), decrypt, chaining)
            if bad_size % 16:
                with pytest.raises(ValueError):
                    native.crypt(bytes(key_size), bytes(16), bytes(bad_size), decrypt, chaining)


@pytest.mark.parametrize("word", ([0, 1, 2, 3, 4], [1, 2, 3, 4, 5]))
@pytest.mark.parametrize("decrypt", (False, True))
def test_noncanonical_round_words_preserve_python_results_and_errors(word, decrypt):
    keys = aes._RoundKeys([word] * 44)
    mirror = aes._decrypt_block_python if decrypt else aes._encrypt_block_python
    operation = aes._decrypt_block if decrypt else aes._encrypt_block
    try:
        expected = mirror(bytes(16), keys, 10)
    except Exception as error:
        with pytest.raises(type(error)) as actual:
            operation(bytes(16), keys, 10)
        assert str(actual.value) == str(error)
    else:
        assert operation(bytes(16), keys, 10) == expected
