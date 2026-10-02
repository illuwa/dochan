"""합성 증폭 측정 입력이 실제 서식 변화와 본문을 담는지 확인한다."""
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from scripts.benchmark_hwp_runs import prepare


@pytest.mark.parametrize('kind', ['hwp', 'hwpx'])
def test_runs_benchmark_public_api_preserves_text(kind):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
        [sys.executable, str(root / 'scripts/benchmark_hwp_runs.py'),
         '--source-root', str(root), '--format', kind, '--count', '8',
         '--style', 'alternating'],
        check=True, capture_output=True, text=True,
    )
    measured = json.loads(result.stdout)
    assert measured['runs'] == 8
    assert measured['bold_runs'] == 4
    assert measured['model_text_chars'] == 8
    assert measured['markdown_text_chars'] == 8
    assert measured['json_text_chars'] == 16
    assert measured['text_preserved']
    assert measured['errors'] == []
    assert measured['peak_rss_mib'] > 0


def test_hwpx_benchmark_spans_sections_within_existing_element_limit(tmp_path):
    prepare(tmp_path, 'hwpx', 300001, 'alternating')
    with zipfile.ZipFile(tmp_path / 'input.hwpx') as archive:
        sections = [name for name in archive.namelist() if name.startswith('Contents/section')]
        assert len(sections) == 4
        texts = [archive.read(name) for name in sections]
        assert sum(text.count(b'<hp:t>x</hp:t>') for text in texts) == 300001
        assert all(text.count(b'<') < 1_000_000 for text in texts)


@pytest.mark.parametrize('kind,pattern', [
    ('hwp', 'paragraphs'), ('hwpx', 'paragraphs'), ('hwpx', 'notes'), ('hwpx', 'bookmarks'),
])
def test_review_benchmark_patterns_preserve_public_api_text(kind, pattern):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
        [sys.executable, str(root / 'scripts/benchmark_hwp_runs.py'),
         '--source-root', str(root), '--format', kind, '--count', '8', '--pattern', pattern],
        check=True, capture_output=True, text=True,
    )
    measured = json.loads(result.stdout)
    assert measured['text_preserved']
    assert measured['model_text_chars'] == 8
    assert measured['markdown_text_chars'] == 8
    assert measured['json_text_chars'] == 16
    assert measured['errors'] == []
    if pattern == 'notes':
        assert measured['notes'] == 8
    elif pattern == 'paragraphs':
        assert measured['paragraphs'] == 8
