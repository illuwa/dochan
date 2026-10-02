"""링크 진단은 비교 프로브 실패와 누락을 기록하고 다음 문서를 계속 읽는다."""
import json
import sys

import pytest

from scripts.probe_pdf_link_deferrals import main
from test_pdf_structure import _build_pdf, _minimal_objects


@pytest.mark.parametrize('after_result,cause,status,error', [
    ({'error': 'ProbeDeadline'}, 'after_probe_error', 'error', 'ProbeDeadline'),
    (None, 'after_result_missing', 'missing', None),
    ({}, 'after_records_missing', 'missing', None),
    ({'records': []}, 'after_record_missing', 'missing', None),
])
def test_unavailable_after_result_is_reported_and_next_document_continues(
        tmp_path, monkeypatch, after_result, cause, status, error):
    row = {'page': 1, 'annotation_index': 0,
           'status': 'deferred', 'expected': 'ABC'}
    baseline = tmp_path / 'before.json'
    after = tmp_path / 'after.json'
    output = tmp_path / 'diagnosis.json'
    baseline.write_text(json.dumps({'results': {
        'slow.pdf': {'records': [row]}, 'healthy.pdf': {'records': [row]},
    }}))
    results = {'healthy.pdf': {'records': [dict(row, status='match')]}}
    if after_result is not None:
        results['slow.pdf'] = after_result
    after.write_text(json.dumps({'results': results}))
    # The unavailable document must not be reparsed; it can be absent locally.
    content = b'BT /F1 10 Tf 10 10 Td (ABC) Tj ET'
    (tmp_path / 'healthy.pdf').write_bytes(_build_pdf(_minimal_objects(content)))
    if after_result == {'records': []}:
        (tmp_path / 'slow.pdf').write_bytes(_build_pdf(_minimal_objects(content)))
    monkeypatch.setattr(sys, 'argv', [
        'probe_pdf_link_deferrals', str(tmp_path), '--baseline', str(baseline),
        '--after', str(after), '--output', str(output),
    ])

    main()

    report = json.loads(output.read_text())
    unavailable, healthy = report['records']
    assert unavailable == {
        'file': 'slow.pdf', 'page': 1, 'annotation_index': 0,
        'cause': cause, 'after_status': status, 'has_drawn_text': True,
        **({'error': error} if error else {}),
    }
    assert healthy['file'] == 'healthy.pdf'
    assert healthy['cause'] == 'disjoint_same_destination_recovered'
    assert report['summary'] == {cause: 1, 'disjoint_same_destination_recovered': 1}
