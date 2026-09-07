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
