import json

from scripts.probe_cfb_review import discover_public, compare_runs, damage_evidence, digest, run_one


def test_review_discovery_excludes_private_and_external_symlink(tmp_path):
    public = tmp_path / 'poi-src' / 'test-data' / 'document'
    public.mkdir(parents=True)
    private = tmp_path / 'local-samples'
    private.mkdir()
    magic = bytes.fromhex('d0cf11e0a1b11ae1')
    (public / 'public.doc').write_bytes(magic)
    (private / 'private.doc').write_bytes(magic)
    (public / 'escape.doc').symlink_to(private / 'private.doc')
    assert discover_public(tmp_path) == ['poi-src/test-data/document/public.doc']


def test_review_compare_separates_damage_and_unclassified_changes():
    baseline = {'a.doc': {'hashes': {'errors': 'a', 'markdown': 'x'}},
                'b.doc': {'hashes': {'errors': 'a', 'markdown': 'x'}}}
    current = {'a.doc': {'hashes': {'errors': 'b', 'markdown': 'x'},
                         'damage': ['CFB truncated stream payload']},
               'b.doc': {'hashes': {'errors': 'b', 'markdown': 'x'}, 'damage': []}}
    report = compare_runs(baseline, current)
    assert report['summary']['errors_changed'] == 2
    assert report['summary']['errors_changed_with_damage_evidence'] == 1
    assert report['summary']['errors_changed_without_damage_evidence'] == 1
    assert report['changes'][0]['damage'] == ['CFB truncated stream payload']


def test_review_compare_never_counts_timeout_as_equal():
    result = compare_runs({'a.doc': {'status': 'timeout'}},
                          {'a.doc': {'status': 'timeout'}})
    assert result['summary']['equal'] == 0
    assert result['summary']['unverified'] == 1


def test_review_worker_timeout_is_bounded(tmp_path):
    script = tmp_path / 'slow.py'
    script.write_text('import time; time.sleep(10)')
    result = run_one(str(tmp_path), str(tmp_path / 'a.doc'), 0.05,
                     worker_script=script)
    assert result == {'status': 'timeout'}
    assert 'a.doc' not in json.dumps(result)


def test_review_worker_memory_is_bounded(tmp_path):
    document = tmp_path / 'synthetic.doc'
    document.write_bytes(b'1234')
    assert run_one(tmp_path, document, 10, memory_mb=1) == {'status': 'memory_limit'}


def test_review_damage_evidence_excludes_nonaddressing_metadata():
    benign = [{'code': 'allocation_marker'}, {'code': 'unused_fat_outside'},
              {'code': 'byte_order', 'actual': 65312, 'expected': 65534},
              {'code': 'partial_last_sector', 'bytes': 32},
              {'code': 'chain_length', 'expected': 1, 'actual': 2},
              {'code': 'directory_name_terminator', 'entry': 0}]
    damaged = [{'code': 'chain_length', 'expected': 2, 'actual': 1},
               {'code': 'directory_name_length', 'entry': 3, 'actual': 0}]
    assert damage_evidence(benign + damaged) == damaged


def test_review_worker_imports_requested_tree_and_hashes_all_outputs(tmp_path):
    package = tmp_path / 'dochan'
    package.mkdir()
    (package / '__init__.py').write_text(
        'class Dochan:\n'
        '    def __init__(self, path): self.errors = ["warning"]\n'
        '    def to_markdown(self): return "sentinel markdown"\n'
        '    def to_json(self): return "sentinel json"\n')
    document = tmp_path / 'synthetic.doc'
    document.write_bytes(b'1234')
    result = run_one(tmp_path, document, 10)
    assert result['status'] == 'converted'
    assert result['hashes'] == {'markdown': digest('sentinel markdown'),
                                'json': digest('sentinel json'),
                                'errors': digest('["warning"]')}


def test_opus_sample_keeps_all_office_and_difat_then_seeded_hwp(tmp_path):
    import random
    import struct
    from scripts.probe_cfb_review import discover_opus_sample
    office = tmp_path / 'poi-src/test-data/document'
    hwp = tmp_path / 'hwp-public/hwp'
    office.mkdir(parents=True)
    hwp.mkdir(parents=True)
    header = bytearray(512)
    header[:8] = bytes.fromhex('d0cf11e0a1b11ae1')
    (office / 'sample.doc').write_bytes(header)
    for number in range(5):
        (hwp / ('%d.hwp' % number)).write_bytes(header)
    struct.pack_into('<I', header, 72, 1)
    (hwp / 'difat.hwp').write_bytes(header)
    actual = discover_opus_sample(tmp_path, hwp_count=2)
    expected_hwp = random.Random(4242).sample(
        ['hwp-public/hwp/%d.hwp' % i for i in range(5)], 2)
    assert actual == ['poi-src/test-data/document/sample.doc',
                      'hwp-public/hwp/difat.hwp'] + expected_hwp


def test_explicit_review_paths_reject_private_and_missing_files(tmp_path):
    import pytest
    from scripts.probe_cfb_review import select_paths
    public = tmp_path / 'poi-src/test-data/document'
    public.mkdir(parents=True)
    (public / 'sample.doc').write_bytes(bytes.fromhex('d0cf11e0a1b11ae1'))
    manifest = tmp_path / 'paths.json'
    manifest.write_text(json.dumps(['poi-src/test-data/document/sample.doc']))
    assert select_paths(tmp_path, 'all', manifest) == [
        'poi-src/test-data/document/sample.doc']
    for name in ('local-samples/private.doc', '../outside.doc',
                 'poi-src/test-data/document/missing.doc'):
        manifest.write_text(json.dumps([name]))
        with pytest.raises(ValueError):
            select_paths(tmp_path, 'all', manifest)
