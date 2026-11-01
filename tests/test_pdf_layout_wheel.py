"""The new layout accelerators must be included in ABI3 artifacts."""
import zipfile

import pytest

from scripts.verify_accel_wheel import validate_accel_wheel


@pytest.mark.parametrize('missing', ['_cnotes', '_cheadings', '_cbody'])
def test_layout_wheel_requires_each_module(tmp_path, missing):
    path = tmp_path / 'dochan-1.0-cp39-abi3-macosx_11_0_arm64.whl'
    # Every accelerator the verifier knows about, so the first missing one is `missing`.
    from scripts.verify_accel_wheel import EXTENSIONS
    with zipfile.ZipFile(path, 'w') as archive:
        for name in EXTENSIONS:
            if name != missing:
                package = 'utils' if name in ('_caes', '_cxml') else 'pdf'
                archive.writestr(f'dochan/{package}/{name}.abi3.so', b'test')
    with pytest.raises(ValueError, match=missing):
        validate_accel_wheel(path)
