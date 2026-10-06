"""실물 PDF 내용 스트림과 그 변형으로 C 스캐너와 순수 Python 스캐너를 차등 비교한다.

사용: python -m scripts.probe_pdf_cscan_fuzz <초> <PDF 경로 JSON 배열 파일>
가속 모듈(`DOCHAN_BUILD_ACCEL=1 python setup.py build_ext --inplace`)이 빌드돼 있어야 한다.
본문은 저장하지 않고 건수만 출력한다. 불일치가 있으면 종료 코드 1.
"""
import json
import random
import struct
import sys
import time

import dochan.pdf.content as content
from dochan import Dochan
from dochan.pdf import _cscan

BUDGET = float(sys.argv[1])

assert content.CONTENT_SCANNER_BACKEND == "c"
Py, C = content._PythonContentScanner, _cscan.Scanner
streams = {}


def record(data):
    if len(streams) < 4000:
        streams.setdefault(hash(data), data)
    return C(data)


content.ContentScanner = record
files = json.load(open(sys.argv[2], encoding="utf-8"))
rng = random.Random(20261006)
rng.shuffle(files)
for path in files[:260]:
    try:
        Dochan(path)
    except Exception:
        pass
content.ContentScanner = C
pool = [d for d in streams.values() if d]
print("recorded streams", len(pool), "bytes", sum(map(len, pool)))


def describe(value):
    if isinstance(value, float):
        return ("f", struct.pack(">d", value))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(describe(v) for v in value))
    if isinstance(value, dict):
        return ("d", tuple((describe(k), describe(v)) for k, v in value.items()))
    return (type(value).__name__, repr(value))


def run(scanner_cls, data, jumps):
    events = []
    try:
        scanner = scanner_cls(data)
    except Exception as exc:
        return [("init-exc", type(exc).__name__)]
    for step in range(len(data) + 8):
        if step in jumps:
            scanner.pos = jumps[step]
        try:
            event = scanner.next()
        except RecursionError:
            events.append(("exc", "RecursionError"))
            break
        except Exception as exc:
            events.append(("exc", type(exc).__name__, scanner.pos))
            break
        if event is None:
            events.append(("end", scanner.pos))
            break
        events.append((event[0], describe(event[1]), scanner.pos))
    return events


def mutate(data):
    data = bytearray(data)
    roll = rng.random()
    if roll < 0.25 and data:
        for _ in range(rng.randint(1, 6)):
            data[rng.randrange(len(data))] = rng.randrange(256)
    elif roll < 0.45 and data:
        del data[rng.randrange(len(data)):]
    elif roll < 0.65 and data:
        at = rng.randrange(len(data))
        data[at:at] = rng.choice([b"(", b")", b"<<", b">>", b"[", b"]", b"%", b"\r", b" 1 0 R ", b"-", b"+.", b"1_0 ",
                                  b"9" * rng.randint(17, 40), b"1e5 ", b"0x1F ", b".", b"..", b"--1 ", b"\x00", b"BI ID EI "])
    elif roll < 0.8 and len(data) > 4:
        a, b = sorted(rng.randrange(len(data)) for _ in range(2))
        del data[a:b]
    else:
        other = rng.choice(pool)
        at = rng.randrange(len(other) + 1)
        data += other[at:at + rng.randint(0, 400)]
    return bytes(data)


started = time.time()
cases = mismatches = 0
while time.time() - started < BUDGET:
    base = rng.choice(pool)
    at = rng.randrange(len(base))
    data = base[at:at + rng.randint(1, 3000)]
    if rng.random() < 0.85:
        data = mutate(data)
    jumps = {}
    if rng.random() < 0.3:
        for _ in range(rng.randint(1, 3)):
            jumps[rng.randint(0, 40)] = rng.choice([rng.randint(-5, len(data) + 5), rng.randrange(len(data) + 1), 2 ** 70, -2 ** 70])
    a, b = run(Py, data, jumps), run(C, data, jumps)
    cases += 1
    if a != b:
        mismatches += 1
        if mismatches <= 3:
            index = next(i for i, (x, y) in enumerate(zip(a, b)) if x != y) if any(x != y for x, y in zip(a, b)) else min(len(a), len(b))
            print("MISMATCH", data[:120], jumps, "\n  py:", a[index:index + 2], "\n  c :", b[index:index + 2])
print(f"cases={cases} mismatches={mismatches} seconds={time.time() - started:.0f}")
sys.exit(1 if mismatches else 0)
