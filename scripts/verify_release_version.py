#!/usr/bin/env python3
"""PyPI 릴리스 태그와 소스/휠 버전의 일치를 검증한다."""

from __future__ import annotations

import argparse
import ast
import os
import re
import sys
import zipfile
from collections.abc import Iterable
from email.parser import BytesParser
from pathlib import Path

# The repeated fields are delimiter-separated, so adversarial mismatch scales
# linearly rather than repartitioning nested repetitions.
_TAG_PATTERN = re.compile(  # nosemgrep: regex_dos
    r"v(?P<version>[0-9]+(?:\.[0-9]+){2}"
    r"(?:(?:a|b|rc)[0-9]+|\.post[0-9]+|\.dev[0-9]+)?"
    r")\Z"
)
_PROJECT_SECTION_PATTERN = re.compile(r"^\s*\[project\]\s*(?:#.*)?$")
_SECTION_PATTERN = re.compile(r"^\s*\[[^]]+\]\s*(?:#.*)?$")
_VERSION_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*version\s*=\s*(['\"])(?P<version>[^'\"]+)\1\s*(?:#.*)?$"
)
_MAX_METADATA_BYTES = 1024 * 1024


class VersionVerificationError(ValueError):
    """릴리스 버전을 확정적으로 검증할 수 없을 때 발생한다."""


def read_pyproject_version(path: Path) -> str:
    """`[project].version`을 읽는다.

    Python 3.9에서도 외부 TOML 파서 없이 실행되도록 릴리스에 필요한
    단일 정적 문자열 필드만 엄격히 해석한다.
    """

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise VersionVerificationError(f"cannot read {path}: {exc}") from exc

    in_project_section = False
    versions: list[str] = []
    for line in lines:
        if _PROJECT_SECTION_PATTERN.fullmatch(line):
            in_project_section = True
            continue
        if _SECTION_PATTERN.fullmatch(line):
            in_project_section = False
            continue
        if not in_project_section:
            continue
        match = _VERSION_ASSIGNMENT_PATTERN.fullmatch(line)
        if match:
            versions.append(match.group("version"))

    if len(versions) != 1:
        raise VersionVerificationError(
            f"{path} must contain exactly one static [project].version; found {len(versions)}"
        )
    return versions[0]


def read_package_version(path: Path) -> str:
    """패키지를 import하지 않고 `__version__` 상수를 읽는다."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise VersionVerificationError(f"cannot parse {path}: {exc}") from exc

    versions: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in targets
        ):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            versions.append(value.value)

    if len(versions) != 1:
        raise VersionVerificationError(
            f"{path} must contain exactly one static __version__; found {len(versions)}"
        )
    return versions[0]


def read_wheel_version(path: Path) -> str:
    """휠 내부의 유일한 `.dist-info/METADATA` Version을 읽는다."""

    try:
        with zipfile.ZipFile(path) as archive:
            metadata_members = [
                info
                for info in archive.infolist()
                if info.filename.endswith(".dist-info/METADATA") and not info.is_dir()
            ]
            if len(metadata_members) != 1:
                raise VersionVerificationError(
                    f"{path} must contain exactly one .dist-info/METADATA member; "
                    f"found {len(metadata_members)}"
                )
            member = metadata_members[0]
            if member.file_size > _MAX_METADATA_BYTES:
                raise VersionVerificationError(
                    f"{path} METADATA exceeds {_MAX_METADATA_BYTES} bytes"
                )
            with archive.open(member) as stream:
                metadata = stream.read(_MAX_METADATA_BYTES + 1)
    except VersionVerificationError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise VersionVerificationError(f"cannot read wheel {path}: {exc}") from exc

    if len(metadata) > _MAX_METADATA_BYTES:
        raise VersionVerificationError(
            f"{path} METADATA exceeds {_MAX_METADATA_BYTES} bytes"
        )
    version = BytesParser().parsebytes(metadata).get("Version")
    if not version:
        raise VersionVerificationError(f"{path} METADATA has no Version field")
    return version


def _version_from_tag(tag: str) -> str:
    if len(tag) > 128:
        raise VersionVerificationError("release tag exceeds 128 characters")
    if "+" in tag:
        raise VersionVerificationError(
            "public release tag must not contain a PEP 440 local version"
        )
    match = _TAG_PATTERN.fullmatch(tag)
    if not match:
        raise VersionVerificationError(
            f"tag must use vMAJOR.MINOR.PATCH (optionally with a PEP 440 suffix); got {tag!r}"
        )
    return match.group("version")


def verify_release_versions(
    root: Path, tag: str, wheels: Iterable[Path]
) -> dict[str, str]:
    """태그, 프로젝트, 패키지, 모든 휠의 버전이 정확히 같은지 검증한다."""

    root = root.resolve()
    wheel_paths = [path.resolve() for path in wheels]
    if not wheel_paths:
        raise VersionVerificationError("at least one wheel is required")
    if len({path.name for path in wheel_paths}) != len(wheel_paths):
        raise VersionVerificationError("wheel filenames must be unique")

    versions = {
        "tag": _version_from_tag(tag),
        "pyproject.toml": read_pyproject_version(root / "pyproject.toml"),
        "dochan/__init__.py": read_package_version(root / "dochan" / "__init__.py"),
    }
    for wheel in wheel_paths:
        versions[wheel.name] = read_wheel_version(wheel)

    expected = versions["pyproject.toml"]
    mismatches = [
        f"{source}={version}"
        for source, version in versions.items()
        if version != expected
    ]
    if mismatches:
        details = ", ".join([f"pyproject.toml={expected}", *mismatches])
        raise VersionVerificationError(f"release version mismatch: {details}")
    return versions


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="repository root (default: current directory)",
    )
    parser.add_argument(
        "--tag",
        default=os.environ.get("GITHUB_REF_NAME"),
        help="release tag (default: GITHUB_REF_NAME)",
    )
    parser.add_argument(
        "--wheel", type=Path, nargs="+", required=True, help="built wheel path(s)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.tag:
        print("error: --tag or GITHUB_REF_NAME is required", file=sys.stderr)
        return 2
    try:
        versions = verify_release_versions(args.project_root, args.tag, args.wheel)
    except VersionVerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"verified release version {versions['tag']} across tag, source, and wheel METADATA"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
