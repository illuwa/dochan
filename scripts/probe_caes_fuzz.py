"""Compare native AES against an independent Python source on public PDF inputs.

The path list must contain public PDFs only. Keys and document bytes remain in
memory; the report contains counts, elapsed time and implementation hashes.
An optional instrumented extension exercises the identical Python boundary under
ASan/UBSan without replacing the normally built extension.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import signal
import sys
import time


OPERATIONS = ("aes_cbc_encrypt_no_pad", "aes_cbc_decrypt_no_pad", "aes128_ecb_decrypt")


def outcome(function, arguments):
    try:
        result = function(*arguments)
        return (type(result), result)
    except Exception as exc:
        return (type(exc), str(exc))


def compare(native, reference, name, arguments):
    actual = outcome(getattr(native, name), arguments)
    expected = outcome(getattr(reference, name), arguments)
    if actual != expected:
        # Never print input or key material, including in assertion diagnostics.
        raise AssertionError("AES mismatch: " + name)


def _timeout(signum, frame):
    raise TimeoutError("public PDF parse budget exceeded")


def capture_public_inputs(aes, paths):
    from dochan import Dochan

    samples, seen = [], set()
    originals = {name: getattr(aes, name) for name in OPERATIONS}
    statistics = {"pdfs_attempted": 0, "pdfs_with_aes_calls": 0,
                  "aes_calls": 0, "oversize_calls": 0, "parse_exceptions": 0}

    def capture(name):
        original = originals[name]

        def wrapped(*arguments):
            statistics["aes_calls"] += 1
            if len(arguments[-1]) <= 65536:
                signature = (name, hashlib.sha256(b"".join(arguments)).digest())
                if signature not in seen and len(samples) < 1024:
                    seen.add(signature)
                    samples.append((name, arguments))
            else:
                statistics["oversize_calls"] += 1
            return original(*arguments)
        return wrapped

    for name in originals:
        setattr(aes, name, capture(name))
    previous_handler = signal.signal(signal.SIGALRM, _timeout)
    try:
        for path in paths:
            statistics["pdfs_attempted"] += 1
            calls_before = statistics["aes_calls"]
            try:
                signal.alarm(30)
                Dochan(path)
            except Exception:
                statistics["parse_exceptions"] += 1
            finally:
                signal.alarm(0)
            if statistics["aes_calls"] > calls_before:
                statistics["pdfs_with_aes_calls"] += 1
    finally:
        signal.signal(signal.SIGALRM, previous_handler)
        for name, original in originals.items():
            setattr(aes, name, original)
    statistics["captured_distinct_inputs"] = len(samples)
    return samples, statistics


def mutate(rng, sample, case):
    name, arguments = sample
    key, data = arguments[0], arguments[-1]
    iv = arguments[1] if len(arguments) == 3 else bytes(16)
    size = rng.choice((16, 24, 32)) if case % 5 == 0 else len(key)
    key = (key * 3)[:size]
    if case % 3:
        key = bytearray(key)
        key[rng.randrange(len(key))] ^= rng.randrange(1, 256)
        key = bytes(key)
    # Keep test cost bounded while retaining sampled bytes and block boundaries.
    blocks = rng.randrange(9)
    at = rng.randrange(len(data) // 16 + 1) * 16
    data = data[at:at + 16 * blocks]
    if case % 2:
        data = bytes(value ^ rng.randrange(256) for value in data)
    choice = case % 19
    if choice == 0:
        key = key[:-1]
    elif choice == 1:
        iv = iv[:-1]
    elif choice == 2:
        data += b"\x00"
    elif choice == 3:
        key, iv, data = bytearray(key), bytearray(iv), bytearray(data)
    elif choice == 4:
        key, iv, data = memoryview(key), memoryview(iv), memoryview(data)
    name = OPERATIONS[case % len(OPERATIONS)]
    return name, (key, data) if name == "aes128_ecb_decrypt" else (key, iv, data)


def check_native_boundary(aes):
    from dochan.utils import _caes

    calls = 0
    for size in range(65):
        for operation, arguments in (
            (_caes.block, (bytes(size), bytes(176), 10, 0)),
            (_caes.block, (bytes(16), bytes(size), 10, 1)),
            (_caes.crypt, (bytes(size), bytes(16), bytes(16), 0, 1)),
            (_caes.crypt, (bytes(16), bytes(size), bytes(16), 1, 1)),
            (_caes.crypt, (bytes(16), bytes(16), bytes(size), 1, 0)),
        ):
            try:
                result = operation(*arguments)
                assert type(result) is bytes
            except ValueError:
                pass
            calls += 1
    for rounds in (-1, 0, 9, 10, 11, 12, 13, 14, 15, 2 ** 31):
        try:
            _caes.block(bytes(16), bytes(240), rounds, 0)
        except (ValueError, OverflowError):
            pass
        calls += 1
    return calls


def run(args):
    if args.extension:
        spec = importlib.util.spec_from_file_location("dochan.utils._caes", args.extension)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    from dochan.utils import aes

    if aes.AES_BACKEND != "c":
        raise RuntimeError("Native AES must be enabled")
    reference_path = args.reference_source / "dochan" / "utils" / "aes.py"
    spec = importlib.util.spec_from_file_location("_caes_independent_reference", reference_path)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    if getattr(reference, "AES_BACKEND", "python") != "python":
        raise RuntimeError("Reference must be the pre-acceleration Python source")
    started = time.perf_counter()
    samples, statistics = capture_public_inputs(aes, json.loads(args.paths.read_text()))
    print(json.dumps(statistics), flush=True)
    if not samples:
        raise RuntimeError("No actual public PDF AES inputs were captured")
    # Compare the complete unmodified captured input before taking mutations.
    for name, arguments in samples:
        compare(aes, reference, name, arguments)
    rng = random.Random(args.seed)
    for case in range(args.count):
        name, arguments = mutate(rng, rng.choice(samples), case)
        compare(aes, reference, name, arguments)
        # Internal blocks also cover AES-192 and malformed block length errors.
        key = bytes(rng.randrange(256) for _ in range((16, 24, 32)[case % 3]))
        keys = aes._key_expansion(key)
        rounds = len(key) // 4 + 6
        block = bytes(rng.randrange(256) for _ in range(15 if case % 31 == 0 else 16))
        for operation in ("_encrypt_block", "_decrypt_block"):
            compare(aes, reference, operation, (block, keys, rounds))
    statistics.update({"native_boundary_calls": check_native_boundary(aes),
                       "mutation_cases": args.count, "block_comparisons": args.count * 2,
                       "mismatches": 0, "seed": args.seed,
                       "seconds": time.perf_counter() - started,
                       "reference_sha256": hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                       "source_sha256": hashlib.sha256(
                           (Path(aes.__file__).parent / "_caes.c").read_bytes()).hexdigest()})
    print(json.dumps(statistics, indent=2), flush=True)
    if args.output:
        args.output.write_text(json.dumps(statistics, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", type=Path, required=True)
    parser.add_argument("--reference-source", type=Path, required=True)
    parser.add_argument("--extension", type=Path)
    parser.add_argument("--count", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=20261101)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    run(args)


if __name__ == "__main__":
    main()
