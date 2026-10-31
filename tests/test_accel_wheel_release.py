"""Release checks must reject optional-extension fallback artifacts."""
import zipfile

import pytest

from scripts.verify_accel_wheel import validate_accel_wheel, validate_release


def _wheel(path, extensions=("_cscan", "_cinterp", "_clines")):
    with zipfile.ZipFile(path, "w") as archive:
        for name in extensions:
            archive.writestr(f"dochan/pdf/{name}.abi3.so", b"test")
    return path


def test_accel_wheel_requires_all_three_extensions(tmp_path):
    wheel = _wheel(tmp_path / "dochan-1.15.0-cp39-abi3-macosx_11_0_arm64.whl")
    validate_accel_wheel(wheel)
    _wheel(wheel, ("_cscan", "_cinterp"))
    with pytest.raises(ValueError, match="_clines"):
        validate_accel_wheel(wheel)


def test_accel_wheel_rejects_wrong_abi(tmp_path):
    wheel = _wheel(tmp_path / "dochan-1.15.0-cp313-cp313-win_amd64.whl")
    with pytest.raises(ValueError, match="cp39-abi3"):
        validate_accel_wheel(wheel)


def test_release_requires_exactly_four_platforms_and_pure_fallback(tmp_path):
    targets = ["manylinux2014_x86_64", "manylinux2014_aarch64",
               "macosx_11_0_arm64", "macosx_10_13_x86_64"]
    for target in targets:
        _wheel(tmp_path / f"dochan-1.15.0-cp39-abi3-{target}.whl")
    _wheel(tmp_path / "dochan-1.15.0-py3-none-any.whl", ())
    (tmp_path / "dochan-1.15.0.tar.gz").touch()
    validate_release(tmp_path)
    (tmp_path / "dochan-1.15.0-cp39-abi3-macosx_10_13_x86_64.whl").unlink()
    with pytest.raises(ValueError, match="platform"):
        validate_release(tmp_path)


def test_wheel_import_guard_ignores_checkout_without_preloading(tmp_path):
    import os
    import subprocess
    import sys
    from scripts.verify_accel_wheel import install_import_guard

    site = tmp_path / "site"
    checkout = tmp_path / "checkout"
    for parent in (site, checkout):
        (parent / "dochan").mkdir(parents=True)
    (site / "dochan" / "__init__.py").write_text("origin = 'wheel'\n")
    (checkout / "dochan" / "__init__.py").write_text("raise RuntimeError('checkout shadow')\n")
    code = (
        "import sys; sys.path.append(sys.argv[1]); "
        "import _dochan_wheel_guard; assert 'dochan' not in sys.modules; "
        "import dochan; assert dochan.origin == 'wheel'"
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    (site / "_dochan_wheel_guard.py").write_text("# defective empty guard\n")
    with pytest.raises(subprocess.CalledProcessError) as failure:
        subprocess.run([sys.executable, "-S", "-c", code, str(site)], cwd=checkout,  # nosemgrep: dangerous-subprocess-use-audit
                       env=env, check=True, capture_output=True)
    assert "checkout shadow" in failure.value.stderr.decode()
    install_import_guard(site, checkout)
    subprocess.run([sys.executable, "-S", "-c", code, str(site)], cwd=checkout,  # nosemgrep: dangerous-subprocess-use-audit
                   env=env, check=True, capture_output=True)


def test_release_does_not_mistake_another_linux_arch_for_x86_64(tmp_path):
    targets = ["manylinux2014_ppc64le", "manylinux2014_aarch64",
               "macosx_11_0_arm64", "macosx_10_13_x86_64"]
    for target in targets:
        _wheel(tmp_path / f"dochan-1.15.0-cp39-abi3-{target}.whl")
    _wheel(tmp_path / "dochan-1.15.0-py3-none-any.whl", ())
    (tmp_path / "dochan-1.15.0.tar.gz").touch()
    with pytest.raises(ValueError, match="platform"):
        validate_release(tmp_path)
