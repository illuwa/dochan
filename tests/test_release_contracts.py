import json
import re
from pathlib import Path

from scripts.verify_release_version import read_package_version, read_pyproject_version


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_declared_python_versions_match_release_matrix():
    project = _read("pyproject.toml")
    workflow = _read(".github/workflows/pypi-release.yml")
    classifiers = re.findall(
        r'"Programming Language :: Python :: (\d+\.\d+)"',
        project,
    )
    matrix_match = re.search(r"python-version:\s*(\[[^\n]+\])", workflow)

    assert matrix_match is not None
    assert json.loads(matrix_match.group(1)) == classifiers


def test_release_versions_and_support_policy_stay_aligned():
    project_version = read_pyproject_version(ROOT / "pyproject.toml")
    package_version = read_package_version(ROOT / "dochan" / "__init__.py")
    readme = _read("README.md")
    security = _read("SECURITY.md")

    assert package_version == project_version
    assert f"Current stable version: {project_version}" in readme
    assert f"| {project_version.split('.', 1)[0]}.x" in security


def test_release_workflow_uses_immutable_actions_and_both_publish_gates():
    workflow = _read(".github/workflows/pypi-release.yml")
    action_references = re.findall(r"^\s*uses:\s*\S+@([^\s#]+)", workflow, re.MULTILINE)

    assert action_references
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_references)
    assert "needs: [test, security]" in workflow
    assert "uv export" in workflow and "--locked" in workflow
    assert (ROOT / "uv.lock").is_file()


def test_default_config_is_declared_as_package_data():
    project = _read("pyproject.toml")
    package_data = re.search(
        r"(?ms)^\[tool\.setuptools\.package-data\]\s*$\s*"
        r"^dochan\s*=\s*(\[[^\n]+\])\s*$",
        project,
    )

    assert (ROOT / "dochan" / "config.yaml").is_file()
    assert package_data is not None
    assert json.loads(package_data.group(1)) == ["config.yaml", "pdf/korean_spacing.json"]
    assert json.loads(_read("dochan/pdf/korean_spacing.json"))["version"] == 1
    # 배포 모델이 실제로 로딩돼야 한다 — 로더는 형식이 어긋나면 조용히 빈 모델로 떨어지므로
    from dochan.pdf.spacing import load_model

    model = load_model(ROOT / "dochan" / "pdf" / "korean_spacing.json")
    assert model.pairs and model.last and model.first


def test_publish_job_smoke_tests_the_installed_wheel_outside_the_checkout():
    workflow = _read(".github/workflows/pypi-release.yml")
    publish_job = workflow.split("\n  publish:\n", 1)[1]

    assert 'artifact_venv="${RUNNER_TEMP}/dochan-artifact-venv"' in publish_job
    assert 'python -m venv "${artifact_venv}"' in publish_job
    assert "uv export" in publish_job
    assert "--locked" in publish_job
    assert "--require-hashes" in publish_job
    assert "--no-deps dist/*.whl" in publish_job
    assert 'cd "${RUNNER_TEMP}"' in publish_job
    assert "env -u PYTHONPATH" in publish_job
    assert "import importlib.metadata" in publish_job
    assert "import importlib.resources" in publish_job
    assert 'joinpath("config.yaml")' in publish_job
    assert "GITHUB_REF_NAME#v" in publish_job
    assert 'bin/dochan" --help' in publish_job
    assert 'bin/dochan" info' in publish_job
    assert 'bin/dochan" convert' in publish_job
    assert "artifact smoke" in publish_job
    assert publish_job.index("Smoke-test installed wheel") < publish_job.index(
        "Publish to PyPI"
    )


def test_documented_commands_do_not_regress_to_broken_paths_or_shell_globs():
    contributing = _read("CONTRIBUTING.md")
    pull_request = _read(".github/pull_request_template.md")
    readme = _read("README.md")
    releasing = _read("RELEASING.md")
    documentation = "\n".join((contributing, pull_request, readme, releasing))

    assert "dochan/tests/" not in documentation
    assert "pip install dochan[ocr]" not in documentation
    assert 'pip install "dochan[ocr]"' in readme
    assert "v1.0.0" not in releasing
    assert (ROOT / "tests").is_dir()


def test_platform_wheels_gate_publication_and_cover_supported_targets():
    workflow = _read(".github/workflows/pypi-release.yml")
    wheels = workflow.split("\n  wheels:\n", 1)[1].split("\n  publish:\n", 1)[0]
    publish = workflow.split("\n  publish:\n", 1)[1]
    assert "needs: [test, security, wheels]" in publish
    assert "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in publish
    assert set(re.findall(r"- target: (\w+)", wheels)) == {
        "manylinux_x86_64", "manylinux_aarch64", "macos_arm64",
        "macos_x86_64",
    }
    assert 'DOCHAN_BUILD_ACCEL: "1"' in wheels
    assert "scripts/verify_accel_wheel.py" in wheels
    assert "auditwheel repair" in wheels
    assert "actions/upload-artifact@" in wheels
    assert publish.index("Download platform wheels") > publish.index(
        "Smoke-test installed wheel outside checkout"
    )
    assert publish.index("Validate all distributions") < publish.index("Publish to PyPI")


def test_platform_wheel_jobs_run_on_pull_requests_with_isolated_builds():
    workflow = _read(".github/workflows/pypi-release.yml")
    assert "  pull_request:" in workflow.split("jobs:", 1)[0]
    for name in ("test", "security", "wheels"):
        job = workflow.split(f"\n  {name}:\n", 1)[1]
        job = re.split(r"\n  \w+:\n", job, maxsplit=1)[0]
        assert not re.search(r"^    if:", job, re.MULTILINE)
    wheels = workflow.split("\n  wheels:\n", 1)[1].split("\n  publish:\n", 1)[0]
    assert "needs: [test, security]" in wheels
    assert wheels.count("python -m build --wheel") == 2
    assert "--no-isolation" not in wheels
    assert "--skip-dependency-check" not in wheels
    assert wheels.count("python scripts/verify_accel_wheel.py") == 2
    assert 'requires = ["setuptools==82.0.1", "wheel==0.48.0"]' in _read("pyproject.toml")


def test_manylinux_build_python_keeps_cp39_abi3_contract():
    workflow = _read(".github/workflows/pypi-release.yml")
    linux = workflow.split("name: Build manylinux wheel", 1)[1].split(
        "name: Build native wheel", 1
    )[0]
    assert "export PATH=/opt/python/cp310-cp310/bin:$PATH" in linux
    assert '"build==1.5.0"' in linux
    assert '"py_limited_api": "cp39"' in _read("setup.py")
    assert '("Py_LIMITED_API", "0x03090000")' in _read("setup.py")
    assert "python scripts/verify_accel_wheel.py" in linux
