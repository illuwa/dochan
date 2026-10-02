"""Adobe 형식의 합성 텍스트로 생성기 입력과 고지 계약을 검증한다."""
import builtins
import hashlib

import pytest

from scripts.generate_pdf_core14 import generate


def _sources(tmp_path):
    afm = tmp_path / "afm"
    agl = tmp_path / "agl"
    afm.mkdir()
    agl.mkdir()
    names = ["Times-Roman", "Symbol", "ZapfDingbats"] + ["Font%d" % n for n in range(11)]
    for name in names:
        glyph = "a1" if name == "ZapfDingbats" else "A"
        (afm / (name + ".afm")).write_text(
            "FontName %s\nNotice Synthetic copyright\nC 65 ; WX 600 ; N %s ;\n" % (name, glyph)
        )
    (afm / "MustRead.html").write_text("This file and the 14 PostScript synthetic AFM files.")
    (agl / "glyphlist.txt").write_text("# Copyright synthetic Adobe notice\nA;0041\na1;0042\n")
    (agl / "zapfdingbats.txt").write_text("# Copyright synthetic Adobe notice\na1;2701\n")
    (agl / "LICENSE.md").write_text("Synthetic license conditions and disclaimer.\n")
    return afm, agl


def test_generator_reads_adobe_sources_without_fonttools(tmp_path, monkeypatch):
    afm, agl = _sources(tmp_path)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert not name.lower().startswith("fonttools")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    module, notice = generate(afm, agl)
    namespace = {}
    exec(module, namespace)
    assert namespace["GLYPH_UNICODE"] == {"A": "A", "a1": "✁"}
    assert namespace["GLYPH_WIDTHS"]["ZapfDingbats"] == {"a1": 600}
    assert namespace["ENCODINGS"]["ZapfDingbatsEncoding"] == {65: "a1"}
    assert "Synthetic license conditions and disclaimer." in notice
    assert "Copyright synthetic Adobe notice" in notice
    assert "fonttools" not in notice.lower()
    for name in ("glyphlist.txt", "zapfdingbats.txt", "LICENSE.md"):
        assert namespace["AGL_SOURCE_SHA256"][name] == hashlib.sha256((agl / name).read_bytes()).hexdigest()
    assert generate(afm, agl) == (module, notice)


def test_generator_preserves_multi_scalar_agl_entry(tmp_path):
    afm, agl = _sources(tmp_path)
    (agl / "glyphlist.txt").write_text("# Copyright synthetic\nA;0041 0301\n")
    module, _ = generate(afm, agl)
    namespace = {}
    exec(module, namespace)
    assert namespace["GLYPH_UNICODE"]["A"] == "A\u0301"


@pytest.mark.parametrize("entry", ["A;D800", "A;110000", "A;0041\nA;0042", "A;nothex"])
def test_generator_rejects_invalid_adobe_mapping(tmp_path, entry):
    afm, agl = _sources(tmp_path)
    (agl / "glyphlist.txt").write_text(entry + "\n")
    with pytest.raises(ValueError):
        generate(afm, agl)
