import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from dochan.quality import batch_validate
from dochan.quality.cross_validator import (
    CrossValidationReport,
    PairComparison,
    SourceResult,
)


def _report(file_name="sample.hwpx", *, available=True):
    return CrossValidationReport(
        file_name=file_name,
        sources={"dochan": SourceResult(name="dochan")},
        comparisons=[
            PairComparison(
                source_a="dochan",
                source_b="pdfplumber",
                bigram_similarity=90.0,
                sentence_coverage=80.0,
                word_coverage=85.0,
                length_ratio=97.5,
            )
        ] if available else [],
        overall_score=88.0 if available else 0.0,
        verdict="ok" if available else "검증 불가",
        validation_available=available,
    )


def _install_main_stubs(monkeypatch, reports):
    monkeypatch.setattr(
        batch_validate,
        "find_pairs",
        lambda pairs_dir: [
            {"name": "sample", "pdf": "sample.pdf", "hwpx": "sample.hwpx"}
        ],
    )
    monkeypatch.setattr(
        batch_validate,
        "validate_pair",
        lambda pair, odl_dir: list(reports),
    )


def test_report_json_includes_length_ratio():
    payload = batch_validate._report_to_dict(_report())

    assert payload["comparisons"][0]["length_ratio"] == 97.5


def test_report_json_preserves_metric_availability_and_keyword_counts():
    report = _report()
    report.comparisons[0].available_metrics = ["bigram_similarity", "length_ratio"]
    report.comparisons[0].keyword_matches = 2
    report.comparisons[0].keyword_total = 3

    comparison = batch_validate._report_to_dict(report)["comparisons"][0]

    assert comparison["available_metrics"] == ["bigram_similarity", "length_ratio"]
    assert comparison["keyword_matches"] == 2
    assert comparison["keyword_total"] == 3


def test_report_json_preserves_missing_sentence_evidence():
    report = _report()
    report.missing_in_hwp = ["Critical omitted sentence"]

    payload = batch_validate._report_to_dict(report)

    assert payload["missing_count"] == 1
    assert payload["missing_in_hwp"] == ["Critical omitted sentence"]


def test_run_odl_does_not_reuse_stale_basename_output(
    monkeypatch, tmp_path
):
    pdf = tmp_path / "inputs" / "sample.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"new pdf identity")
    output_dir = tmp_path / "odl"
    output_dir.mkdir()
    (output_dir / "sample.md").write_text("STALE OLD RESULT", encoding="utf-8")
    calls = []

    def convert(*, input_path, output_dir, format, quiet):
        calls.append((input_path, output_dir, format, quiet))
        destination = Path(output_dir) / "sample.md"
        destination.write_text("FRESH RESULT", encoding="utf-8")

    monkeypatch.setitem(
        sys.modules,
        "opendataloader_pdf",
        SimpleNamespace(convert=convert),
    )

    result = batch_validate.run_odl(str(pdf), str(output_dir))

    assert calls
    assert Path(result).read_text(encoding="utf-8") == "FRESH RESULT"
    assert Path(result) != output_dir / "sample.md"


def test_run_odl_does_not_accept_stale_hash_scoped_output(monkeypatch, tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"same pdf identity")
    output_dir = tmp_path / "odl"
    source_digest = batch_validate._file_sha256(str(pdf))[:16]
    stale_dir = output_dir / f"sample-{source_digest}"
    stale_dir.mkdir(parents=True)
    (stale_dir / "sample.md").write_text("STALE", encoding="utf-8")
    calls = []

    def convert(*, input_path, output_dir, format, quiet):
        calls.append((input_path, output_dir, format, quiet))

    monkeypatch.setitem(
        sys.modules,
        "opendataloader_pdf",
        SimpleNamespace(convert=convert),
    )

    result = batch_validate.run_odl(str(pdf), str(output_dir))

    assert calls
    assert result == ""
    assert (stale_dir / "sample.md").read_text(encoding="utf-8") == "STALE"


def test_run_odl_hashes_pdf_without_reading_entire_file(monkeypatch, tmp_path):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"streamed pdf")
    output_dir = tmp_path / "odl"

    def forbidden_read_bytes(self):
        raise AssertionError("Path.read_bytes must not be used")

    def convert(*, input_path, output_dir, format, quiet):
        (Path(output_dir) / "sample.md").write_text("converted", encoding="utf-8")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    monkeypatch.setitem(
        sys.modules,
        "opendataloader_pdf",
        SimpleNamespace(convert=convert),
    )

    result = batch_validate.run_odl(str(pdf), str(output_dir))

    assert Path(result).read_text(encoding="utf-8") == "converted"


def test_run_odl_rejects_oversized_pdf_before_hashing_or_conversion(
    monkeypatch, tmp_path
):
    pdf = tmp_path / "large.pdf"
    pdf.write_bytes(b"1234")
    calls = []
    monkeypatch.setattr(batch_validate, "MAX_REFERENCE_PDF_BYTES", 3)
    monkeypatch.setattr(
        batch_validate,
        "_file_sha256",
        lambda path: (_ for _ in ()).throw(AssertionError("must not hash")),
    )
    monkeypatch.setitem(
        sys.modules,
        "opendataloader_pdf",
        SimpleNamespace(convert=lambda **kwargs: calls.append(kwargs)),
    )

    result = batch_validate.run_odl(str(pdf), str(tmp_path / "odl"))

    assert result == ""
    assert calls == []


def test_find_pairs_rejects_unicode_normalization_collisions(monkeypatch, tmp_path):
    monkeypatch.setattr(
        batch_validate.os,
        "listdir",
        lambda path: ["e\u0301.hwp", "é.hwp", "é.pdf"],
    )

    with pytest.raises(ValueError, match="Unicode-normalized filename collision"):
        batch_validate.find_pairs(str(tmp_path))


def test_run_odl_applies_java_environment_only_during_conversion(
    monkeypatch, tmp_path
):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"pdf")
    output_dir = tmp_path / "odl"
    java_home = "/opt/homebrew/opt/openjdk@17"
    original_java_home = os.environ.get("JAVA_HOME")
    original_path = os.environ.get("PATH")
    real_exists = os.path.exists

    def fake_exists(path):
        if path == java_home:
            return True
        return real_exists(path)

    seen = []

    def convert(*, input_path, output_dir, format, quiet):
        seen.append((os.environ.get("JAVA_HOME"), os.environ.get("PATH")))
        (Path(output_dir) / "sample.md").write_text("converted", encoding="utf-8")

    monkeypatch.setattr(batch_validate.os.path, "exists", fake_exists)
    monkeypatch.setitem(
        sys.modules,
        "opendataloader_pdf",
        SimpleNamespace(convert=convert),
    )

    result = batch_validate.run_odl(str(pdf), str(output_dir))

    assert Path(result).read_text(encoding="utf-8") == "converted"
    assert seen[0][0] == java_home
    assert seen[0][1].split(os.pathsep)[0] == f"{java_home}/bin"
    assert os.environ.get("JAVA_HOME") == original_java_home
    assert os.environ.get("PATH") == original_path


def test_validate_pair_preserves_other_report_when_one_validation_raises(
    monkeypatch, tmp_path
):
    class Validator:
        def validate(self, *, hwpx_path, pdf_path, odl_output_path):
            if hwpx_path.endswith(".hwp"):
                raise RuntimeError("broken hwp")
            return _report(file_name="ignored")

    monkeypatch.setattr(batch_validate, "CrossValidator", Validator)
    monkeypatch.setattr(batch_validate, "run_odl", lambda pdf, output: "")
    pair = {
        "name": "sample",
        "pdf": "sample.pdf",
        "hwp": "sample.hwp",
        "hwpx": "sample.hwpx",
    }

    reports = batch_validate.validate_pair(pair, str(tmp_path))

    assert len(reports) == 2
    failed, succeeded = reports
    assert failed.file_name == "sample.hwp"
    assert failed.validation_available is False
    assert "broken hwp" in failed.sources["dochan"].error
    assert succeeded.file_name == "sample.hwpx"
    assert succeeded.validation_available is True


def test_main_returns_zero_and_cleans_automatic_odl_directory(monkeypatch, tmp_path):
    captured_odl_dirs = []
    monkeypatch.setattr(
        batch_validate,
        "find_pairs",
        lambda pairs_dir: [
            {"name": "sample", "pdf": "sample.pdf", "hwpx": "sample.hwpx"}
        ],
    )

    def validate(pair, odl_dir):
        assert Path(odl_dir).is_dir()
        captured_odl_dirs.append(odl_dir)
        return [_report()]

    monkeypatch.setattr(batch_validate, "validate_pair", validate)

    exit_code = batch_validate.main(["--pairs-dir", str(tmp_path)])

    assert exit_code == 0
    assert len(captured_odl_dirs) == 1
    assert not Path(captured_odl_dirs[0]).exists()


def test_main_returns_nonzero_if_any_validation_is_unavailable(monkeypatch, tmp_path):
    _install_main_stubs(monkeypatch, [_report(), _report("bad.hwp", available=False)])

    exit_code = batch_validate.main(["--pairs-dir", str(tmp_path)])

    assert exit_code != 0


def test_main_aggregates_pair_exceptions_and_continues(monkeypatch, tmp_path, capsys):
    pairs = [
        {"name": "bad", "pdf": "bad.pdf", "hwp": "bad.hwp"},
        {"name": "good", "pdf": "good.pdf", "hwpx": "good.hwpx"},
    ]
    monkeypatch.setattr(batch_validate, "find_pairs", lambda pairs_dir: pairs)
    calls = []

    def validate(pair, odl_dir):
        calls.append(pair["name"])
        if pair["name"] == "bad":
            raise RuntimeError("pair failed")
        return [_report("good.hwpx")]

    monkeypatch.setattr(batch_validate, "validate_pair", validate)

    exit_code = batch_validate.main(["--pairs-dir", str(tmp_path)])

    assert exit_code != 0
    assert calls == ["bad", "good"]
    assert "검증 실패 파일 수: 1개" in capsys.readouterr().out


def test_main_atomically_writes_json_and_preserves_existing_mode(monkeypatch, tmp_path):
    _install_main_stubs(monkeypatch, [_report()])
    output = tmp_path / "report.json"
    output.write_text("old", encoding="utf-8")
    output.chmod(0o640)

    exit_code = batch_validate.main(
        ["--pairs-dir", str(tmp_path), "--output", str(output)]
    )

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))[0]["file_name"] == "sample.hwpx"
    assert output.stat().st_mode & 0o777 == 0o640


def test_main_rejects_report_path_aliasing_an_input(monkeypatch, tmp_path):
    source = tmp_path / "sample.hwpx"
    source.write_bytes(b"original document")
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(
        batch_validate,
        "find_pairs",
        lambda pairs_dir: [
            {"name": "sample", "pdf": str(pdf), "hwpx": str(source)}
        ],
    )
    monkeypatch.setattr(
        batch_validate,
        "validate_pair",
        lambda pair, odl_dir: [_report()],
    )

    exit_code = batch_validate.main(
        ["--pairs-dir", str(tmp_path), "--output", str(source)]
    )

    assert exit_code == 1
    assert source.read_bytes() == b"original document"


def test_main_rejects_report_hardlink_aliasing_an_input(monkeypatch, tmp_path):
    source = tmp_path / "sample.hwpx"
    source.write_bytes(b"original document")
    output = tmp_path / "report.json"
    os.link(source, output)
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"pdf")
    monkeypatch.setattr(
        batch_validate,
        "find_pairs",
        lambda pairs_dir: [
            {"name": "sample", "pdf": str(pdf), "hwpx": str(source)}
        ],
    )
    monkeypatch.setattr(
        batch_validate,
        "validate_pair",
        lambda pair, odl_dir: [_report()],
    )

    exit_code = batch_validate.main(
        ["--pairs-dir", str(tmp_path), "--output", str(output)]
    )

    assert exit_code == 1
    assert source.read_bytes() == b"original document"
    assert output.read_bytes() == b"original document"


def test_main_reports_filename_collision_without_traceback(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        batch_validate,
        "find_pairs",
        lambda pairs_dir: (_ for _ in ()).throw(
            ValueError("Unicode-normalized filename collision")
        ),
    )

    exit_code = batch_validate.main(["--pairs-dir", str(tmp_path)])

    assert exit_code == 1
    assert "입력 쌍 탐색 실패" in capsys.readouterr().err


def test_main_keeps_existing_report_if_atomic_publish_fails(
    monkeypatch, tmp_path
):
    _install_main_stubs(monkeypatch, [_report()])
    output = tmp_path / "report.json"
    output.write_text("old report", encoding="utf-8")
    output.chmod(0o600)

    def fail_replace(*args, **kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("dochan.batch.os.replace", fail_replace)

    exit_code = batch_validate.main(
        ["--pairs-dir", str(tmp_path), "--output", str(output)]
    )

    assert exit_code != 0
    assert output.read_text(encoding="utf-8") == "old report"
    assert output.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".report.json.*.tmp")) == []


def test_main_rejects_symlink_report_target(monkeypatch, tmp_path):
    _install_main_stubs(monkeypatch, [_report()])
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("outside", encoding="utf-8")
    output = tmp_path / "report.json"
    output.symlink_to(outside)

    try:
        exit_code = batch_validate.main(
            ["--pairs-dir", str(tmp_path), "--output", str(output)]
        )

        assert exit_code != 0
        assert output.is_symlink()
        assert outside.read_text(encoding="utf-8") == "outside"
    finally:
        outside.unlink(missing_ok=True)


def test_main_returns_nonzero_when_no_pairs(tmp_path):
    assert batch_validate.main(["--pairs-dir", str(tmp_path)]) != 0


def test_module_entrypoint_propagates_main_exit_code(tmp_path):
    # The executable is the active Python interpreter, argv is fixed, and no shell is used.
    result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
        [
            sys.executable,
            "-m",
            "dochan.quality.batch_validate",
            "--pairs-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "HWP+PDF 쌍을 찾을 수 없습니다." in result.stdout
