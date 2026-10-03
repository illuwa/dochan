"""Public pair selection must follow source provenance, not generated filenames."""

import json

from scripts.probe_hwp_compose_pairs import source_pairs


def test_source_pairs_uses_original_url_and_ignores_same_stem_mismatch(tmp_path):
    hwp = tmp_path / 'hwp'
    hwpx = tmp_path / 'hwpx'
    hwp.mkdir()
    hwpx.mkdir()
    for name in ('from_5.hwp', 'from_7.hwp', 'from_8.hwp'):
        (hwp / name).write_bytes(b'fixture')
    for name in ('from_5.hwpx', 'from_7.hwpx', 'from_11.hwpx'):
        (hwpx / name).write_bytes(b'fixture')
    rows = [
        ('hwp/from_5.hwp', 'compose/from.hwp'),
        ('hwp/from_7.hwp', 'curve/from.hwp'),
        ('hwp/from_8.hwp', 'dutmal/from.hwp'),
        ('hwpx/from_5.hwpx', 'check_button/from.hwpx'),
        ('hwpx/from_7.hwpx', 'compose/from.hwpx'),
        ('hwpx/from_11.hwpx', 'dutmal/from.hwpx'),
    ]
    sources = tmp_path / 'SOURCES.json'
    sources.write_text(json.dumps([
        {'path': path, 'url': 'https://example.org/test/' + url, 'source': 'example'}
        for path, url in rows
    ]), encoding='utf-8')
    pairs = source_pairs(hwp, hwpx, sources)
    assert [(a.name, b.name) for a, b in pairs] == [
        ('from_5.hwp', 'from_7.hwpx'), ('from_8.hwp', 'from_11.hwpx')]


def test_source_pairs_does_not_pair_distinct_download_queries(tmp_path):
    hwp = tmp_path / 'hwp'
    hwpx = tmp_path / 'hwpx'
    hwp.mkdir()
    hwpx.mkdir()
    (hwp / 'a.hwp').write_bytes(b'fixture')
    (hwpx / 'b.hwpx').write_bytes(b'fixture')
    sources = tmp_path / 'SOURCES.json'
    sources.write_text(json.dumps([
        {'path': 'hwp/a.hwp', 'url': 'https://example.org/download?id=1', 'source': 'agency'},
        {'path': 'hwpx/b.hwpx', 'url': 'https://example.org/download?id=2', 'source': 'agency'},
    ]), encoding='utf-8')
    assert source_pairs(hwp, hwpx, sources) == []
