"""공개 저장소에 로컬 절대 경로·작업용 임시 경로가 들어가지 않게 막는다."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LOCAL = re.compile(r"/Users/illuwa|/private/tmp/claude-|orca/workspaces/")


def test_tracked_files_have_no_local_absolute_paths():
    files = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    offenders = []
    for name in files:
        if name == "tests/test_no_local_paths.py":
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _LOCAL.search(text):
            offenders.append(name)
    assert offenders == []
