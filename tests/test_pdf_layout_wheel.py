"""The new layout accelerators must be included in ABI3 artifacts."""
import zipfile

import pytest

from scripts.verify_accel_wheel import validate_accel_wheel


@pytest.mark.parametrize('missing', ['_cnotes', '_cheadings', '_cbody'])
def test_layout_wheel_requires_each_module(tmp_path, missing):
    path = tmp_path / 'dochan-1.0-cp39-abi3-macosx_11_0_arm64.whl'
    modules = ('_cscan', '_cinterp', '_clines', '_cobjects', '_ccmap',
               '_ctables', '_cnotes', '_cheadings', '_cbody')
    with zipfile.ZipFile(path, 'w') as archive:
        for name in modules:
            if name != missing:
                archive.writestr(f'dochan/pdf/{name}.abi3.so', b'test')
    with pytest.raises(ValueError, match=missing):
        validate_accel_wheel(path)
