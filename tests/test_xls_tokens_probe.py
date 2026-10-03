from scripts.probe_xls_tokens import compare_snapshots, failure_cause


def test_token_cause_uses_diagnostic_not_operand_bytes():
    assert failure_cause(['WARN: XLS formula A1: unsupported or truncated token 0x29; expression omitted']) == 'PtgMemFunc (0x29)'
    assert failure_cause(['WARN: XLS formula DDE/OLE external name is unresolved']) == 'DDE/OLE NameX'
    assert failure_cause([]) == 'no decoder diagnostic'


def test_snapshot_comparison_distinguishes_added_formula_from_cache_regression():
    before = {'files': [{'file': 'sample.xls', 'markdown_sha256': 'old',
                         'json_sha256': 'old', 'cells': [['Sheet1', 'A1', '2'],
                                                     ['Sheet1', 'B1', '3 (=1+2)']]}]}
    after = {'files': [{'file': 'sample.xls', 'markdown_sha256': 'new',
                        'json_sha256': 'new', 'cells': [['Sheet1', 'A1', '2 (=1+1)'],
                                                    ['Sheet1', 'B1', '3 (=1+2)']]}]}
    result = compare_snapshots(before, after)
    assert result['added_formulas'] == 1
    assert result['lost_formulas'] == []
    assert result['changed_existing_formulas'] == []
    assert result['changed_cache_values'] == []
    after['files'][0]['cells'][1][2] = '4'
    result = compare_snapshots(before, after)
    assert len(result['lost_formulas']) == 1
    assert len(result['changed_cache_values']) == 1


def test_probe_restores_reader_hooks_and_hashes_real_serializers(monkeypatch):
    from dochan.model.document import Document
    import dochan.office_binary.xls as xls
    from scripts.probe_xls_tokens import inspect_file

    original = xls._parse_sheet_records
    monkeypatch.setattr(xls.XLSReader, 'read', lambda self, path: Document())
    result = inspect_file('synthetic.xls')
    assert xls._parse_sheet_records is original
    assert len(result['markdown_sha256']) == 64
    assert len(result['json_sha256']) == 64
    assert result['raw_formula_cells'] == 0


def test_formula_presence_keeps_comment_annotations_out_of_omission_count():
    from scripts.probe_xls_tokens import formula_is_rendered
    assert formula_is_rendered('2 (=1+1) [comment: reviewer]', '1+1')
    assert not formula_is_rendered('2 (=1+2) [comment: reviewer]', '1+1')
    assert not formula_is_rendered('2 (=1+1) unexpected suffix', '1+1')
    assert formula_is_rendered('cached (=literal) (=1+1) [comment: reviewer]', '1+1')
    assert not formula_is_rendered('cached (=literal) [comment: reviewer]', '1+1')
    assert not formula_is_rendered('cached [comment: example (=1+1)]', '1+1')
