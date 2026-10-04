import json
import logging
from pathlib import Path

import pytest

from scripts.probe_speed_batch import compare_records, measure, select_sample


def test_seeded_sample_uses_only_public_roots_and_skips_links(tmp_path):
    public = tmp_path / "poi-src/test-data/document"
    public.mkdir(parents=True)
    for index in range(5):
        (public / ("{}.docx".format(index))).write_bytes(b"public")
    private = tmp_path / "local-samples"
    private.mkdir()
    (private / "private.docx").write_bytes(b"private")
    (public / "linked.docx").symlink_to(private / "private.docx")
    first = select_sample(tmp_path, {"docx": 3}, 42)
    assert first == select_sample(tmp_path, {"docx": 3}, 42)
    assert len(first) == 3
    assert all(name.startswith("poi-src/test-data/document/") for name in first)
    assert all("linked" not in name for name in first)
    with pytest.raises(ValueError, match="available 5"):
        select_sample(tmp_path, {"docx": 6}, 42)


def test_hash_comparison_also_detects_warnings_failures_and_missing_results():
    reference = {"ok": {"sha256": "same", "success": True, "errors": []},
                 "bad": {"sha256": None, "success": False, "errors": ["error"]}}
    assert compare_records(reference, reference)["identical"] == 2
    changed = json.loads(json.dumps(reference))
    changed["ok"]["errors"].append("new warning")
    del changed["bad"]
    assert compare_records(reference, changed)["mismatches"] == ["bad", "ok"]


def test_probe_cleans_outputs_and_keeps_hashes_for_real_conversion(tmp_path):
    from test_batch_speed import _docx

    corpus = tmp_path / "corpus"
    public = corpus / "poi-src/test-data/document"
    public.mkdir(parents=True)
    _docx(public / "sample.docx", "probe")
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    selected = ["poi-src/test-data/document/sample.docx"]
    logger = logging.getLogger("dochan")
    previous_level = logger.level
    try:
        row = measure(corpus, temporary, selected, 1, "markdown")
    finally:
        logger.setLevel(previous_level)
    assert row["success"] == row["total"] == 1
    assert row["records"][selected[0]]["bytes"] == len(b"probe")
    assert len(row["records"][selected[0]]["sha256"]) == 64
    assert list(temporary.iterdir()) == []
    assert not Path(row["records"][selected[0]]["output_path"]).is_absolute()
