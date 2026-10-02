import io

from scripts.compare_cfb_olefile import discover_ole, stream_snapshot, compare_snapshots, mutated_bytes, error_summary


class FakeOle:
    def listdir(self, streams=True, storages=False):
        return [["Storage"]] if storages and not streams else [["Storage", "One"]]

    def get_size(self, name):
        return 3

    def openstream(self, name):
        return io.BytesIO(b"abc")


def test_discover_ole_checks_magic_recursively_and_deduplicates(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    ole = nested / "no-extension"
    ole.write_bytes(bytes.fromhex("d0cf11e0a1b11ae1") + b"x")
    (tmp_path / "false.doc").write_bytes(b"no")
    assert discover_ole([str(tmp_path), str(nested)]) == [str(ole)]


def test_stream_signature_compares_data_and_storage_paths():
    one = stream_snapshot(FakeOle())
    assert compare_snapshots(one, one) == []
    two = stream_snapshot(FakeOle())
    two["streams"][0]["sha256"] = "changed"
    assert compare_snapshots(one, two) == ["stream_bytes"]
    two = stream_snapshot(FakeOle())
    two["storages"] = []
    assert compare_snapshots(one, two) == ["storage_list"]


def test_fuzz_mutations_are_reproducible_bounded_and_changed():
    data = bytes(range(256)) * 8
    values = [mutated_bytes(data, 42, n) for n in range(100)]
    assert values == [mutated_bytes(data, 42, n) for n in range(100)]
    assert all(value != data and len(value) <= len(data) + 128 for value in values)


def test_exception_summary_never_contains_paths_or_payload():
    summary = error_summary(ValueError("private-path/private-content"))
    assert summary == {"type": "ValueError", "reason": "invalid_value"}


def test_conversion_samples_are_seeded_and_cover_formats():
    from scripts.compare_cfb_olefile import select_samples
    paths = ["/data/%d.%s" % (i, ext) for ext in ("hwp", "doc", "ppt", "xls", "zip") for i in range(6)]
    chosen = select_samples(paths, 3, 42)
    assert len(chosen) == 12
    assert chosen == select_samples(paths, 3, 42)
    assert all(not path.endswith(".zip") for path in chosen)


def test_parent_watchdog_classifies_worker_exit(monkeypatch):
    import os
    from scripts import compare_cfb_olefile as probe
    monkeypatch.setattr(probe, "_work", lambda task: os._exit(9))
    # Linux 는 자식에 RLIMIT_AS 를 건다. fork 한 pytest 프로세스는 128 MiB 로는 스레드도 못 띄우므로 넉넉히 준다.
    results = list(probe.bounded_results([("compare", 0, "/opaque.doc", 1, 42)], 1, 5, 4096))
    assert len(results) == 1
    assert results[0]["error"]["reason"] == "worker_crash"
    assert results[0]["id"] == 0


def test_parent_watchdog_reads_result_buffered_during_process_exit(monkeypatch):
    from types import SimpleNamespace
    from scripts import compare_cfb_olefile as probe

    class Connection:
        polls = 0
        closed = False

        def poll(self):
            self.polls += 1
            return self.polls > 1

        def recv(self):
            assert self.polls == 2
            return {"status": "equal"}

        def close(self):
            self.closed = True

    class Process:
        pid = 123

        def __init__(self, target, args):
            pass

        def start(self):
            pass

        def is_alive(self):
            return False

        def join(self, timeout=None):
            pass

    parent, child = Connection(), Connection()
    context = SimpleNamespace(
        Pipe=lambda duplex: (parent, child),
        Value=lambda *args, **kwargs: SimpleNamespace(value=0),
        Process=Process,
    )
    monkeypatch.setattr(probe.multiprocessing, "get_context", lambda method: context)
    results = list(probe.bounded_results([("compare", 42, "/opaque.doc", 1, 42)], 1, 1, 128))
    assert len(results) == 1
    assert results[0]["status"] == "equal"
    assert results[0]["id"] == 42
    assert parent.closed and child.closed


def test_comparison_backend_switches_legacy_irm_reader():
    import pytest
    from dochan import cfb
    from dochan.crypto import legacy
    from scripts import compare_cfb_olefile as probe

    reference = pytest.importorskip("olefile", exc_type=ImportError)
    with probe._backend(reference):
        assert legacy.cfb is reference
    assert legacy.cfb is cfb


def test_reference_backend_translates_recovery_validation_keyword():
    import pytest
    from dochan.office_binary import ole_objects
    from scripts import compare_cfb_olefile as probe
    from test_cfb import compound

    reference = pytest.importorskip('olefile', exc_type=ImportError)
    original = reference.OleFileIO
    raw, _ = compound()
    with probe._backend(reference):
        with ole_objects.cfb.OleFileIO(raw, strict_recovery=True) as ole:
            assert ole.exists('Regular')
    assert reference.OleFileIO is original
