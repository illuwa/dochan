"""MS-CFB differential verification; reference olefile is optional and never inspected.

Run with ``python -m scripts.compare_cfb_olefile ROOT ... --output result.json``.
Modes: compare (all CFB inputs), convert (seeded samples per format), fuzz (mutations).
Reports contain opaque file IDs, hashes, counts and fixed error categories only;
no document paths, stream names, document contents or exception messages escape.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import importlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import random
import resource
import signal
import sys
import threading
import time

MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
CHUNK = 1024 * 1024
MAX_STREAM = 512 * CHUNK
MAX_INPUT = 512 * CHUNK
MAX_ENTRIES = 100000


def discover_ole(roots):
    """Discover every file with CFB magic, regardless of filename extension."""
    found = set()
    for root in roots:
        root = Path(root)
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if not path.is_file():
                continue
            try:
                with path.open("rb") as source:
                    if source.read(8) == MAGIC:
                        found.add(str(path.resolve()))
            except OSError:
                continue
    return sorted(found)


def error_summary(exc):
    """Fixed categories deliberately exclude potentially private exception text."""
    message = str(exc).lower()
    categories = (
        ("cycle", ("cycle", "cyclic", "loop")),
        ("duplicate_sector", ("duplicate", "overlap", "already used", "cross-linked")),
        ("out_of_range", ("out of range", "outside", "invalid sector", "sector index")),
        ("truncated", ("truncat", "incomplete", "short read", "less than", "not enough")),
        ("chain_length", ("chain length", "chain ended", "chain too", "incorrect last sector")),
        ("directory", ("directory", "entry name", "root entry", "storage tree")),
        ("header", ("header", "magic", "signature", "byte order", "sector size", "version")),
        ("limit", ("limit", "too large", "maximum", "oversized")),
        ("fat", ("fat", "allocation")),
    )
    if isinstance(exc, MemoryError):
        reason = "memory_limit"
    elif isinstance(exc, TimeoutError):
        reason = "timeout"
    else:
        reason = next((name for name, words in categories if any(word in message for word in words)), None)
        if reason is None:
            reason = "invalid_value" if isinstance(exc, ValueError) else "invalid_container" if isinstance(exc, OSError) else "unexpected_exception"
    return {"type": type(exc).__name__, "reason": reason}


def stream_snapshot(ole):
    streams = sorted(tuple(path) for path in ole.listdir(streams=True, storages=False))
    storages = sorted(tuple(path) for path in ole.listdir(streams=False, storages=True))
    if len(streams) + len(storages) > MAX_ENTRIES:
        raise ValueError("entry count limit")
    result = {"storages": storages, "streams": []}
    for path in streams:
        item = {"path": path}
        try:
            item["size"] = ole.get_size(list(path))
            if item["size"] > MAX_STREAM:
                raise ValueError("stream size limit")
            digest = hashlib.sha256()
            size = 0
            with ole.openstream(list(path)) as stream:
                while True:
                    chunk = stream.read(CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_STREAM:
                        raise ValueError("stream size limit")
                    digest.update(chunk)
            item.update(sha256=digest.hexdigest(), read_size=size)
        except Exception as exc:
            item["error"] = error_summary(exc)
        result["streams"].append(item)
    return result


def compare_snapshots(reference, native):
    differences = []
    if reference["storages"] != native["storages"]:
        differences.append("storage_list")
    left = {tuple(s["path"]): s for s in reference["streams"]}
    right = {tuple(s["path"]): s for s in native["streams"]}
    if left.keys() != right.keys():
        differences.append("stream_list")
    for name in sorted(left.keys() & right.keys()):
        a, b = left[name], right[name]
        if a.get("size") != b.get("size"):
            differences.append("stream_size")
        if "error" in a or "error" in b:
            reasons = {item.get("error", {}).get("reason") for item in (a, b)}
            differences.append("stream_limit" if "limit" in reasons else "stream_read_error")
        elif a.get("sha256") != b.get("sha256") or a.get("read_size") != b.get("read_size"):
            differences.append("stream_bytes")
    return sorted(set(differences))


def _snapshot(backend, path):
    try:
        with backend.OleFileIO(path) as ole:
            return {"accepted": True, "snapshot": stream_snapshot(ole)}
    except Exception as exc:
        return {"accepted": False, "error": error_summary(exc)}


def _cfb_compare(path):
    native = importlib.import_module("dochan.cfb")
    reference = importlib.import_module("olefile")
    old, new = _snapshot(reference, path), _snapshot(native, path)
    result = {"reference_accepted": old["accepted"], "native_accepted": new["accepted"]}
    if old["accepted"] and new["accepted"]:
        result["differences"] = compare_snapshots(old["snapshot"], new["snapshot"])
        result["status"] = "different" if result["differences"] else "equal"
        result["streams"] = len(old["snapshot"]["streams"])
        native_streams = {tuple(item["path"]): item for item in new["snapshot"]["streams"]}
        result["verified_streams"] = sum(
            1 for item in old["snapshot"]["streams"]
            if "error" not in item and native_streams.get(tuple(item["path"])) == item
        )
        result["stream_errors"] = {
            "reference": [s["error"] for s in old["snapshot"]["streams"] if "error" in s],
            "native": [s["error"] for s in new["snapshot"]["streams"] if "error" in s],
        }
    else:
        result["status"] = "both_rejected" if not old["accepted"] and not new["accepted"] else "native_only" if new["accepted"] else "reference_only"
    for label, outcome in (("reference", old), ("native", new)):
        if "error" in outcome:
            result[label + "_error"] = outcome["error"]
    return result


@contextmanager
def _backend(module):
    """Swap only dochan module references, restoring them even after failure."""
    native = importlib.import_module("dochan.cfb")
    reference = importlib.import_module("olefile")
    # Import all consumers before swapping, including lazily imported readers.
    for name in ("dochan.reader", "dochan.hwp.bin_data", "dochan.office_binary.doc", "dochan.office_binary.ppt", "dochan.office_binary.xls", "dochan.office_binary.ole_objects", "dochan.crypto.legacy", "dochan.crypto.ooxml", "dochan.crypto.ppt"):
        importlib.import_module(name)
    patches = []
    for name, consumer in list(sys.modules.items()):
        if not name.startswith("dochan.") or consumer is native:
            continue
        for key, value in list(vars(consumer).items()):
            if value is native or value is reference:
                patches.append((consumer, key, value))
                setattr(consumer, key, module)
            elif value is native.OleFileIO or value is reference.OleFileIO:
                patches.append((consumer, key, value))
                setattr(consumer, key, module.OleFileIO)
    try:
        yield
    finally:
        for consumer, key, value in reversed(patches):
            setattr(consumer, key, value)


def _conversion(path, module):
    from dochan import Dochan
    with _backend(module):
        doc = Dochan(path)
        parts = {"markdown": doc.to_markdown(), "json": doc.to_json(), "errors": json.dumps(doc.errors, ensure_ascii=False)}
        return {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in parts.items()}


def _convert_compare(path):
    reference = _conversion(path, importlib.import_module("olefile"))
    native = _conversion(path, importlib.import_module("dochan.cfb"))
    differences = [key for key in reference if reference[key] != native[key]]
    return {"status": "different" if differences else "equal", "differences": differences,
            "reference": reference, "native": native}


def mutated_bytes(data, seed, iteration):
    rng = random.Random((seed << 32) + iteration)
    mode = iteration % 4
    if mode == 0:
        result = bytearray(data)
        for unused in range(rng.randint(1, 16)):
            at = rng.randrange(len(result))
            result[at] ^= rng.randint(1, 255)
        return bytes(result)
    if mode == 1:
        return data[:rng.randrange(len(data))]
    if mode == 2:
        at = rng.randrange(len(data))
        length = min(rng.randint(1, 64), len(data) - at)
        return data[:at] + bytes(rng.randrange(256) for unused in range(length)) + data[at + length:]
    return data + bytes(rng.randrange(256) for unused in range(rng.randint(1, 128)))


def _fuzz(path, seed, iteration):
    from dochan import cfb
    with open(path, "rb") as source:
        data = source.read(MAX_INPUT + 1)
    if len(data) > MAX_INPUT:
        return {"status": "skipped_input_limit"}
    blob = mutated_bytes(data, seed, iteration)
    try:
        with cfb.OleFileIO(io.BytesIO(blob)) as ole:
            snapshot = stream_snapshot(ole)
        errors = [s["error"] for s in snapshot["streams"] if "error" in s]
        unexpected = [e for e in errors if e["reason"] in ("unexpected_exception", "memory_limit", "timeout")]
        return {"status": "unexpected" if unexpected else "accepted", "stream_errors": errors}
    except (TimeoutError, MemoryError) as exc:
        return {"status": "unexpected", "error": error_summary(exc)}
    except (OSError, ValueError, EOFError) as exc:
        return {"status": "rejected", "error": error_summary(exc)}
    except Exception as exc:
        return {"status": "unexpected", "error": error_summary(exc)}


def _timeout(signum, frame):
    raise TimeoutError("per-document timeout")


def _worker_init(memory_mb):
    signal.signal(signal.SIGALRM, _timeout)
    limit = memory_mb * CHUNK
    try:
        resource.setrlimit(resource.RLIMIT_DATA, (limit, limit))
        if sys.platform != "darwin":
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except (OSError, ValueError):
        # Darwin may reject setrlimit even though getrlimit reports infinity.
        # The independent parent RSS/wall-clock watchdog remains active.
        pass


def _child(connection, task, memory_mb, rss_value):
    _worker_init(memory_mb)
    def sample_memory():
        while True:
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_value.value = peak if sys.platform == "darwin" else peak * 1024
            time.sleep(0.05)
    threading.Thread(target=sample_memory, daemon=True).start()
    try:
        connection.send(_work(task))
    finally:
        connection.close()


def bounded_results(tasks, jobs, timeout, memory_mb):
    """Isolate each document and kill runaway children from the parent process."""
    context = multiprocessing.get_context("fork")
    pending = iter(tasks)
    active = {}
    exhausted = False
    try:
        while active or not exhausted:
            while len(active) < jobs and not exhausted:
                try:
                    task = next(pending)
                except StopIteration:
                    exhausted = True
                    break
                parent, child = context.Pipe(duplex=False)
                rss_value = context.Value("Q", 0, lock=False)
                process = context.Process(target=_child, args=(child, task, memory_mb, rss_value))
                process.start()
                child.close()
                active[process.pid] = (process, parent, task, time.monotonic(), rss_value)
            now = time.monotonic()
            for pid, (process, connection, task, started, rss_value) in list(active.items()):
                result = None
                if connection.poll():
                    try:
                        result = connection.recv()
                    except EOFError:
                        result = {"status": "unexpected", "error": {"type": "WorkerExit", "reason": "worker_crash"}}
                elif rss_value.value > memory_mb * CHUNK:
                    process.kill()
                    result = {"status": "unexpected", "error": {"type": "MemoryError", "reason": "memory_limit"}}
                elif now - started > timeout + 1:
                    process.kill()
                    result = {"status": "unexpected", "error": {"type": "TimeoutError", "reason": "timeout"}}
                elif not process.is_alive():
                    result = {"status": "unexpected", "error": {"type": "WorkerExit", "reason": "worker_crash"}}
                    # The child may send and exit between the initial poll and
                    # is_alive(). Drain its final buffered result before
                    # classifying an exit without a result as a crash.
                    if connection.poll():
                        try:
                            result = connection.recv()
                        except EOFError:
                            pass
                if result is None:
                    continue
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join()
                connection.close()
                result.setdefault("id", task[1])
                result.setdefault("format", Path(task[2]).suffix.lower().lstrip("."))
                result.setdefault("seconds", round(now - started, 4))
                result["watchdog_peak_sample_rss_bytes"] = rss_value.value
                del active[pid]
                yield result
            if active:
                time.sleep(0.005)
    finally:
        for process, connection, task, started, rss_value in active.values():
            if process.is_alive():
                process.kill()
            process.join()
            connection.close()


def _work(task):
    mode, index, path, timeout, seed = task
    started = time.monotonic()
    signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        if os.path.getsize(path) > MAX_INPUT:
            result = {"status": "skipped_input_limit"}
        elif mode == "compare":
            result = _cfb_compare(path)
        elif mode == "convert":
            result = _convert_compare(path)
        elif mode in ("convert_reference", "convert_native"):
            backend = "olefile" if mode.endswith("reference") else "dochan.cfb"
            result = {"status": "converted", "hashes": _conversion(path, importlib.import_module(backend))}
        else:
            result = _fuzz(path, seed, index)
    except Exception as exc:
        result = {"status": "unexpected", "error": error_summary(exc)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    result.update(id=index, format=Path(path).suffix.lower().lstrip("."), seconds=round(time.monotonic() - started, 4), peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return result


def select_samples(paths, per_format, seed):
    groups = {}
    for path in paths:
        extension = Path(path).suffix.lower().lstrip(".")
        if extension in ("hwp", "doc", "ppt", "xls"):
            groups.setdefault(extension, []).append(path)
    rng = random.Random(seed)
    return [path for ext in sorted(groups) for path in rng.sample(groups[ext], min(per_format, len(groups[ext])))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--mode", choices=("compare", "convert", "fuzz"), default="compare")
    parser.add_argument("--output", required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--memory-mb", type=int, default=1536)
    parser.add_argument("--per-format", type=int, default=250)
    parser.add_argument("--conversion-backend", choices=("both", "reference", "native"), default="both")
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261003)
    args = parser.parse_args(argv)
    if args.jobs < 1 or args.timeout <= 0 or args.memory_mb < 128 or args.per_format < 1 or args.iterations < 1:
        parser.error("positive limits are required (memory >= 128 MiB)")
    report = {"mode": args.mode, "seed": args.seed, "timeout_seconds": args.timeout,
              "memory_mb": args.memory_mb, "rss_unit": "bytes" if sys.platform == "darwin" else "KiB", "records": []}
    if args.mode != "fuzz":
        try:
            importlib.import_module("olefile")
        except ImportError:
            report["skipped"] = "optional_reference_olefile_not_installed"
            Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
            return 0
    started = time.monotonic()
    paths = discover_ole(args.roots)
    report["discovered"] = len(paths)
    if args.mode == "convert":
        paths = select_samples(paths, args.per_format, args.seed)
    if args.mode == "fuzz" and paths:
        paths = [path for path in paths if 8 <= os.path.getsize(path) <= 8 * CHUNK]
        rng = random.Random(args.seed)
        paths = [rng.choice(paths) for unused in range(args.iterations)] if paths else []
    report["scheduled"] = len(paths)
    if not paths:
        report["fatal"] = "no_eligible_inputs"
    task_mode = "convert_" + args.conversion_backend if args.mode == "convert" and args.conversion_backend != "both" else args.mode
    report["conversion_backend"] = args.conversion_backend if args.mode == "convert" else None
    tasks = [(task_mode, i, path, args.timeout, args.seed) for i, path in enumerate(paths)]
    # Preload application modules once; forked children retain independent state.
    importlib.import_module("dochan.cfb")
    report["memory_enforcement"] = "child RSS peak sampler every 50ms with parent kill; rlimit where supported"
    for index, result in enumerate(bounded_results(tasks, args.jobs, args.timeout, args.memory_mb)):
        report["records"].append(result)
        if (index + 1) % 100 == 0:
            print("completed %d/%d" % (index + 1, len(tasks)), file=sys.stderr, flush=True)
    report["records"].sort(key=lambda item: item["id"])
    report["counts"] = dict(Counter(record["status"] for record in report["records"]))
    report["formats"] = {ext: dict(Counter(r["status"] for r in report["records"] if r["format"] == ext)) for ext in sorted({r["format"] for r in report["records"]})}
    report["seconds"] = round(time.monotonic() - started, 3)
    if args.mode == "compare":
        report["streams_in_both_opened_files"] = sum(r.get("streams", 0) for r in report["records"])
        report["verified_streams"] = sum(r.get("verified_streams", 0) for r in report["records"])
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "records"}, ensure_ascii=False), flush=True)
    bad = {"unexpected", "different", "reference_only", "native_only", "skipped_input_limit"}
    return 1 if report.get("fatal") or any(key in bad for key in report["counts"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
