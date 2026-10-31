"""Validate release coverage and exercise an installed abi3 wheel in a fresh venv."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import venv
import zipfile


EXTENSIONS = ("_cscan", "_cinterp", "_clines")
TARGETS = {"manylinux_x86_64", "manylinux_aarch64", "macos_arm64", "macos_x86_64"}


def validate_accel_wheel(wheel):
    if "-cp39-abi3-" not in wheel.name:
        raise ValueError(f"Expected cp39-abi3 wheel: {wheel.name}")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for extension in EXTENSIONS:
            if not any(name.startswith(f"dochan/pdf/{extension}.")
                       and name.endswith((".so", ".pyd")) for name in names):
                raise ValueError(f"Missing {extension} in {wheel.name}")


def validate_release(directory):
    wheels = list(directory.glob("*.whl"))
    pure = [wheel for wheel in wheels if wheel.name.endswith("-py3-none-any.whl")]
    if len(pure) != 1 or len(list(directory.glob("*.tar.gz"))) != 1:
        raise ValueError("Expected one pure wheel and one sdist")
    platforms = []
    for wheel in wheels:
        if wheel in pure:
            continue
        validate_accel_wheel(wheel)
        tag = wheel.stem.split("-")[-1]
        target = tag
        for prefix, arches in (("manylinux", ("aarch64", "x86_64")),
                               ("macosx", ("arm64", "x86_64"))):
            for arch in arches:
                if all(part.startswith(prefix) and part.endswith("_" + arch)
                       for part in tag.split(".")):
                    target = ("macos" if prefix == "macosx" else prefix) + "_" + arch
        platforms.append(target)
    if len(platforms) != len(TARGETS) or set(platforms) != TARGETS:
        raise ValueError(f"Unexpected platform coverage: {platforms}")


def _run(args, **kwargs):
    # nosemgrep: dangerous-subprocess-use-audit
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def install_import_guard(site, checkout):
    """Keep subprocess imports on the wheel without preloading loader-test modules."""
    (site / "_dochan_wheel_guard.py").write_text(
        "import importlib.machinery, pathlib, sys\n"
        f"CHECKOUT = pathlib.Path({str(checkout.resolve())!r}) / 'dochan'\n"
        "class WheelFinder:\n"
        "    @staticmethod\n"
        "    def find_spec(fullname, path=None, target=None):\n"
        "        if fullname == 'dochan':\n"
        "            spec = importlib.machinery.PathFinder.find_spec(fullname, path)\n"
        "            if spec is None or spec.origin is None:\n"
        "                return None\n"
        "            if pathlib.Path(spec.origin).resolve().parent != CHECKOUT:\n"
        "                return None\n"
        "            return importlib.machinery.PathFinder.find_spec(\n"
        "                fullname, [str(pathlib.Path(__file__).parent)])\n"
        "sys.meta_path.insert(0, WheelFinder)\n", encoding="utf-8",
    )
    (site / "dochan_wheel_test.pth").write_text(
        "import _dochan_wheel_guard\n", encoding="utf-8",
    )


def verify_installed(wheel, requirements):
    validate_accel_wheel(wheel)
    root = Path(__file__).resolve().parents[1]
    # Some probe tests require the selected tree to contain the imported package.
    # Keep the isolated venv under that tree; the guard still forces wheel imports.
    with tempfile.TemporaryDirectory(prefix=".dochan-wheel-", dir=root) as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # ensurepip in the manylinux images ships pip 23.0.1, which in hash-checking
        # mode does not match pytest-cov's `coverage[toml]` against the pinned
        # `coverage==` line and aborts; pip 25.3 (Python >=3.9) resolves it.
        _run([python, "-m", "pip", "install", "--disable-pip-version-check", "pip==25.3"])
        _run([python, "-m", "pip", "install", "--require-hashes", "-r", requirements])
        _run([python, "-m", "pip", "install", "--no-deps", wheel])
        # The test-only finder also runs in multiprocessing/subprocess children.
        # Merely importing dochan before pytest leaves spawn children on source.
        # Do not preload dochan: loader tests deliberately intercept first import.
        # nosemgrep: dangerous-subprocess-use-audit
        site = subprocess.check_output(
            [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
            text=True,
        ).strip()
        install_import_guard(Path(site), root)
        code = '''
import os, pathlib, sys
import dochan
import dochan.pdf.content as c
location = pathlib.Path(dochan.__file__).resolve()
assert location.is_relative_to(pathlib.Path(sys.prefix).resolve()), location
backends = (c.CONTENT_SCANNER_BACKEND, c.CONTENT_INTERPRETER_BACKEND, c.LINE_ASSEMBLY_BACKEND)
expected = "python" if os.environ.get("DOCHAN_DISABLE_ACCEL") == "1" else "c"
print("Installed:", location, "backends:", backends, flush=True)
assert backends == (expected,) * 3, backends
'''
        for disabled in (False, True):
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env.pop("DOCHAN_DISABLE_ACCEL", None)
            if disabled:
                env["DOCHAN_DISABLE_ACCEL"] = "1"
            _run([python, "-I", "-c", code], cwd=root, env=env)
            _run([python, "-m", "pytest", "tests/", "-q", "-p", "no:cacheprovider"],
                 cwd=root, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--wheel-dir", type=Path)
    group.add_argument("--release-dir", type=Path)
    parser.add_argument("--requirements", type=Path)
    args = parser.parse_args()
    if args.release_dir:
        validate_release(args.release_dir)
    else:
        wheels = list(args.wheel_dir.glob("*.whl"))
        if len(wheels) != 1 or args.requirements is None:
            parser.error("Expected exactly one wheel and --requirements")
        verify_installed(wheels[0].resolve(), args.requirements.resolve())


if __name__ == "__main__":
    main()
