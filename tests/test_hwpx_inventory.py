"""A01 inventory contracts; fixtures contain synthetic metadata and payloads only."""
import hashlib
import json
import os
import struct
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path

import pytest

from scripts import hwpx_inventory as inventory


def write_zip(path, entries=()):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return path


def write_ole(path):
    """Minimal valid compound file: header, root directory, FAT; no streams."""
    header = bytearray(512)
    header[:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<HHHHH", header, 24, 0x003E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIIII", header, 40, 0, 1, 0, 0, 4096,
                     0xFFFFFFFE, 0, 0xFFFFFFFE, 0)
    struct.pack_into("<109I", header, 76, 1, *([0xFFFFFFFF] * 108))
    directory = bytearray(512)
    name = "Root Entry\0".encode("utf-16le")
    directory[:len(name)] = name
    struct.pack_into("<HBBIII", directory, 64, len(name), 5, 1,
                     0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF)
    struct.pack_into("<I", directory, 116, 0xFFFFFFFE)
    fat = struct.pack("<128I", 0xFFFFFFFE, 0xFFFFFFFD, *([0xFFFFFFFF] * 126))
    path.write_bytes(header + directory + fat)
    return path


def rows(report):
    return {row["path"]: row for row in report["files"]}


def test_inventory_uses_magic_instead_of_extension_and_scans_recursively(tmp_path):
    (tmp_path / "nested").mkdir()
    write_zip(tmp_path / "nested" / "wrong.HWP", [("Contents/section0.xml", "synthetic")])
    write_ole(tmp_path / "wrong.hwpx")
    write_zip(tmp_path / "no-extension")
    (tmp_path / "not-a-document.hwpx").write_bytes(b"synthetic unknown input")

    result = inventory.build_inventory(tmp_path)
    files = rows(result)

    assert list(files) == sorted(files)
    assert files["nested/wrong.HWP"]["extension"] == ".hwp"
    assert files["nested/wrong.HWP"]["container"] == "zip"
    assert files["wrong.hwpx"]["container"] == "ole"
    assert files["wrong.hwpx"]["errors"] == []
    assert files["no-extension"]["container"] == "zip"
    assert files["no-extension"]["zip"]["entry_count"] == 0
    assert files["not-a-document.hwpx"]["container"] == "unknown"
    assert files["not-a-document.hwpx"]["errors"] == ["unrecognized_magic"]
    assert result["summary"]["containers"] == {"ole": 1, "unknown": 1, "zip": 2}
    assert result["summary"]["extension_mismatches"] == 3


def test_hashes_duplicates_and_sizes_include_corrupt_files(tmp_path):
    content = b"same synthetic corrupt data"
    for name in ["z.hwpx", "a.hwp", "m.bin"]:
        (tmp_path / name).write_bytes(content)
    (tmp_path / "unique").write_bytes(b"other synthetic data")
    result = inventory.build_inventory(tmp_path)
    digest = hashlib.sha256(content).hexdigest()

    assert result["duplicate_groups"] == [
        {"sha256": digest, "paths": ["a.hwp", "m.bin", "z.hwpx"]}
    ]
    assert rows(result)["a.hwp"]["bytes"] == len(content)
    assert rows(result)["a.hwp"]["sha256"] == digest
    assert result["summary"]["unique_sha256"] == 2
    assert result["summary"]["duplicate_files"] == 2
    assert result["summary"]["files_in_duplicate_groups"] == 3


def test_zip_metadata_never_inflates_document_payloads(tmp_path, monkeypatch):
    path = write_zip(tmp_path / "large.hwpx", [
        ("z/", b""), ("Contents/section0.xml", b"PRIVATE_BODY" * 100_000),
        ("BinData/image.bin", b"\0" * 100_000),
    ])
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
    def forbidden(*args, **kwargs):
        raise AssertionError("document payload must not be decompressed")
    for method in ["open", "read", "extract", "extractall", "testzip"]:
        monkeypatch.setattr(zipfile.ZipFile, method, forbidden)

    result = inventory.build_inventory(tmp_path)
    metadata = result["files"][0]["zip"]
    assert metadata["entry_count"] == 3
    assert metadata["uncompressed_bytes"] == sum(info.file_size for info in infos)
    assert metadata["compressed_bytes"] == sum(info.compress_size for info in infos)
    assert [part["name"] for part in metadata["parts"]] == sorted(info.filename for info in infos)
    section = next(part for part in metadata["parts"] if part["name"].endswith(".xml"))
    assert section["compression_ratio"] > 100
    assert section["compression_method"] == zipfile.ZIP_DEFLATED
    assert "PRIVATE_BODY" not in inventory.to_json(result)
    assert metadata["generator"] is None


def test_zip_keeps_duplicate_names_and_reports_unsafe_names_without_extracting(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        write_zip(tmp_path / "names.hwpx", [("same", "a"), ("same", "bb"),
                  ("../escape", "c"), ("/absolute", "d"), ("C:\\escape", "e")])
    metadata = inventory.build_inventory(tmp_path)["files"][0]["zip"]
    assert metadata["duplicate_names"] == ["same"]
    assert metadata["unsafe_names"] == ["../escape", "/absolute", "C:\\escape"]
    assert len(metadata["parts"]) == 5
    assert [p["index"] for p in metadata["parts"] if p["name"] == "same"] == [0, 1]


@pytest.mark.parametrize("data,container,error", [
    (b"", "unknown", "empty_file"),
    (b"PK\x03\x04truncated", "zip", "invalid_zip"),
    (b"PK\x05\x06truncated", "zip", "invalid_zip"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1truncated", "ole", "invalid_ole"),
])
def test_damaged_inputs_are_structured_errors_and_do_not_abort(tmp_path, data, container, error):
    (tmp_path / "broken.hwpx").write_bytes(data)
    write_zip(tmp_path / "good.hwpx")
    result = inventory.build_inventory(tmp_path)
    broken = rows(result)["broken.hwpx"]
    assert broken["container"] == container
    assert broken["errors"] == [error]
    assert broken["sha256"] == hashlib.sha256(data).hexdigest()
    assert rows(result)["good.hwpx"]["errors"] == []
    assert result["summary"]["files_with_errors"] == 1


@pytest.mark.parametrize("field,value", [(12, 0x7FFFFFFF), (10, 65534)])
def test_zip_directory_budget_is_checked_before_zipfile_allocates(tmp_path, monkeypatch, field, value):
    path = write_zip(tmp_path / "oversize.hwpx")
    data = bytearray(path.read_bytes())
    struct.pack_into("<I" if field == 12 else "<H", data, field, value)
    path.write_bytes(data)
    monkeypatch.setattr(zipfile, "ZipFile", lambda *a, **k: pytest.fail("budget must precede ZipFile"))
    result = inventory.build_inventory(tmp_path)
    assert result["files"][0]["errors"] == ["zip_metadata_limit"]


def test_empty_zip64_is_classified_by_magic(tmp_path):
    end64 = struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0, 0, 0, 0, 0)
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, 0, 1)
    end = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, 65535, 65535, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    (tmp_path / "empty-zip64.hwpx").write_bytes(end64 + locator + end)
    row = inventory.build_inventory(tmp_path)["files"][0]
    assert row["container"] == "zip"
    assert row["errors"] == []
    assert row["zip"]["entry_count"] == 0


def test_zip64_directory_limit_uses_64_bit_declarations(tmp_path, monkeypatch):
    end64 = struct.pack("<4sQHHIIQQQQ", b"PK\x06\x06", 44, 45, 45, 0, 0, 0, 0, 1 << 40, 0)
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, 0, 1)
    end = struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, 0, 0, 0, 0, 0)
    (tmp_path / "oversize-zip64.hwpx").write_bytes(end64 + locator + end)
    monkeypatch.setattr(zipfile, "ZipFile", lambda *a, **k: pytest.fail("budget must precede ZipFile"))
    assert inventory.build_inventory(tmp_path)["files"][0]["errors"] == ["zip_metadata_limit"]


def test_inconsistent_entry_count_is_reported(tmp_path):
    path = write_zip(tmp_path / "wrong-count.hwpx", [("synthetic", "data")])
    data = bytearray(path.read_bytes())
    struct.pack_into("<H", data, len(data) - 12, 0)
    path.write_bytes(data)
    assert inventory.build_inventory(tmp_path)["files"][0]["errors"] == ["invalid_zip"]


def test_encrypted_and_zero_compressed_size_parts_are_metadata_only(tmp_path):
    path = write_zip(tmp_path / "encrypted.hwpx", [("synthetic", "data")])
    data = bytearray(path.read_bytes())
    central = data.index(b"PK\x01\x02")
    struct.pack_into("<H", data, central + 8, 1)
    struct.pack_into("<I", data, central + 20, 0)
    path.write_bytes(data)
    row = inventory.build_inventory(tmp_path)["files"][0]
    assert row["errors"] == []
    assert row["zip"]["encrypted_entries"] == 1
    assert row["zip"]["parts"][0]["compression_ratio"] is None
    assert "Infinity" not in inventory.to_json(row)


def test_generator_reads_only_bounded_version_metadata(tmp_path, monkeypatch):
    write_zip(tmp_path / "generator.hwpx", [
        ("version.xml", '<v:version xmlns:v="urn:synthetic" application="Synthetic Writer" appVersion="1.2"/>'),
        ("Contents/section0.xml", "PRIVATE_BODY"),
    ])
    original_open = zipfile.ZipFile.open
    reads = []
    def checked_open(self, name, *args, **kwargs):
        assert name.filename == "version.xml"
        stream = original_open(self, name, *args, **kwargs)
        original_read = stream.read
        def bounded_read(size=-1):
            assert 0 < size <= inventory.MAX_GENERATOR_BYTES + 1
            reads.append(size)
            return original_read(size)
        stream.read = bounded_read
        return stream
    monkeypatch.setattr(zipfile.ZipFile, "open", checked_open)

    result = inventory.build_inventory(tmp_path)
    assert result["files"][0]["zip"]["generator"] == {
        "application": "Synthetic Writer", "app_version": "1.2"
    }
    assert reads == [inventory.MAX_GENERATOR_BYTES + 1]
    assert "PRIVATE_BODY" not in inventory.to_json(result)


@pytest.mark.parametrize("version,error", [
    (b"x" * 65537, "generator_size_limit"),
    (b"<broken", "invalid_generator_xml"),
    (b'<!DOCTYPE x [<!ENTITY e "PRIVATE_ENTITY">]><x application="&e;"/>', "invalid_generator_xml"),
])
def test_unsafe_generator_metadata_is_bounded_and_reported(tmp_path, version, error):
    write_zip(tmp_path / "bad-version.hwpx", [("version.xml", version)])
    result = inventory.build_inventory(tmp_path)
    assert result["files"][0]["errors"] == [error]
    assert result["files"][0]["zip"]["generator"] is None
    assert "PRIVATE_ENTITY" not in inventory.to_json(result)


def test_oversize_and_encrypted_generator_are_rejected_before_open(tmp_path, monkeypatch):
    write_zip(tmp_path / "large.hwpx", [("version.xml", b"x" * 65537)])
    path = write_zip(tmp_path / "encrypted.hwpx", [("version.xml", "<version/>")])
    data = bytearray(path.read_bytes())
    struct.pack_into("<H", data, data.index(b"PK\x01\x02") + 8, 1)
    path.write_bytes(data)
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *a, **k: pytest.fail("must not inflate"))
    result = rows(inventory.build_inventory(tmp_path))
    assert result["large.hwpx"]["errors"] == ["generator_size_limit"]
    assert result["encrypted.hwpx"]["errors"] == ["encrypted_generator_metadata"]


def test_duplicate_generator_and_bad_generator_crc_are_reported(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        write_zip(tmp_path / "duplicate.hwpx", [("version.xml", "<version/>"), ("version.xml", "<other/>")])
    path = write_zip(tmp_path / "bad-crc.hwpx", [("version.xml", "<version/>")])
    data = bytearray(path.read_bytes())
    struct.pack_into("<I", data, data.index(b"PK\x01\x02") + 16, 0)
    path.write_bytes(data)
    result = rows(inventory.build_inventory(tmp_path))
    assert result["duplicate.hwpx"]["errors"] == ["ambiguous_generator_metadata"]
    assert result["bad-crc.hwpx"]["errors"] == ["unreadable_generator_metadata"]


def test_missing_or_non_directory_root_is_not_reported_as_empty_corpus(tmp_path):
    with pytest.raises(ValueError, match="directory"):
        inventory.build_inventory(tmp_path / "missing")
    path = tmp_path / "file.hwpx"
    path.touch()
    with pytest.raises(ValueError, match="directory"):
        inventory.build_inventory(path)
    assert inventory.build_inventory(tmp_path / ".." / tmp_path.name)["summary"]["total_files"] == 1


def test_symlinks_and_special_files_are_not_followed(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.hwpx").write_bytes(b"PRIVATE_OUTSIDE")
    (root / "file-link").symlink_to(outside / "secret.hwpx")
    (root / "dir-link").symlink_to(outside, target_is_directory=True)
    (root / "broken-link").symlink_to(tmp_path / "absent")
    os.mkfifo(root / "pipe")
    result = inventory.build_inventory(root)
    assert len(result["files"]) == 4
    assert all(row["sha256"] is None for row in result["files"])
    assert all(row["errors"] == ["not_regular_file"] for row in result["files"])
    assert "PRIVATE_OUTSIDE" not in inventory.to_json(result)


def test_symlink_loop_does_not_abort_inventory(tmp_path):
    (tmp_path / "loop").symlink_to("loop")
    result = inventory.build_inventory(tmp_path)
    assert result["files"][0]["errors"] == ["not_regular_file"]


def test_walk_permission_error_does_not_silently_produce_empty_success(tmp_path, monkeypatch):
    def failed_walk(root, *, followlinks, onerror):
        onerror(PermissionError("PRIVATE_ERROR_DETAIL"))
    monkeypatch.setattr(os, "walk", failed_walk)
    with pytest.raises(ValueError, match="cannot enumerate input directory"):
        inventory.build_inventory(tmp_path)


def test_unreadable_file_is_reported_without_exception_text(tmp_path, monkeypatch):
    path = tmp_path / "blocked.hwpx"
    path.touch()
    original_open = Path.open
    def denied(self, *args, **kwargs):
        if self == path:
            raise PermissionError("PRIVATE_ERROR_DETAIL")
        return original_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", denied)
    result = inventory.build_inventory(tmp_path)
    assert result["files"][0]["errors"] == ["unreadable_file"]
    assert result["files"][0]["sha256"] is None
    assert "PRIVATE_ERROR_DETAIL" not in inventory.to_json(result)


def test_optional_source_index_matches_paths_not_basenames(tmp_path):
    root = tmp_path / "hwpx"
    root.mkdir()
    write_zip(root / "one.hwpx")
    source_index = tmp_path / "SOURCES.json"
    source_index.write_text(json.dumps([
        {"path": "hwp/one.hwpx", "source": "wrong", "license": "MIT"},
        {"path": "hwpx/one.hwpx", "source": "synthetic", "license": "MIT",
         "url": "https://example.test/?private=secret", "notes": "PRIVATE_NOTES"},
    ]))
    result = inventory.build_inventory(root, source_index=source_index)
    assert result["files"][0]["sources"] == [{"source": "synthetic", "license": "MIT"}]
    assert result["summary"]["files_with_source"] == 1
    assert "PRIVATE_NOTES" not in inventory.to_json(result)
    assert "private=secret" not in inventory.to_json(result)


@pytest.mark.parametrize("content", ["not JSON", "{}", '[{"source": "missing path"}]',
                                     '[{"path": "one.hwpx", "source": {}}]'])
def test_invalid_source_index_is_an_explicit_input_error(tmp_path, content):
    root = tmp_path / "input"
    root.mkdir()
    source_index = tmp_path / "SOURCES.json"
    source_index.write_text(content)
    with pytest.raises(ValueError):
        inventory.build_inventory(root, source_index=source_index)


def test_empty_corpus_has_no_duplicates_or_errors(tmp_path):
    result = inventory.build_inventory(tmp_path)
    assert result["files"] == result["duplicate_groups"] == []
    assert result["summary"]["total_files"] == result["summary"]["files_with_errors"] == 0


def test_json_is_byte_deterministic_sorted_and_portable(tmp_path):
    root = tmp_path / "one"
    root.mkdir()
    write_zip(root / "z.hwpx", [("z", "z"), ("a", "a")])
    (root / "a.hwpx").write_bytes((root / "z.hwpx").read_bytes())
    first = inventory.to_json(inventory.build_inventory(root))
    os.utime(root / "a.hwpx", (1, 1))
    second = inventory.to_json(inventory.build_inventory(root))
    root.rename(tmp_path / "two")
    third = inventory.to_json(inventory.build_inventory(tmp_path / "two"))
    assert first == second == third
    assert first == json.dumps(json.loads(first), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    assert str(tmp_path) not in first


def test_cli_direct_and_module_invocation_write_identical_json(tmp_path):
    root = tmp_path / "input"
    root.mkdir()
    write_zip(root / "good.hwpx")
    output = tmp_path / "output.json"
    script = Path(inventory.__file__).resolve()
    # Fixed interpreter and repository script; test-owned argv, shell=False.
    direct = subprocess.run([sys.executable, str(script), str(root), "--output", str(output)],  # nosemgrep: dangerous-subprocess-use-audit
                            cwd=tmp_path, capture_output=True, text=True)
    # Fixed module under the current interpreter, without shell evaluation.
    module = subprocess.run([sys.executable, "-m", "scripts.hwpx_inventory", str(root)],  # nosemgrep: dangerous-subprocess-use-audit
                            cwd=script.parents[1], capture_output=True, text=True)
    assert direct.returncode == module.returncode == 0
    assert output.read_text() == module.stdout
    assert json.loads(direct.stdout) == json.loads(module.stdout)["summary"]
    assert direct.stderr == module.stderr == ""


def test_cli_errors_exit_codes_and_output_inside_corpus_is_rejected(tmp_path):
    script = Path(inventory.__file__).resolve()
    def run(*args):
        # Arguments are generated test paths/options, never executable source.
        return subprocess.run([sys.executable, str(script), *map(str, args)],  # nosemgrep: dangerous-subprocess-use-audit
                              capture_output=True, text=True)
    missing = run(tmp_path / "missing")
    assert missing.returncode == 2
    assert "Traceback" not in missing.stderr
    (tmp_path / "broken.hwpx").write_bytes(b"PK\x03\x04broken")
    damaged = run(tmp_path)
    assert damaged.returncode == 1
    assert json.loads(damaged.stdout)["summary"]["files_with_errors"] == 1
    forbidden_output = tmp_path / "report.json"
    rejected = run(tmp_path, "--output", forbidden_output)
    assert rejected.returncode == 2
    assert not forbidden_output.exists()
