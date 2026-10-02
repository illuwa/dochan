"""Measure deterministic 1 MiB AES workloads; no external crypto dependency."""
import argparse
import json
import time

from dochan.utils.aes import (
    aes128_ecb_decrypt,
    aes_cbc_decrypt_no_pad,
    aes_cbc_encrypt_no_pad,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modes", nargs="+", default=["ecb128", "cbc128", "cbc256"])
    args = parser.parse_args()
    block = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    data = block * (1024 * 1024 // 16)
    for mode in args.modes:
        start = time.perf_counter()
        if mode == "ecb128":
            out = aes128_ecb_decrypt(bytes(range(16)), data)
            assert out == bytes.fromhex("00112233445566778899aabbccddeeff") * (len(data) // 16)
        elif mode in ("cbc128", "cbc256"):
            size = 16 if mode == "cbc128" else 32
            out = aes_cbc_decrypt_no_pad(bytes(range(size)), bytes(16), data)
            assert len(out) == len(data)
        elif mode == "cbc256-encrypt":
            out = aes_cbc_encrypt_no_pad(bytes(range(32)), bytes(16), data)
            assert len(out) == len(data)
        else:
            parser.error("unsupported mode: " + mode)
        elapsed = time.perf_counter() - start
        print(json.dumps({"mode": mode, "bytes": len(data), "seconds": round(elapsed, 6),
                          "mib_per_second": round(1 / elapsed, 6)}), flush=True)


if __name__ == "__main__":
    main()
