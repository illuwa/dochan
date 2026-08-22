import io
import os
from pathlib import Path

import pytest

from dochan.batch import BatchSummary, _atomic_write_text, batch_convert
from dochan.cli import main


def _install_fake_reader(monkeypatch, errors=()):
    class FakeDochan:
        def __init__(self, file_path, ocr=False):
            self.file_path = Path(file_path)
            self.errors = list(errors)

        def to_markdown(self):
            return self.file_path.read_text(encoding="utf-8")

        def to_json(self):
            return '{"content": %r}' % self.file_path.read_text(encoding="utf-8")

        def to_plain_text(self):
            return self.file_path.read_text(encoding="utf-8")

    monkeypatch.setattr("dochan.reader.Dochan", FakeDochan)


def test_batch_preserves_relative_paths_and_disambiguates_output_collisions(
    monkeypatch, tmp_path
):
    _install_fake_reader(monkeypatch)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    sources = {
        Path("left/report.hwp"): "left hwp",
        Path("left/report.docx"): "left docx",
        Path("right/report.hwp"): "right hwp",
    }
    for relative_path, content in sources.items():
        source = input_dir / relative_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(content, encoding="utf-8")

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert summary.total == 3
    assert summary.success == 3
    assert summary.failed == 0

    destinations = {
        Path(result.file_path).relative_to(input_dir): Path(result.output_path).relative_to(
            output_dir
        )
        for result in summary.results
    }
    assert destinations[Path("left/report.hwp")].parent == Path("left")
    assert destinations[Path("left/report.docx")].parent == Path("left")
    assert destinations[Path("right/report.hwp")].parent == Path("right")
    assert len(set(destinations.values())) == len(sources)
    assert {
        (output_dir / output_path).read_text(encoding="utf-8")
        for output_path in destinations.values()
    } == set(sources.values())


def test_batch_parallel_workers_parse_verified_private_snapshots(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    sources = {
        "first.docx": "first parallel document",
        "second.docx": "second parallel document",
    }
    for filename, text in sources.items():
        path = input_dir / filename
        from zipfile import ZIP_DEFLATED, ZipFile

        with ZipFile(path, mode="w", compression=ZIP_DEFLATED) as package:
            package.writestr(
                "[Content_Types].xml",
                """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                <Override PartName="/word/document.xml"
                  ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                </Types>""",
            )
            package.writestr(
                "word/document.xml",
                f"""<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
                </w:document>""",
            )

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=2
    )

    assert summary.total == 2
    assert summary.success == 2
    assert summary.failed == 0
    assert {
        path.name: path.read_text(encoding="utf-8")
        for path in output_dir.glob("*.md")
    } == {
        "first.md": "first parallel document",
        "second.md": "second parallel document",
    }


def test_batch_rejects_oversized_source_before_snapshot_copy(
    monkeypatch, tmp_path
):
    reader_calls = []

    class UnexpectedReader:
        def __init__(self, *args, **kwargs):
            reader_calls.append((args, kwargs))

    monkeypatch.setattr("dochan.reader.Dochan", UnexpectedReader)
    monkeypatch.setattr("dochan.batch.MAX_BATCH_SOURCE_SIZE", 3)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "large.hwp").write_bytes(b"1234")

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert summary.total == 1
    assert summary.success == 0
    assert summary.failed == 1
    assert "snapshot size limit" in summary.results[0].errors[0]
    assert reader_calls == []
    assert not (output_dir / "large.md").exists()


def test_batch_convert_rejects_output_aliasing_input_identity(tmp_path, monkeypatch):
    _install_fake_reader(monkeypatch)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source = input_dir / "document.hwp"
    source.write_text("inside", encoding="utf-8")
    output_dir.mkdir()
    output = output_dir / "document.md"
    os.link(source, output)

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert summary.total == 1
    assert summary.failed == 1
    assert summary.results[0].success is False
    assert "aliases a protected input" in summary.results[0].errors[0]
    assert source.read_text(encoding="utf-8") == "inside"
    assert output.read_text(encoding="utf-8") == "inside"


def test_snapshot_copy_stops_after_scanned_size_when_source_grows():
    from dochan.batch import _copy_exact_source

    source = io.BytesIO(b"abc" + (b"x" * 1024 * 1024))
    snapshot = io.BytesIO()

    with pytest.raises(OSError, match="changed while it was read"):
        _copy_exact_source(source, snapshot, 3, "growing.hwp")

    assert snapshot.getvalue() == b"abc"
    assert source.tell() == 4


def test_batch_prunes_nested_output_directory_from_recursive_inputs(monkeypatch, tmp_path):
    _install_fake_reader(monkeypatch)
    input_dir = tmp_path / "input"
    output_dir = input_dir / "generated"
    source = input_dir / "source" / "document.hwp"
    source.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    output_dir.mkdir()
    (output_dir / "stale.hwp").write_text("must not be collected", encoding="utf-8")

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "source" / "document.md").read_text(encoding="utf-8") == "source"
    assert not (output_dir / "stale.md").exists()


def test_batch_rejects_output_subdirectory_symlink_escape(monkeypatch, tmp_path):
    _install_fake_reader(monkeypatch)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    outside_dir = tmp_path / "outside"
    source = input_dir / "nested" / "document.hwp"
    source.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    output_dir.mkdir()
    outside_dir.mkdir()
    sentinel = outside_dir / "document.md"
    sentinel.write_text("sentinel", encoding="utf-8")
    (output_dir / "nested").symlink_to(outside_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes output directory"):
        batch_convert(
            str(input_dir), str(output_dir), output_format="markdown", max_workers=1
        )

    assert sentinel.read_text(encoding="utf-8") == "sentinel"


def test_batch_rejects_input_symlink_before_a_post_planning_target_swap(
    monkeypatch, tmp_path
):
    _install_fake_reader(monkeypatch)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    safe_payload = input_dir / "safe-payload"
    safe_payload.write_text("inside", encoding="utf-8")
    source_link = input_dir / "document.hwp"
    source_link.symlink_to(safe_payload)
    outside_payload = tmp_path / "outside-payload"
    outside_payload.write_text("outside", encoding="utf-8")

    from dochan import batch as batch_module

    real_plan_outputs = batch_module._plan_outputs
    collected_counts = []

    def swap_link_after_planning(files, output_root, output_format):
        planned = real_plan_outputs(files, output_root, output_format)
        collected_counts.append(len(files))
        source_link.unlink()
        source_link.symlink_to(outside_payload)
        return planned

    monkeypatch.setattr(batch_module, "_plan_outputs", swap_link_after_planning)

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert collected_counts == [0]
    assert summary.total == 0
    assert summary.success == 0
    assert summary.failed == 0
    assert outside_payload.read_text(encoding="utf-8") == "outside"
    assert not list(output_dir.rglob("*.md"))


def test_batch_rejects_regular_input_replaced_by_outside_symlink_after_planning(
    monkeypatch, tmp_path
):
    _install_fake_reader(monkeypatch)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source = input_dir / "document.hwp"
    source.write_text("inside", encoding="utf-8")
    outside_payload = tmp_path / "outside-payload"
    outside_payload.write_text("outside", encoding="utf-8")

    from dochan import batch as batch_module

    real_plan_outputs = batch_module._plan_outputs

    def replace_source_after_planning(files, output_root, output_format):
        planned = real_plan_outputs(files, output_root, output_format)
        source.unlink()
        source.symlink_to(outside_payload)
        return planned

    monkeypatch.setattr(batch_module, "_plan_outputs", replace_source_after_planning)

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert summary.total == 1
    assert summary.success == 0
    assert summary.failed == 1
    assert "changed before it could be read" in summary.results[0].errors[0]
    assert outside_payload.read_text(encoding="utf-8") == "outside"
    assert not (output_dir / "document.md").exists()


def test_batch_atomic_publish_failure_preserves_final_and_removes_temp(
    monkeypatch, tmp_path
):
    _install_fake_reader(monkeypatch)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "document.hwp").write_text("replacement", encoding="utf-8")
    final_path = output_dir / "document.md"
    final_path.write_text("previous", encoding="utf-8")
    replace_paths = []

    def fail_replace(source, destination, **kwargs):
        replace_paths.append((Path(source), Path(destination), kwargs))
        raise OSError("publish failed")

    monkeypatch.setattr("dochan.batch.os.replace", fail_replace)

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert summary.failed == 1
    assert summary.success == 0
    assert final_path.read_text(encoding="utf-8") == "previous"
    assert len(replace_paths) == 1
    assert replace_paths[0][0].name.endswith(".tmp")
    assert replace_paths[0][1] == Path("document.md")
    assert replace_paths[0][2]["src_dir_fd"] == replace_paths[0][2]["dst_dir_fd"]
    assert list(output_dir.iterdir()) == [final_path]


def test_atomic_write_rejects_parent_symlink_swap_after_path_checks(
    monkeypatch, tmp_path
):
    output_root = tmp_path / "output"
    nested = output_root / "nested"
    displaced = output_root / "nested-original"
    outside = tmp_path / "outside"
    nested.mkdir(parents=True)
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")

    from dochan import batch as batch_module

    real_assert = batch_module._assert_within_root
    check_count = 0

    def swap_after_second_check(path, root):
        nonlocal check_count
        real_assert(path, root)
        check_count += 1
        if check_count == 2:
            nested.rename(displaced)
            nested.symlink_to(outside, target_is_directory=True)

    monkeypatch.setattr(batch_module, "_assert_within_root", swap_after_second_check)

    with pytest.raises(OSError):
        _atomic_write_text(
            str(nested / "escaped.md"),
            "must not escape",
            allowed_root=str(output_root),
        )

    assert check_count == 2
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert not (outside / "escaped.md").exists()
    assert not (displaced / "escaped.md").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_atomic_write_detects_parent_directory_move_during_replace_and_cleans_publish(
    monkeypatch, tmp_path
):
    output_root = tmp_path / "output"
    nested = output_root / "nested"
    moved_outside = tmp_path / "moved-outside"
    nested.mkdir(parents=True)

    from dochan import batch as batch_module

    real_replace = os.replace

    def move_parent_then_replace(source, destination, **kwargs):
        nested.rename(moved_outside)
        nested.mkdir()
        return real_replace(source, destination, **kwargs)

    monkeypatch.setattr(batch_module.os, "replace", move_parent_then_replace)

    with pytest.raises(OSError, match="directory changed during operation"):
        _atomic_write_text(
            str(nested / "document.md"),
            "must not escape",
            allowed_root=str(output_root),
        )

    assert not (nested / "document.md").exists()
    assert not (moved_outside / "document.md").exists()
    assert not list(tmp_path.rglob("*.tmp"))


def test_atomic_write_restores_existing_target_when_parent_moves_after_publish(
    monkeypatch, tmp_path
):
    output_root = tmp_path / "output"
    nested = output_root / "nested"
    moved_outside = tmp_path / "moved-outside"
    nested.mkdir(parents=True)
    target = nested / "document.md"
    target.write_text("previous", encoding="utf-8")

    from dochan import batch as batch_module

    real_replace = os.replace

    def move_parent_then_replace(source, destination, **kwargs):
        nested.rename(moved_outside)
        nested.mkdir()
        return real_replace(source, destination, **kwargs)

    monkeypatch.setattr(batch_module.os, "replace", move_parent_then_replace)

    with pytest.raises(OSError, match="directory changed during operation"):
        _atomic_write_text(
            str(target),
            "replacement",
            allowed_root=str(output_root),
        )

    assert not (nested / "document.md").exists()
    assert (moved_outside / "document.md").read_text(encoding="utf-8") == "previous"
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.bak"))


def test_atomic_write_rejects_allowed_root_as_the_output_target(tmp_path):
    output_root = tmp_path / "output"
    output_root.mkdir()

    with pytest.raises(ValueError, match="invalid output filename"):
        _atomic_write_text(
            str(output_root),
            "must not become a child file",
            allowed_root=str(output_root),
        )

    assert list(output_root.iterdir()) == []


def test_atomic_write_preserves_existing_target_permission_bits(tmp_path):
    target = tmp_path / "document.md"
    target.write_text("previous", encoding="utf-8")
    target.chmod(0o751)

    _atomic_write_text(str(target), "replacement")

    assert target.read_text(encoding="utf-8") == "replacement"
    assert target.stat().st_mode & 0o777 == 0o751


def test_atomic_write_new_target_uses_normal_umask_mode(tmp_path):
    target = tmp_path / "document.md"
    previous_umask = os.umask(0o022)
    try:
        _atomic_write_text(str(target), "new")
    finally:
        os.umask(previous_umask)

    assert target.stat().st_mode & 0o777 == 0o644


def test_atomic_write_permission_failure_preserves_target_and_removes_temp(
    monkeypatch, tmp_path
):
    target = tmp_path / "document.md"
    target.write_text("previous", encoding="utf-8")
    target.chmod(0o640)

    def fail_fchmod(_fd, _mode):
        raise OSError("permission copy failed")

    monkeypatch.setattr("dochan.batch.os.fchmod", fail_fchmod)

    with pytest.raises(OSError, match="permission copy failed"):
        _atomic_write_text(str(target), "replacement")

    assert target.read_text(encoding="utf-8") == "previous"
    assert target.stat().st_mode & 0o777 == 0o640
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_target_swap_before_backup_leaves_no_recovery_link(
    monkeypatch, tmp_path
):
    target = tmp_path / "document.md"
    target.write_text("previous", encoding="utf-8")
    real_link = os.link
    swapped = False

    def swap_then_link(source, destination, **kwargs):
        nonlocal swapped
        if not swapped:
            swapped = True
            target.unlink()
            target.write_text("concurrent", encoding="utf-8")
        return real_link(source, destination, **kwargs)

    monkeypatch.setattr("dochan.batch.os.link", swap_then_link)

    with pytest.raises(OSError, match="changed before publication"):
        _atomic_write_text(str(target), "replacement")

    assert target.read_text(encoding="utf-8") == "concurrent"
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob("*.bak"))


@pytest.mark.parametrize(
    "parser_errors",
    [
        ["ERR: document body is corrupt"],
        ["ERROR: document body is corrupt"],
        ["[DOCX] ERR: document body is corrupt"],
        ["fatal parse error: document tree is unusable"],
        ["[DOCX] fatal parser failure: document tree is unusable"],
    ],
)
def test_batch_fatal_parser_errors_fail_without_publishing(
    monkeypatch, tmp_path, parser_errors
):
    _install_fake_reader(monkeypatch, parser_errors)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "document.hwp").write_text("partial", encoding="utf-8")

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert summary.total == 1
    assert summary.failed == 1
    assert summary.success == 0
    assert summary.results[0].success is False
    assert summary.results[0].errors == parser_errors
    assert not (output_dir / "document.md").exists()
    assert not list(output_dir.rglob("*.tmp"))


@pytest.mark.parametrize(
    "parser_errors",
    [
        ["WARN: encrypted attachment was skipped"],
        ["WARN: parser wrote to stderr: parse error recovery succeeded"],
        ["[DOCX] WARN: fatal parse error was recovered"],
        ["섹션 2 파싱 실패: truncated section was skipped"],
    ],
)
def test_batch_recoverable_parser_warnings_still_publish(
    monkeypatch, tmp_path, parser_errors
):
    _install_fake_reader(monkeypatch, parser_errors)
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "document.hwp").write_text("recovered", encoding="utf-8")

    summary = batch_convert(
        str(input_dir), str(output_dir), output_format="markdown", max_workers=1
    )

    assert summary.success == 1
    assert summary.failed == 0
    assert summary.results[0].errors == parser_errors
    assert (output_dir / "document.md").read_text(encoding="utf-8") == "recovered"


def test_cli_convert_fatal_parse_error_is_stderr_nonzero_and_not_published(
    monkeypatch, tmp_path, capsys
):
    _install_fake_reader(monkeypatch, ["ERR: unusable document"])
    source = tmp_path / "document.hwp"
    output = tmp_path / "document.md"
    source.write_text("partial", encoding="utf-8")

    exit_code = main(["convert", str(source), "--output", str(output)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "ERR: unusable document" in captured.err
    assert captured.out == ""
    assert not output.exists()


def test_cli_convert_warning_only_is_successful(monkeypatch, tmp_path, capsys):
    _install_fake_reader(monkeypatch, ["WARN: recovered content"])
    source = tmp_path / "document.hwp"
    source.write_text("converted", encoding="utf-8")

    exit_code = main(["convert", str(source)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "converted\n"
    assert "WARN: recovered content" in captured.err


def test_cli_convert_rejects_output_aliasing_input(monkeypatch, tmp_path, capsys):
    _install_fake_reader(monkeypatch)
    source = tmp_path / "document.hwp"
    source.write_text("original", encoding="utf-8")

    exit_code = main(["convert", str(source), "--output", str(source)])

    assert exit_code == 1
    assert source.read_text(encoding="utf-8") == "original"
    assert "aliases a protected input" in capsys.readouterr().err


def test_cli_convert_rejects_output_hardlink_to_input(monkeypatch, tmp_path, capsys):
    _install_fake_reader(monkeypatch)
    source = tmp_path / "document.hwp"
    output = tmp_path / "output.md"
    source.write_text("original", encoding="utf-8")
    os.link(source, output)

    exit_code = main(["convert", str(source), "--output", str(output)])

    assert exit_code == 1
    assert source.read_text(encoding="utf-8") == "original"
    assert "aliases a protected input" in capsys.readouterr().err


def test_cli_info_fatal_parse_error_returns_nonzero(monkeypatch, tmp_path, capsys):
    class FakeDochan:
        def __init__(self, _file_path):
            self.errors = ["ERR: corrupt document"]
            self.metadata = {"source_format": "hwp"}

    monkeypatch.setattr("dochan.reader.Dochan", FakeDochan)
    source = tmp_path / "document.hwp"
    source.write_text("broken", encoding="utf-8")

    exit_code = main(["info", str(source)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ERR: corrupt document" in captured.err


def test_cli_info_unknown_input_reports_unknown_format(monkeypatch, tmp_path, capsys):
    class FakeDochan:
        def __init__(self, _file_path):
            self.errors = ["ERR: unknown input"]
            self.metadata = {}

    monkeypatch.setattr("dochan.reader.Dochan", FakeDochan)
    source = tmp_path / "payload.bin"
    source.write_bytes(b"unknown")

    exit_code = main(["info", str(source)])

    payload = __import__("json").loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["format"] == "unknown"


def test_cli_convert_atomic_publish_failure_preserves_final_and_removes_temp(
    monkeypatch, tmp_path, capsys
):
    _install_fake_reader(monkeypatch)
    source = tmp_path / "document.hwp"
    output = tmp_path / "document.md"
    source.write_text("replacement", encoding="utf-8")
    output.write_text("previous", encoding="utf-8")
    replace_paths = []

    def fail_replace(source_path, destination_path, **kwargs):
        replace_paths.append((Path(source_path), Path(destination_path), kwargs))
        raise OSError("publish failed")

    monkeypatch.setattr("dochan.batch.os.replace", fail_replace)

    exit_code = main(["convert", str(source), "--output", str(output)])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "publish failed" in captured.err
    assert output.read_text(encoding="utf-8") == "previous"
    assert len(replace_paths) == 1
    assert replace_paths[0][0].name.endswith(".tmp")
    assert replace_paths[0][1] == Path("document.md")
    assert replace_paths[0][2]["src_dir_fd"] == replace_paths[0][2]["dst_dir_fd"]
    assert set(tmp_path.iterdir()) == {source, output}


@pytest.mark.parametrize(
    ("failed", "expected_exit"),
    [(0, 0), (1, 1)],
)
def test_cli_batch_exit_reflects_failed_count(
    monkeypatch, tmp_path, capsys, failed, expected_exit
):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    summary = BatchSummary(total=1, success=1 - failed, failed=failed)
    monkeypatch.setattr("dochan.batch.batch_convert", lambda **kwargs: summary)

    exit_code = main(["batch", str(input_dir), str(output_dir)])

    capsys.readouterr()
    assert exit_code == expected_exit


def test_cli_batch_prints_recoverable_warnings(monkeypatch, tmp_path, capsys):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    result = __import__("dochan.batch", fromlist=["BatchResult"]).BatchResult(
        file_path="document.hwp",
        success=True,
        output_path="document.md",
        error_count=1,
        errors=["WARN: recovered optional metadata"],
    )
    summary = BatchSummary(total=1, success=1, failed=0, results=[result])
    monkeypatch.setattr("dochan.batch.batch_convert", lambda **kwargs: summary)

    exit_code = main(["batch", str(input_dir), str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "WARN: recovered optional metadata" in captured.err


def test_batch_rejects_invalid_output_format_before_creating_output(tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    with pytest.raises(ValueError, match="output_format"):
        batch_convert(str(input_dir), str(output_dir), output_format="html")

    assert not output_dir.exists()


def test_batch_rejects_missing_input_before_creating_output(tmp_path):
    input_dir = tmp_path / "missing"
    output_dir = tmp_path / "output"

    with pytest.raises(FileNotFoundError, match="input directory"):
        batch_convert(str(input_dir), str(output_dir))

    assert not output_dir.exists()


@pytest.mark.parametrize("max_workers", [0, -1, 1.5, True])
def test_batch_rejects_invalid_max_workers(tmp_path, max_workers):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    with pytest.raises(ValueError, match="max_workers"):
        batch_convert(str(input_dir), str(output_dir), max_workers=max_workers)

    assert not output_dir.exists()


def test_cli_rejects_non_positive_worker_count(tmp_path, capsys):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        main(["batch", str(input_dir), str(output_dir), "--workers", "0"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "positive" in captured.err.lower()
    assert not output_dir.exists()
