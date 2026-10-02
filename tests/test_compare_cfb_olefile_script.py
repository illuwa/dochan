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
    results = list(probe.bounded_results([("compare", 0, "/opaque.doc", 1, 42)], 1, 1, 128))
    assert len(results) == 1
    assert results[0]["error"]["reason"] == "worker_crash"
    assert results[0]["id"] == 0
