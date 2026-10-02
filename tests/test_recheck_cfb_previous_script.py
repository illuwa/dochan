from pathlib import Path

import pytest

from scripts.recheck_cfb_previous import map_previous


def test_previous_cfb_mapping_preserves_old_and_new_ids(tmp_path):
    folder = tmp_path / 'poi-src'
    folder.mkdir()
    sample = folder / 'public.doc'
    sample.write_bytes(b'CFB')
    rows = map_previous([str(sample)], [
        {'id': 12, 'filename': 'public.doc', 'file_size': 3,
         'status': 'reference_only', 'native_reason': 'truncated'},
    ], tmp_path)
    assert rows[12]['new_id'] == 0
    assert rows[12]['file'] == 'corpus/poi-src/public.doc'
    assert rows[12]['prior_native_reason'] == 'truncated'


@pytest.mark.parametrize('copies', [0, 2])
def test_previous_cfb_mapping_refuses_missing_or_ambiguous_identity(tmp_path, copies):
    candidates = []
    for index in range(copies):
        folder = tmp_path / 'poi-src' / str(index)
        folder.mkdir(parents=True)
        sample = folder / 'public.doc'
        sample.write_bytes(b'CFB')
        candidates.append(str(sample))
    with pytest.raises(ValueError, match='unique'):
        map_previous(candidates, [{'id': 12, 'filename': 'public.doc',
                                  'file_size': 3, 'status': 'different'}], tmp_path)


def test_previous_cfb_mapping_refuses_paths_outside_corpus(tmp_path):
    sample = tmp_path / 'public.doc'
    sample.write_bytes(b'CFB')
    with pytest.raises(ValueError):
        map_previous([str(sample)], [{'id': 12, 'filename': 'public.doc',
                                     'file_size': 3, 'status': 'different'}],
                     Path(tmp_path / 'corpus'))


def test_previous_cfb_mapping_refuses_internal_corpus(tmp_path):
    folder = tmp_path / 'local-samples'
    folder.mkdir()
    sample = folder / 'synthetic.doc'
    sample.write_bytes(b'CFB')
    with pytest.raises(ValueError, match='only public'):
        map_previous([str(sample)], [{'id': 12, 'filename': 'synthetic.doc',
                                     'file_size': 3, 'status': 'different'}], tmp_path)


def test_previous_cfb_replay_rejects_internal_roots_before_discovery(tmp_path, monkeypatch):
    import json
    from scripts import recheck_cfb_previous as probe

    previous = tmp_path / 'previous'
    previous.mkdir()
    (previous / 'cfb-discrepancy-classification.json').write_text(json.dumps({'rows': []}))
    (previous / 'cfb-conversion-classification.json').write_text(
        json.dumps({'rows': [], 'roots': [{'root': 'local-samples'}]}))
    monkeypatch.setattr(probe, 'discover_ole', lambda roots: pytest.fail('private root traversed'))
    with pytest.raises(ValueError, match='only public'):
        probe.replay(tmp_path, previous)
