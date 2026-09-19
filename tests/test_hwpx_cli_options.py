"""CLI/batch option forwarding, output safety, and optional public corpus checks."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from dochan import Dochan
from dochan.batch import batch_convert
from dochan.cli import main


ROOT = Path(__file__).resolve().parents[1]
NS = (
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'
)
OPTIONS = [
    (["--no-assets"], {"include_assets": False}),
    (["--revision-mode", "final"], {"revision_mode": "final"}),
    (["--revision-mode", "original"], {"revision_mode": "original"}),
    (["--no-assets", "--revision-mode", "final"],
     {"include_assets": False, "revision_mode": "final"}),
]


def make_hwpx(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", (
            f'<hh:head {NS}><hh:refList><hh:trackChanges>'
            '<hh:trackChange id="1" type="Insert"/>'
            '<hh:trackChange id="2" type="Delete"/>'
            '</hh:trackChanges></hh:refList></hh:head>'
        ))
        archive.writestr("Contents/section0.xml", (
            f'<hs:sec {NS}><hp:p><hp:run><hp:t>기본'
            '<hp:deleteBegin Id="2" TcId="2"/> 삭제'
            '<hp:deleteEnd Id="2" TcId="2" paraend="0"/>'
            '<hp:insertBegin Id="1" TcId="1"/> 삽입'
            '<hp:insertEnd Id="1" TcId="1" paraend="0"/>'
            '</hp:t><hp:pic><hc:img binaryItemIDRef="photo"/>'
            '<hp:shapeComment>그림 설명</hp:shapeComment>'
            '</hp:pic></hp:run></hp:p></hs:sec>'
        ))
        archive.writestr("BinData/photo.png", b"\x89PNG\r\n\x1a\npicture")
    return path


def make_docx(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>다른 형식</w:t></w:r></w:p></w:body></w:document>'
        ))
    return path


@pytest.fixture
def source(tmp_path):
    return make_hwpx(tmp_path / "input" / "sample.hwpx")


def render(reader, output_format):
    return getattr(reader, {
        "markdown": "to_markdown", "text": "to_plain_text", "json": "to_json",
    }[output_format])()


@pytest.mark.parametrize("command", ["convert", "batch"])
def test_help_describes_hwpx_options(command, capsys):
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "--no-assets" in help_text
    assert "--revision-mode {preserve,final,original}" in help_text
    assert "HWPX" in help_text


@pytest.mark.parametrize("mode", ["preserve", "final", "original"])
@pytest.mark.parametrize("no_assets", [False, True])
@pytest.mark.parametrize("output_format", ["markdown", "json", "text"])
def test_convert_matches_reader(source, capsys, mode, no_assets, output_format):
    args = ["convert", str(source), "--format", output_format, "--revision-mode", mode]
    if no_assets:
        args.append("--no-assets")
    expected = Dochan(source, include_assets=not no_assets, revision_mode=mode)
    assert expected.errors == []

    assert main(args) == 0
    captured = capsys.readouterr()
    assert captured.out == render(expected, output_format) + "\n"
    assert captured.err == ""


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("flags, options", OPTIONS)
def test_batch_matches_reader_including_parallel_snapshots(source, tmp_path, workers, flags, options):
    # A renamed HWPX must follow the reader's package-identity contract too.
    renamed = source.with_name("renamed.pdf")
    renamed.write_bytes(source.read_bytes())
    output = tmp_path / "output"
    assert main([
        "batch", str(source.parent), str(output), "--format", "json",
        "--workers", str(workers), *flags,
    ]) == 0
    expected = Dochan(source, **options).to_dict()
    assert json.loads((output / "sample.json").read_text()) == expected
    assert json.loads((output / "renamed.json").read_text()) == expected


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("flags, options", OPTIONS)
def test_mixed_batch_reports_failure_and_preserves_failed_output(
    source, tmp_path, workers, flags, options,
):
    other = make_docx(source.with_name("other.docx"))
    original_bytes = other.read_bytes()
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "other.md"
    existing.write_text("KEEP")

    result = cli_process(
        "batch", str(source.parent), str(output), "--workers", str(workers), *flags,
    )
    assert result.returncode == 1
    assert "1/2" in result.stdout
    assert str(other) in result.stderr
    assert "only for HWPX" in result.stderr
    assert existing.read_text() == "KEEP"
    assert other.read_bytes() == original_bytes
    assert (output / "sample.md").read_text() == Dochan(source, **options).to_markdown()
    assert sorted(p.name for p in output.iterdir()) == ["other.md", "sample.md"]


@pytest.mark.parametrize("flags, options", OPTIONS)
def test_batch_api_failed_results_are_explicit(source, tmp_path, flags, options):
    other = make_docx(source.with_name("other.hwpx"))
    output = tmp_path / "output"
    summary = batch_convert(str(source.parent), str(output), max_workers=1, **options)
    assert (summary.total, summary.success, summary.failed) == (2, 1, 1)
    failed = next(result for result in summary.results if not result.success)
    assert failed.file_path == str(other)
    assert failed.output_path == ""
    assert failed.error_count == 1
    assert "only for HWPX" in failed.errors[0]
    assert not (output / "other.md").exists()


@pytest.mark.parametrize("flags, options", OPTIONS)
def test_convert_rejects_other_package_without_publishing(tmp_path, capsys, flags, options):
    source = make_docx(tmp_path / "disguised.hwpx")
    output = tmp_path / "output.md"
    output.write_text("KEEP")
    assert main(["convert", str(source), "-o", str(output), *flags]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "only for HWPX" in captured.err
    assert output.read_text() == "KEEP"


@pytest.mark.parametrize("flags", [[], ["--revision-mode", "preserve"]])
def test_default_convert_and_mixed_batch_accept_other_formats(source, tmp_path, capsys, flags):
    other = make_docx(source.with_name("other.docx"))
    assert main(["convert", str(other), "--format", "text", *flags]) == 0
    assert capsys.readouterr().out == "다른 형식\n"
    assert main([
        "batch", str(source.parent), str(tmp_path / "output"), "--workers", "1", *flags,
    ]) == 0
    assert "2/2" in capsys.readouterr().out


def test_default_batch_keeps_path_only_reader_call(source, tmp_path, monkeypatch):
    class LegacyReader:
        def __init__(self, path):
            self.errors = []

        def to_markdown(self):
            return "legacy"

    monkeypatch.setattr("dochan.reader.Dochan", LegacyReader)
    summary = batch_convert(
        str(source.parent), str(tmp_path / "output"), max_workers=1,
        include_assets=True, revision_mode="preserve",
    )
    assert (summary.success, summary.failed) == (1, 0)


def test_no_assets_with_ocr_fails_without_touching_output(source, tmp_path, capsys):
    output = tmp_path / "output.md"
    output.write_text("KEEP")
    assert main(["convert", str(source), "--no-assets", "--ocr", "-o", str(output)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ocr=True cannot be used with include_assets=False" in captured.err
    assert output.read_text() == "KEEP"


@pytest.mark.parametrize("flags, options", OPTIONS)
def test_option_convert_retains_source_alias_protection(source, capsys, flags, options):
    before = source.read_bytes()
    assert main(["convert", str(source), "-o", str(source), *flags]) == 1
    assert capsys.readouterr().out == ""
    assert source.read_bytes() == before


@pytest.mark.parametrize("command", ["convert", "batch"])
def test_invalid_cli_revision_is_usage_error_before_output(source, tmp_path, command):
    output = tmp_path / "output"
    args = (["convert", str(source), "-o", str(output)] if command == "convert"
            else ["batch", str(source.parent), str(output)])
    with pytest.raises(SystemExit) as exc:
        main([*args, "--revision-mode", "invalid"])
    assert exc.value.code == 2
    assert not output.exists()


def test_batch_api_invalid_revision_fails_even_for_empty_input(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="revision_mode"):
        batch_convert(str(source), str(output), revision_mode="invalid")
    assert not output.exists()


def public_sample(name, sha256):
    path = ROOT / "corpus/hwp-public/hwpx" / name
    if not path.exists():
        pytest.skip("Optional public HWPX corpus is not installed")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha256
    return path


def cli_process(*args):
    # Fixed interpreter/module, test-owned argv, no shell or document-sourced command.
    return subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
        [sys.executable, "-m", "dochan.cli", *map(str, args)],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )


def make_partial_hwpx(path, problem):
    paragraph = lambda text: f'<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>'
    begin = '<hp:deleteBegin Id="d" TcId="2"/>'
    end = '<hp:deleteEnd Id="d" TcId="2" paraend="0"/>'
    changes = '<hh:trackChange id="2" type="Delete"/>'
    if problem == "formatting":
        changes += '<hh:trackChange id="3" type="ParaShape"/>'
        body = paragraph("BODYKEEP")
    elif problem == "missing-end":
        body = paragraph(begin + "BODYKEEP")
    else:
        body = ('<hp:p><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList>'
                + begin + paragraph("CELL")
                + '</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>'
                + paragraph("BODY" + end + "KEEP"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/header.xml", f'<hh:head {NS}>{changes}</hh:head>')
        archive.writestr("Contents/section0.xml", f'<hs:sec {NS}>{body}</hs:sec>')
    return path


@pytest.mark.parametrize("problem", ["formatting", "missing-end", "malformed-flow"])
@pytest.mark.parametrize("flags, success", [
    ([], True), (["--revision-mode", "preserve"], True),
    (["--revision-mode", "final"], False), (["--revision-mode", "original"], False),
])
@pytest.mark.parametrize("command", ["convert", "batch"])
def test_partial_revision_cli_severity_and_output(tmp_path, problem, flags, success, command):
    source = make_partial_hwpx(tmp_path / "input" / "partial.hwpx", problem)
    original_bytes = source.read_bytes()
    output = tmp_path / "output"
    output.mkdir()
    destination = output / "partial.txt"
    destination.write_text("EXISTING")
    if command == "convert":
        args = ["convert", source, "-o", destination]
    else:
        args = ["batch", source.parent, output, "--workers", "1"]
    result = cli_process(*args, "--format", "text", *flags)
    assert result.returncode == (0 if success else 1), result.stderr
    assert ("WARN: HWPX revision partial" if success else "ERR: HWPX revision partial") in result.stderr
    if success:
        assert "BODYKEEP" in destination.read_text()
        if problem == "malformed-flow":
            assert "CELL" in destination.read_text()
    else:
        assert destination.read_text() == "EXISTING"
        if command == "convert":
            assert result.stdout == ""
    assert source.read_bytes() == original_bytes


@pytest.mark.parametrize("flags, success", [
    ([], True), (["--revision-mode", "preserve"], True),
    (["--revision-mode", "final"], False), (["--revision-mode", "original"], False),
])
def test_public_complex_revision_cli_preserves_or_fails_explicitly(flags, success):
    source = public_sample(
        "admrul-관세조사-운영-훈령.hwpx",
        "27c559e41150a166213dffb33d2e496e6cc4d50d18a6fc159c4fe77eacf5dff8",
    )
    result = cli_process("convert", source, "--format", "text", *flags)
    assert result.returncode == (0 if success else 1), result.stderr
    if success:
        reader = Dochan(source)
        assert result.stdout == reader.to_plain_text() + "\n"
        paragraphs = reader.find_all("paragraph")
        assert len(paragraphs) == 3654
        assert sum(len(p.text) for p in paragraphs) == 102740
        assert "WARN: HWPX revision partial" in result.stderr
        assert "ERR:" not in result.stderr
    else:
        assert result.stdout == ""
        assert "ERR: HWPX revision partial" in result.stderr


@pytest.mark.parametrize("mode, expected", [
    ("preserve", "변경 추적 \t인간은"),
    ("final", "변경 \t인간은"),
    ("original", "변경 추적 \t"),
])
def test_public_changetrack_cli_matches_independent_xml_gold(mode, expected):
    # Independently derived from Contents/section0.xml; see revision-spec.md.
    source = public_sample(
        "hwpxlib-ChangeTrack.hwpx",
        "05e6384795611406b29302cf62326b6d1f0a9399d2fbc201fcbe459aa730e356",
    )
    result = cli_process("convert", source, "--format", "json", "--revision-mode", mode)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    document = json.loads(result.stdout)
    paragraphs = [e["text"] for s in document["sections"] for e in s["elements"]
                  if e["type"] == "paragraph"]
    assert paragraphs == [expected]


def assert_no_asset_reads(source, monkeypatch):
    loaded = Dochan(source)
    assert any(image.has_data for image in loaded.find_all("image"))
    for image in loaded.find_all("image"):
        image.image_data = b""
    original_open = zipfile.ZipFile.open

    def guard(archive, name, *args, **kwargs):
        filename = name.filename if isinstance(name, zipfile.ZipInfo) else name
        assert not filename.startswith("BinData/"), filename
        return original_open(archive, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", guard)
    skipped = Dochan(source, include_assets=False)
    assert loaded.doc == skipped.doc
    assert skipped.errors == []
    return skipped


@pytest.mark.parametrize("command", ["convert", "batch"])
def test_no_assets_cli_and_api_never_open_image_data(source, tmp_path, monkeypatch, capsys, command):
    skipped = assert_no_asset_reads(source, monkeypatch)
    if command == "convert":
        assert main(["convert", str(source), "--no-assets", "--format", "json"]) == 0
        actual = json.loads(capsys.readouterr().out)
    else:
        output = tmp_path / "output"
        assert main([
            "batch", str(source.parent), str(output), "--no-assets", "--format", "json",
            "--workers", "1",
        ]) == 0
        actual = json.loads((output / "sample.json").read_text())
    assert actual == skipped.to_dict()


def test_public_image_no_assets_cli_matches_api_without_binary_reads(monkeypatch, capsys):
    source = public_sample(
        "hwpxlib-SimplePicture.hwpx",
        "7ed3bdf89986fd88fdbcd92eaeac3f852aa6984fb1f7ddf4dd4f582afe20084c",
    )
    skipped = assert_no_asset_reads(source, monkeypatch)
    assert main(["convert", str(source), "--no-assets", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out) == skipped.to_dict()
    for output_format in ("json", "markdown", "text"):
        result = cli_process("convert", source, "--no-assets", "--format", output_format)
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        assert result.stdout == render(skipped, output_format) + "\n"
