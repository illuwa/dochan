"""배치 스케줄링의 메모리 상한과 파일별 실패 격리를 검증한다."""

from concurrent.futures import Future
from pathlib import Path
from zipfile import ZipFile

import pytest

import dochan.batch as batch


def _docx(path, text):
    with ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", """<Types
          xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
          <Override PartName="/word/document.xml" ContentType=
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
          </Types>""")
        package.writestr("word/document.xml", """<w:document
          xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body><w:p><w:r><w:t>{}</w:t></w:r></w:p></w:body></w:document>""".format(text))


class _ConsumedFuture(Future):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.consumed = False

    def result(self, *args, **kwargs):
        if not self.consumed:
            self.owner.pending -= 1
            self.consumed = True
        return super().result(*args, **kwargs)


class _Executor:
    def __init__(self, max_workers):
        self.pending = 0
        self.peak = 0
        self.submitted = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def submit(self, function, *args, **kwargs):
        self.pending += 1
        self.peak = max(self.peak, self.pending)
        self.submitted.append(Path(args[0]).name)
        future = _ConsumedFuture(self)
        try:
            if Path(args[0]).name == "timeout.docx":
                raise TimeoutError("synthetic worker timeout")
            future.set_result(function(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future


def _install_executor(monkeypatch):
    executors = []

    def factory(max_workers):
        executor = _Executor(max_workers)
        executors.append(executor)
        return executor

    monkeypatch.setattr(batch, "ProcessPoolExecutor", factory)
    return executors


def test_parallel_submission_is_bounded_and_timeout_does_not_drop_other_files(
    monkeypatch, tmp_path
):
    sources = tmp_path / "input"
    sources.mkdir()
    for index in range(23):
        _docx(sources / ("{:02d}.docx".format(index)), "payload {}".format(index))
    _docx(sources / "timeout.docx", "timeout")
    (sources / "broken.docx").write_bytes(b"PK\x03\x04broken")
    executors = _install_executor(monkeypatch)

    summary = batch.batch_convert(str(sources), str(tmp_path / "out"), max_workers=2)

    assert summary.total == 25
    assert summary.success == 23
    assert summary.failed == 2
    assert len(summary.results) == 25
    assert executors[0].peak <= 8
    assert executors[0].pending == 0
    timeout = next(result for result in summary.results
                   if Path(result.file_path).name == "timeout.docx")
    assert timeout.errors == ["synthetic worker timeout"]
    assert timeout.error_count == 1
    assert not timeout.success


def test_parallel_schedules_large_inputs_first_without_changing_collision_names(
    monkeypatch, tmp_path
):
    sources = tmp_path / "input"
    sources.mkdir()
    _docx(sources / "a.docx", "small")
    _docx(sources / "z.docx", "large " * 1000)
    # 이름 충돌은 크기별 스케줄링 전에 결정해야 한다.
    _docx(sources / "a.hwp", "other")
    serial = batch.batch_convert(str(sources), str(tmp_path / "serial"), max_workers=1)
    executors = _install_executor(monkeypatch)

    parallel = batch.batch_convert(str(sources), str(tmp_path / "parallel"), max_workers=2)

    assert executors[0].submitted[0] == "z.docx"
    assert serial.success == parallel.success == 3
    assert {Path(row.file_path).name: Path(row.output_path).name for row in serial.results} == {
        Path(row.file_path).name: Path(row.output_path).name for row in parallel.results}
    for row in serial.results:
        name = Path(row.output_path).name
        assert (tmp_path / "serial" / name).read_bytes() == (
            tmp_path / "parallel" / name).read_bytes()


@pytest.mark.parametrize("output_format", ["markdown", "json", "text"])
def test_real_parallel_output_and_failed_reports_equal_serial(tmp_path, output_format):
    sources = tmp_path / "input"
    sources.mkdir()
    for index in range(12):
        _docx(sources / ("{}.docx".format(index)), "실제 작업자 {}".format(index))
    (sources / "broken.docx").write_bytes(b"PK\x03\x04broken")
    summaries = []
    for workers in (1, 2):
        output = tmp_path / str(workers)
        summary = batch.batch_convert(str(sources), str(output), output_format,
                                      max_workers=workers)
        records = {}
        for result in summary.results:
            records[Path(result.file_path).name] = (
                result.success, result.error_count, result.errors,
                Path(result.output_path).read_bytes() if result.success else None,
                Path(result.output_path).name if result.success else "")
        summaries.append((summary.total, summary.success, summary.failed, records))
    assert summaries[0] == summaries[1]


def test_empty_parallel_batch_does_not_start_workers(monkeypatch, tmp_path):
    sources = tmp_path / "empty"
    sources.mkdir()
    executors = _install_executor(monkeypatch)
    summary = batch.batch_convert(str(sources), str(tmp_path / "out"), max_workers=4)
    assert summary.total == summary.success == summary.failed == 0
    assert executors == []
