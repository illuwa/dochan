import zipfile
from pathlib import Path

import pytest

from scripts.verify_release_version import (
    VersionVerificationError,
    read_package_version,
    read_pyproject_version,
    read_wheel_version,
    verify_release_versions,
)


def _write_project(
    root: Path, *, project_version: str = "1.2.3", package_version: str = "1.2.3"
) -> None:
    (root / "dochan").mkdir()
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[build-system]",
                'requires = ["setuptools"]',
                "",
                "[project]",
                'name = "dochan"',
                f'version = "{project_version}"',
            ]
        ),
        encoding="utf-8",
    )
    (root / "dochan" / "__init__.py").write_text(
        f'__version__ = "{package_version}"\n',
        encoding="utf-8",
    )


def _write_wheel(path: Path, version: str, *, metadata_members: int = 1) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(metadata_members):
            suffix = "" if index == 0 else f"_{index}"
            archive.writestr(
                f"dochan{suffix}-{version}.dist-info/METADATA",
                f"Metadata-Version: 2.4\nName: dochan\nVersion: {version}\n",
            )


def test_version_readers_do_not_import_the_package(tmp_path):
    _write_project(tmp_path)
    wheel = tmp_path / "dochan-1.2.3-py3-none-any.whl"
    _write_wheel(wheel, "1.2.3")

    assert read_pyproject_version(tmp_path / "pyproject.toml") == "1.2.3"
    assert read_package_version(tmp_path / "dochan" / "__init__.py") == "1.2.3"
    assert read_wheel_version(wheel) == "1.2.3"


def test_verify_release_versions_accepts_exact_tag_source_and_wheel_match(tmp_path):
    _write_project(tmp_path)
    wheel = tmp_path / "dochan-1.2.3-py3-none-any.whl"
    _write_wheel(wheel, "1.2.3")

    versions = verify_release_versions(tmp_path, "v1.2.3", [wheel])

    assert versions == {
        "tag": "1.2.3",
        "pyproject.toml": "1.2.3",
        "dochan/__init__.py": "1.2.3",
        wheel.name: "1.2.3",
    }


@pytest.mark.parametrize(
    ("tag", "project_version", "package_version", "wheel_version", "mismatched_source"),
    [
        ("v9.9.9", "1.2.3", "1.2.3", "1.2.3", "tag"),
        ("v1.2.3", "9.9.9", "1.2.3", "1.2.3", "pyproject.toml"),
        ("v1.2.3", "1.2.3", "9.9.9", "1.2.3", "dochan/__init__.py"),
        ("v1.2.3", "1.2.3", "1.2.3", "9.9.9", "dochan-9.9.9-py3-none-any.whl"),
    ],
)
def test_verify_release_versions_rejects_every_version_mismatch(
    tmp_path,
    tag,
    project_version,
    package_version,
    wheel_version,
    mismatched_source,
):
    _write_project(
        tmp_path, project_version=project_version, package_version=package_version
    )
    wheel = tmp_path / f"dochan-{wheel_version}-py3-none-any.whl"
    _write_wheel(wheel, wheel_version)

    with pytest.raises(VersionVerificationError, match=mismatched_source):
        verify_release_versions(tmp_path, tag, [wheel])


@pytest.mark.parametrize(
    "tag",
    ["1.2.3", "v", "release-v1.2.3", "v1.2.3\n", "v1.2.3+" + "a" * 129],
)
def test_verify_release_versions_rejects_malformed_tags(tmp_path, tag):
    _write_project(tmp_path)
    wheel = tmp_path / "dochan-1.2.3-py3-none-any.whl"
    _write_wheel(wheel, "1.2.3")

    with pytest.raises(VersionVerificationError, match="tag"):
        verify_release_versions(tmp_path, tag, [wheel])


@pytest.mark.parametrize("tag", ["v1.2.3+local", "v1.2.3+linux.x86_64"])
def test_verify_release_versions_rejects_local_version_public_tags(tmp_path, tag):
    _write_project(tmp_path, project_version=tag[1:], package_version=tag[1:])
    wheel = tmp_path / f"dochan-{tag[1:]}-py3-none-any.whl"
    _write_wheel(wheel, tag[1:])

    with pytest.raises(VersionVerificationError, match="public release tag"):
        verify_release_versions(tmp_path, tag, [wheel])


@pytest.mark.parametrize("metadata_members", [0, 2])
def test_read_wheel_version_requires_exactly_one_metadata_member(
    tmp_path, metadata_members
):
    wheel = tmp_path / "dochan-1.2.3-py3-none-any.whl"
    _write_wheel(wheel, "1.2.3", metadata_members=metadata_members)

    with pytest.raises(VersionVerificationError, match="METADATA"):
        read_wheel_version(wheel)
