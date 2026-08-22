"""
batch.py — 배치 처리
다수 HWP 파일의 병렬 변환
"""

import os
import logging
import secrets
import stat
import tempfile
import unicodedata
from contextlib import contextmanager
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from .utils.diagnostics import is_fatal_diagnostic

logger = logging.getLogger('dochan')

_OUTPUT_EXTENSIONS = {
    'markdown': '.md',
    'json': '.json',
    'text': '.txt',
}
MAX_BATCH_SOURCE_SIZE = 512 * 1024 * 1024

_DIRECTORY_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, 'O_DIRECTORY', 0)
    | getattr(os, 'O_CLOEXEC', 0)
    | getattr(os, 'O_NOFOLLOW', 0)
)
_SOURCE_OPEN_FLAGS = (
    os.O_RDONLY
    | getattr(os, 'O_CLOEXEC', 0)
    | getattr(os, 'O_NOFOLLOW', 0)
)
_HAS_DESCRIPTOR_WALK = (
    os.open in os.supports_dir_fd
    and os.stat in os.supports_dir_fd
    and os.scandir in os.supports_fd
)


@dataclass(frozen=True)
class _SourceIdentity:
    """Identity captured while a source is still linked below the input root."""

    root_device: int
    root_inode: int
    source_device: int
    source_inode: int
    source_mode: int
    source_size: int
    source_mtime_ns: int
    source_ctime_ns: int


def _object_identity(value: os.stat_result) -> Tuple[int, int]:
    return value.st_dev, value.st_ino


def _source_identity(
    root_stat: os.stat_result,
    source_stat: os.stat_result,
) -> _SourceIdentity:
    return _SourceIdentity(
        root_device=root_stat.st_dev,
        root_inode=root_stat.st_ino,
        source_device=source_stat.st_dev,
        source_inode=source_stat.st_ino,
        source_mode=source_stat.st_mode,
        source_size=source_stat.st_size,
        source_mtime_ns=source_stat.st_mtime_ns,
        source_ctime_ns=source_stat.st_ctime_ns,
    )


def _source_stat_matches(
    actual: os.stat_result,
    expected: _SourceIdentity,
) -> bool:
    return (
        actual.st_dev == expected.source_device
        and actual.st_ino == expected.source_inode
        and actual.st_mode == expected.source_mode
        and actual.st_size == expected.source_size
        and actual.st_mtime_ns == expected.source_mtime_ns
        and actual.st_ctime_ns == expected.source_ctime_ns
    )


def _validate_relative_path(relative_path: Path, label: str) -> Tuple[str, ...]:
    parts = relative_path.parts
    if (
        relative_path.is_absolute()
        or not parts
        or any(part in {'', '.', '..'} for part in parts)
    ):
        raise ValueError(f"invalid {label} path: {relative_path!s}")
    return parts


def _verify_root_identity(
    root_path: Path,
    root_fd: int,
    expected: Optional[Tuple[int, int]] = None,
) -> os.stat_result:
    """Ensure a pinned root descriptor is still named by ``root_path``."""
    descriptor_stat = os.fstat(root_fd)
    path_stat = os.stat(root_path, follow_symlinks=False)
    if not stat.S_ISDIR(descriptor_stat.st_mode) or not stat.S_ISDIR(path_stat.st_mode):
        raise OSError(f"root path is not a directory: {root_path}")
    if _object_identity(descriptor_stat) != _object_identity(path_stat):
        raise OSError(f"root directory changed during operation: {root_path}")
    if expected is not None and _object_identity(descriptor_stat) != expected:
        raise OSError(f"root directory identity changed: {root_path}")
    return descriptor_stat


def _verify_directory_link(parent_fd: int, name: str, child_fd: int) -> None:
    """Ensure the open child directory is still linked from its parent."""
    child_stat = os.fstat(child_fd)
    linked_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISDIR(child_stat.st_mode)
        or not stat.S_ISDIR(linked_stat.st_mode)
        or _object_identity(child_stat) != _object_identity(linked_stat)
    ):
        raise OSError(f"directory changed during operation: {name}")


def _verify_directory_chain(
    root_path: Path,
    root_fd: int,
    links: Sequence[Tuple[int, str, int]],
    expected_root: Optional[Tuple[int, int]] = None,
) -> None:
    _verify_root_identity(root_path, root_fd, expected_root)
    for parent_fd, name, child_fd in links:
        _verify_directory_link(parent_fd, name, child_fd)

@dataclass
class BatchResult:
    """단일 파일 처리 결과"""
    file_path: str = ""
    success: bool = False
    output_path: str = ""
    error_count: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class BatchSummary:
    """배치 처리 전체 요약"""
    total: int = 0
    success: int = 0
    failed: int = 0
    results: List[BatchResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.success / max(self.total, 1) * 100


def _is_fatal_parser_error(error: str) -> bool:
    """Return whether a parser diagnostic makes the conversion unusable."""
    return is_fatal_diagnostic(error)


def _assert_within_root(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"output path escapes output directory: {path}") from exc


def _nested_output_relative(
    input_root: Path,
    output_root: Path,
) -> Optional[Path]:
    if output_root == input_root:
        return None
    try:
        return output_root.relative_to(input_root)
    except ValueError:
        return None


def _collect_sources_descriptor(
    input_root: Path,
    output_root: Path,
    extensions: Tuple[str, ...],
) -> List[Tuple[Path, Path, _SourceIdentity]]:
    """Collect regular files through directory descriptors without following links."""
    root_fd = os.open(str(input_root), _DIRECTORY_OPEN_FLAGS)
    output_relative = _nested_output_relative(input_root, output_root)
    collected: List[Tuple[Path, Path, _SourceIdentity]] = []

    try:
        root_stat = _verify_root_identity(input_root, root_fd)
        root_identity = _object_identity(root_stat)

        def visit(directory_fd: int, relative_dir: Path) -> None:
            with os.scandir(directory_fd) as iterator:
                entries = sorted(iterator, key=lambda entry: _path_key(Path(entry.name)))

            for entry in entries:
                name = entry.name
                if name in {'', '.', '..'} or os.sep in name:
                    raise OSError(f"invalid input directory entry: {name!r}")
                relative = relative_dir / name

                try:
                    linked_stat = os.stat(
                        name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    raise OSError(f"input entry changed during collection: {relative}")

                if stat.S_ISLNK(linked_stat.st_mode):
                    logger.warning(f"심볼릭 링크 입력 건너뜀: {input_root / relative}")
                    continue

                if stat.S_ISDIR(linked_stat.st_mode):
                    if output_relative is not None and relative == output_relative:
                        continue
                    child_fd = os.open(name, _DIRECTORY_OPEN_FLAGS, dir_fd=directory_fd)
                    try:
                        child_stat = os.fstat(child_fd)
                        if _object_identity(child_stat) != _object_identity(linked_stat):
                            raise OSError(
                                f"input directory changed during collection: {relative}"
                            )
                        _verify_directory_link(directory_fd, name, child_fd)
                        visit(child_fd, relative)
                        _verify_directory_link(directory_fd, name, child_fd)
                    finally:
                        os.close(child_fd)
                    continue

                if not stat.S_ISREG(linked_stat.st_mode):
                    continue
                if not name.casefold().endswith(extensions):
                    continue

                source_fd = os.open(name, _SOURCE_OPEN_FLAGS, dir_fd=directory_fd)
                try:
                    source_stat = os.fstat(source_fd)
                    current_link = os.stat(
                        name,
                        dir_fd=directory_fd,
                        follow_symlinks=False,
                    )
                    if (
                        not stat.S_ISREG(source_stat.st_mode)
                        or _object_identity(source_stat) != _object_identity(current_link)
                    ):
                        raise OSError(
                            f"input file changed during collection: {relative}"
                        )
                    collected.append(
                        (
                            input_root / relative,
                            relative,
                            _source_identity(root_stat, source_stat),
                        )
                    )
                finally:
                    os.close(source_fd)

        visit(root_fd, Path())
        _verify_root_identity(input_root, root_fd, root_identity)
        return collected
    finally:
        os.close(root_fd)


def _collect_sources_fallback(
    input_root: Path,
    output_root: Path,
    extensions: Tuple[str, ...],
) -> List[Tuple[Path, Path, _SourceIdentity]]:
    """Best-effort fallback for platforms without descriptor-relative opens."""
    root_stat = os.stat(input_root, follow_symlinks=False)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise OSError(f"input root is not a directory: {input_root}")
    root_identity = _object_identity(root_stat)
    output_relative = _nested_output_relative(input_root, output_root)
    collected: List[Tuple[Path, Path, _SourceIdentity]] = []

    for current_root, dirnames, filenames in os.walk(str(input_root), followlinks=False):
        current_path = Path(current_root)
        current_relative = current_path.relative_to(input_root)
        retained_directories = []
        for dirname in sorted(dirnames, key=lambda value: _path_key(Path(value))):
            relative = current_relative / dirname
            candidate = current_path / dirname
            candidate_stat = os.stat(candidate, follow_symlinks=False)
            if stat.S_ISLNK(candidate_stat.st_mode):
                logger.warning(f"심볼릭 링크 입력 건너뜀: {candidate}")
                continue
            if output_relative is not None and relative == output_relative:
                continue
            retained_directories.append(dirname)
        dirnames[:] = retained_directories

        for filename in sorted(filenames, key=lambda value: _path_key(Path(value))):
            if not filename.casefold().endswith(extensions):
                continue
            source = current_path / filename
            relative = source.relative_to(input_root)
            source_stat = os.stat(source, follow_symlinks=False)
            if stat.S_ISLNK(source_stat.st_mode):
                logger.warning(f"심볼릭 링크 입력 건너뜀: {source}")
                continue
            if not stat.S_ISREG(source_stat.st_mode):
                continue
            if _object_identity(
                os.stat(input_root, follow_symlinks=False)
            ) != root_identity:
                raise OSError(f"input root changed during collection: {input_root}")
            collected.append(
                (source, relative, _source_identity(root_stat, source_stat))
            )

    return collected


def _collect_sources(
    input_root: Path,
    output_root: Path,
    extensions: tuple,
) -> List[Tuple[Path, Path, _SourceIdentity]]:
    normalized_extensions = tuple(str(extension).casefold() for extension in extensions)
    if _HAS_DESCRIPTOR_WALK:
        return _collect_sources_descriptor(
            input_root,
            output_root,
            normalized_extensions,
        )
    return _collect_sources_fallback(
        input_root,
        output_root,
        normalized_extensions,
    )


def _verify_source_link(
    parent_fd: int,
    source_name: str,
    source_fd: int,
    expected: _SourceIdentity,
) -> os.stat_result:
    source_stat = os.fstat(source_fd)
    linked_stat = os.stat(
        source_name,
        dir_fd=parent_fd,
        follow_symlinks=False,
    )
    if (
        not stat.S_ISREG(source_stat.st_mode)
        or not stat.S_ISREG(linked_stat.st_mode)
        or _object_identity(source_stat) != _object_identity(linked_stat)
        or not _source_stat_matches(source_stat, expected)
        or not _source_stat_matches(linked_stat, expected)
    ):
        raise OSError(f"input source changed before it could be read: {source_name}")
    return source_stat


@contextmanager
def _private_source_snapshot(
    input_root: str,
    relative_path: str,
    expected: _SourceIdentity,
) -> Iterator[Path]:
    """Copy a verified input descriptor into a private, same-suffix snapshot."""
    if expected.source_size > MAX_BATCH_SOURCE_SIZE:
        raise OSError(
            "input source exceeds batch snapshot size limit: "
            f"{expected.source_size} > {MAX_BATCH_SOURCE_SIZE} bytes"
        )
    root_path = Path(input_root)
    relative = Path(relative_path)
    parts = _validate_relative_path(relative, "input")
    opened_fds: List[int] = []
    directory_links: List[Tuple[int, str, int]] = []
    source_fd: Optional[int] = None
    source_parent_fd: Optional[int] = None

    try:
        if _HAS_DESCRIPTOR_WALK:
            root_fd = os.open(str(root_path), _DIRECTORY_OPEN_FLAGS)
            opened_fds.append(root_fd)
            expected_root = (expected.root_device, expected.root_inode)
            _verify_root_identity(root_path, root_fd, expected_root)

            current_fd = root_fd
            for component in parts[:-1]:
                child_fd = os.open(
                    component,
                    _DIRECTORY_OPEN_FLAGS,
                    dir_fd=current_fd,
                )
                opened_fds.append(child_fd)
                directory_links.append((current_fd, component, child_fd))
                _verify_directory_link(current_fd, component, child_fd)
                current_fd = child_fd

            source_parent_fd = current_fd
            try:
                source_fd = os.open(
                    parts[-1],
                    _SOURCE_OPEN_FLAGS,
                    dir_fd=source_parent_fd,
                )
            except OSError as exc:
                raise OSError(
                    f"input source changed before it could be read: {relative}"
                ) from exc
            _verify_directory_chain(
                root_path,
                root_fd,
                directory_links,
                expected_root,
            )
            before_copy = _verify_source_link(
                source_parent_fd,
                parts[-1],
                source_fd,
                expected,
            )
        else:
            source_path = root_path / relative
            root_stat = os.stat(root_path, follow_symlinks=False)
            if _object_identity(root_stat) != (
                expected.root_device,
                expected.root_inode,
            ):
                raise OSError(f"input root identity changed: {root_path}")
            if source_path.resolve(strict=True).relative_to(root_path) != relative:
                raise OSError(f"input source changed before it could be read: {relative}")
            linked_stat = os.stat(source_path, follow_symlinks=False)
            if stat.S_ISLNK(linked_stat.st_mode):
                raise OSError(f"symbolic-link inputs are not allowed: {source_path}")
            source_fd = os.open(str(source_path), _SOURCE_OPEN_FLAGS)
            before_copy = os.fstat(source_fd)
            if (
                not stat.S_ISREG(before_copy.st_mode)
                or not _source_stat_matches(before_copy, expected)
                or _object_identity(before_copy) != _object_identity(linked_stat)
            ):
                raise OSError(
                    f"input source changed before it could be read: {source_path}"
                )

        with tempfile.TemporaryDirectory(prefix="dochan-batch-") as temp_directory:
            snapshot_path = Path(temp_directory) / f"source{relative.suffix}"
            with os.fdopen(os.dup(source_fd), mode='rb') as source_file:
                with snapshot_path.open(mode='xb') as snapshot_file:
                    _copy_exact_source(
                        source_file,
                        snapshot_file,
                        expected.source_size,
                        relative,
                    )
                    snapshot_file.flush()

            after_copy = os.fstat(source_fd)
            if (
                _object_identity(before_copy) != _object_identity(after_copy)
                or not _source_stat_matches(after_copy, expected)
            ):
                raise OSError(f"input source changed while it was read: {relative}")

            if _HAS_DESCRIPTOR_WALK:
                _verify_directory_chain(
                    root_path,
                    opened_fds[0],
                    directory_links,
                    (expected.root_device, expected.root_inode),
                )
                _verify_source_link(
                    source_parent_fd,
                    parts[-1],
                    source_fd,
                    expected,
                )
            else:
                current_link = os.stat(root_path / relative, follow_symlinks=False)
                if (
                    _object_identity(current_link) != _object_identity(after_copy)
                    or not _source_stat_matches(current_link, expected)
                ):
                    raise OSError(f"input source changed while it was read: {relative}")

            yield snapshot_path
    finally:
        if source_fd is not None:
            os.close(source_fd)
        for directory_fd in reversed(opened_fds):
            os.close(directory_fd)


def _copy_exact_source(source_file, snapshot_file, expected_size: int, label) -> None:
    """Copy the scanned size and probe one byte for concurrent growth."""
    remaining = expected_size
    while remaining:
        chunk = source_file.read(min(1024 * 1024, remaining))
        if not chunk:
            raise OSError(f"input source changed while it was read: {label}")
        snapshot_file.write(chunk)
        remaining -= len(chunk)

    if source_file.read(1):
        raise OSError(f"input source changed while it was read: {label}")


def _atomic_write_text(
    output_path: str,
    content: str,
    allowed_root: str = "",
    protected_paths: Sequence[str] = (),
) -> None:
    """Write beside the target and atomically publish it with ``os.replace``."""
    target = Path(output_path)
    if allowed_root:
        _assert_within_root(target, Path(allowed_root))
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
    if allowed_root:
        # This second check keeps the pre-existing defense in depth.  All
        # operations after it are descriptor-relative, so replacing a checked
        # directory with a symlink cannot redirect publication.
        _assert_within_root(target, Path(allowed_root))

    target_name = target.name
    if (
        not target_name
        or target_name in {'.', '..'}
        or os.sep in target_name
        or (os.altsep is not None and os.altsep in target_name)
    ):
        raise ValueError(f"invalid output filename: {target_name!r}")

    parent_fd: Optional[int] = None
    root_fd: Optional[int] = None
    opened_fds: List[int] = []
    directory_links: List[Tuple[int, str, int]] = []
    expected_root: Optional[Tuple[int, int]] = None
    root: Optional[Path] = None
    temp_name: Optional[str] = None
    temp_fd: Optional[int] = None
    backup_name: Optional[str] = None
    published_identity: Optional[Tuple[int, int]] = None
    target_identity: Optional[Tuple[int, int]] = None

    try:
        directory_flags = (
            os.O_RDONLY
            | getattr(os, 'O_DIRECTORY', 0)
            | getattr(os, 'O_CLOEXEC', 0)
        )
        if allowed_root:
            directory_flags |= getattr(os, 'O_NOFOLLOW', 0)
            # Keep user-facing check path as provided so a second check can
            # reason about the declared output root (including aliases like
            # ``/tmp``).  Descriptor traversal uses a resolved root directory
            # to avoid ENOTDIR when the root path itself is a symlink.
            root = Path(os.path.abspath(allowed_root))
            root_for_open = Path(os.path.realpath(str(root)))
            absolute_target = Path(os.path.abspath(str(target)))
            try:
                relative_target = absolute_target.relative_to(root)
            except ValueError as exc:
                raise ValueError(
                    f"output path escapes output directory: {target}"
                ) from exc
            if not relative_target.parts or relative_target.name in {'.', '..'}:
                raise ValueError(f"invalid output filename: {relative_target!s}")

            relative_parent = relative_target.parent
            if any(part in {'', '.', '..'} for part in relative_parent.parts):
                raise ValueError(f"invalid output parent: {relative_parent}")

            root_fd = os.open(str(root_for_open), directory_flags)
            parent_fd = root_fd
            opened_fds.append(root_fd)
            expected_root = _object_identity(
                _verify_root_identity(root_for_open, root_fd)
            )
            for component in relative_parent.parts:
                try:
                    next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
                except FileNotFoundError:
                    try:
                        os.mkdir(component, mode=0o777, dir_fd=parent_fd)
                    except FileExistsError:
                        pass
                    next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
                directory_links.append((parent_fd, component, next_fd))
                _verify_directory_link(parent_fd, component, next_fd)
                parent_fd = next_fd
                opened_fds.append(parent_fd)
            _verify_directory_chain(
                root_for_open,
                root_fd,
                directory_links,
                expected_root,
            )
        else:
            parent_fd = os.open(str(target.parent), directory_flags)
            opened_fds.append(parent_fd)

        try:
            target_stat = os.stat(
                target_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_mode = None
        else:
            if not stat.S_ISREG(target_stat.st_mode):
                raise OSError(f"output target is not a regular file: {target}")
            target_mode = target_stat.st_mode & 0o777
            target_identity = _object_identity(target_stat)

        for protected_path in protected_paths:
            try:
                protected_stat = os.stat(protected_path, follow_symlinks=True)
            except FileNotFoundError:
                continue
            if target_identity is not None and (
                _object_identity(protected_stat) == target_identity
            ):
                raise ValueError(
                    "output path aliases a protected input: "
                    f"{protected_path}"
                )
            try:
                same_path = os.path.samefile(str(target), protected_path)
            except (FileNotFoundError, OSError):
                same_path = (
                    os.path.realpath(str(target)) == os.path.realpath(protected_path)
                )
            if same_path:
                raise ValueError(
                    "output path aliases a protected input: "
                    f"{protected_path}"
                )

        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, 'O_CLOEXEC', 0)
            | getattr(os, 'O_NOFOLLOW', 0)
        )
        for _ in range(128):
            candidate = f'.{target_name}.{secrets.token_hex(8)}.tmp'
            try:
                temp_fd = os.open(candidate, flags, 0o666, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temp_name = candidate
            break
        else:
            raise FileExistsError(f"could not allocate temporary file for: {target}")

        if target_mode is not None:
            os.fchmod(temp_fd, target_mode)

        with os.fdopen(temp_fd, mode='w', encoding='utf-8') as temp_file:
            temp_fd = None
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            published_identity = _object_identity(os.fstat(temp_file.fileno()))

        # The context manager above closes the descriptor before its name is
        # handed to os.replace; this is required for portable atomic publish.
        if allowed_root:
            _verify_directory_chain(
                root,
                root_fd,
                directory_links,
                expected_root,
            )

        # Preserve an existing target inside the already-opened directory.
        # If the directory is renamed after publication, post-publish
        # validation can fail even though os.replace succeeded.  A same-file
        # hard link lets us restore the previous contents through the pinned
        # descriptor instead of deleting both versions.
        if target_identity is not None:
            for _ in range(128):
                candidate = f'.{target_name}.{secrets.token_hex(8)}.bak'
                try:
                    os.link(
                        target_name,
                        candidate,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    continue
                backup_name = candidate
                break
            else:
                raise FileExistsError(
                    f"could not allocate recovery link for: {target}"
                )

            backup_stat = os.stat(
                backup_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            current_target = os.stat(
                target_name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if (
                _object_identity(backup_stat) != target_identity
                or _object_identity(current_target) != target_identity
            ):
                raise OSError(f"output target changed before publication: {target}")

        os.replace(
            temp_name,
            target_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temp_name = None

        published_stat = os.stat(
            target_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(published_stat.st_mode)
            or _object_identity(published_stat) != published_identity
        ):
            raise OSError(f"output target changed during publication: {target}")
        if allowed_root:
            _verify_directory_chain(
                root,
                root_fd,
                directory_links,
                expected_root,
            )
        if backup_name is not None:
            os.unlink(backup_name, dir_fd=parent_fd)
            backup_name = None
    except BaseException:
        if temp_fd is not None:
            os.close(temp_fd)
        if temp_name is not None and parent_fd is not None:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        target_is_published = False
        if parent_fd is not None and published_identity is not None:
            try:
                current_target = os.stat(
                    target_name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                target_is_published = (
                    _object_identity(current_target) == published_identity
                )
                if target_is_published:
                    os.unlink(target_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        if backup_name is not None and parent_fd is not None:
            try:
                if target_identity is not None:
                    try:
                        current_target = os.stat(
                            target_name,
                            dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        current_target = None
                    if current_target is None:
                        os.rename(
                            backup_name,
                            target_name,
                            src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd,
                        )
                        backup_name = None
                    elif _object_identity(current_target) == target_identity:
                        os.unlink(backup_name, dir_fd=parent_fd)
                        backup_name = None
            except FileNotFoundError:
                backup_name = None
            finally:
                if backup_name is not None:
                    try:
                        os.unlink(backup_name, dir_fd=parent_fd)
                    except FileNotFoundError:
                        pass
                    backup_name = None
        raise
    finally:
        for directory_fd in reversed(opened_fds):
            os.close(directory_fd)


def _path_key(path: Path) -> str:
    """Use a conservative key for filesystems with case/Unicode folding."""
    return unicodedata.normalize('NFC', str(path)).casefold()


def _plan_outputs(
    files: Sequence[Tuple[Path, Path]], output_dir: Path, output_format: str
) -> List[Tuple[Path, Path]]:
    """Map sources to deterministic, collision-free output paths."""
    output_extension = _OUTPUT_EXTENSIONS[output_format]
    base_targets = [
        output_dir / relative.parent / f'{relative.stem}{output_extension}'
        for _, relative in files
    ]
    target_counts: Dict[str, int] = {}
    for target in base_targets:
        key = _path_key(target)
        target_counts[key] = target_counts.get(key, 0) + 1

    planned = []
    used_targets = set()
    for (source, relative), base_target in zip(files, base_targets):
        if target_counts[_path_key(base_target)] > 1:
            candidate = output_dir / relative.parent / f'{relative.name}{output_extension}'
        else:
            candidate = base_target

        unique_candidate = candidate
        suffix_number = 2
        while _path_key(unique_candidate) in used_targets:
            unique_candidate = candidate.with_name(
                f'{candidate.stem}.{suffix_number}{candidate.suffix}'
            )
            suffix_number += 1

        _assert_within_root(unique_candidate, output_dir)
        used_targets.add(_path_key(unique_candidate))
        planned.append((source, unique_candidate))

    return planned


def _process_single(
    file_path: str,
    output_path: str,
    output_format: str,
    output_root: str = "",
    input_root: str = "",
    relative_path: str = "",
    source_identity: Optional[_SourceIdentity] = None,
) -> BatchResult:
    """단일 파일 처리 (별도 프로세스에서 실행)"""
    from .reader import Dochan

    result = BatchResult(file_path=file_path)

    try:
        def convert(source_path: str) -> Tuple[str, List[str]]:
            reader = Dochan(source_path)
            if output_format == 'json':
                rendered = reader.to_json()
            elif output_format == 'text':
                rendered = reader.to_plain_text()
            else:
                rendered = reader.to_markdown()
            return rendered, list(reader.errors)

        if source_identity is None:
            content, parser_errors = convert(file_path)
        else:
            with _private_source_snapshot(
                input_root,
                relative_path,
                source_identity,
            ) as snapshot_path:
                content, parser_errors = convert(str(snapshot_path))

        if any(_is_fatal_parser_error(error) for error in parser_errors):
            result.errors = parser_errors
            result.error_count = len(parser_errors)
            return result

        # 같은 디렉터리의 임시 파일을 거쳐 원자적으로 게시
        _atomic_write_text(
            output_path,
            content,
            allowed_root=output_root,
            protected_paths=(file_path,),
        )

        result.success = True
        result.output_path = output_path
        result.errors = parser_errors
        result.error_count = len(parser_errors)

    except Exception as e:
        result.success = False
        result.errors = [str(e)]
        result.error_count = 1

    return result


def batch_convert(
    input_dir: str,
    output_dir: str,
    output_format: str = 'markdown',
    max_workers: int = 4,
    extensions: tuple = ('.hwp', '.hwpx', '.doc', '.ppt', '.xls', '.docx', '.pptx', '.xlsx', '.pdf'),
) -> BatchSummary:
    """
    디렉토리 내 HWP 파일 일괄 변환

    Args:
        input_dir: 입력 디렉토리
        output_dir: 출력 디렉토리
        output_format: 'markdown', 'json', 'text'
        max_workers: 병렬 워커 수
        extensions: 처리할 확장자

    Returns:
        BatchSummary
    """
    if output_format not in _OUTPUT_EXTENSIONS:
        valid_formats = ', '.join(sorted(_OUTPUT_EXTENSIONS))
        raise ValueError(
            f"output_format must be one of: {valid_formats}; got {output_format!r}"
        )
    if (
        not isinstance(max_workers, int)
        or isinstance(max_workers, bool)
        or max_workers < 1
    ):
        raise ValueError(f"max_workers must be a positive integer; got {max_workers!r}")

    resolved_input = Path(input_dir).resolve()
    resolved_output = Path(output_dir).resolve()
    if not resolved_input.is_dir():
        raise FileNotFoundError(f"input directory does not exist: {input_dir}")
    resolved_output.mkdir(parents=True, exist_ok=True)

    # Descriptor-relative collection rejects symbolic links and captures the
    # identities that workers must see before parsing any source bytes.
    collected_files = _collect_sources(resolved_input, resolved_output, extensions)
    collected_files.sort(key=lambda item: _path_key(item[1]))
    files = [(source, relative) for source, relative, _ in collected_files]
    planned_files = _plan_outputs(files, resolved_output, output_format)
    work_items = [
        (source, output_path, relative, identity)
        for (source, output_path), (_, relative, identity) in zip(
            planned_files,
            collected_files,
        )
    ]

    summary = BatchSummary(total=len(work_items))
    logger.info(f"배치 시작: {len(work_items)}개 파일, {max_workers} 워커")

    if max_workers <= 1:
        for file_path, output_path, relative_path, source_identity in work_items:
            result = _process_single(
                str(file_path),
                str(output_path),
                output_format,
                str(resolved_output),
                str(resolved_input),
                str(relative_path),
                source_identity,
            )
            summary.results.append(result)
            if result.success:
                summary.success += 1
                logger.info(f"✓ {os.path.basename(file_path)}")
            else:
                summary.failed += 1
                logger.error(f"✗ {os.path.basename(file_path)}: {result.errors}")

        logger.info(f"배치 완료: {summary.success}/{summary.total} 성공 ({summary.success_rate:.1f}%)")
        return summary

    # 병렬 처리
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_single,
                str(file_path),
                str(output_path),
                output_format,
                str(resolved_output),
                str(resolved_input),
                str(relative_path),
                source_identity,
            ): str(file_path)
            for file_path, output_path, relative_path, source_identity in work_items
        }

        for future in as_completed(futures):
            file_path = futures[future]
            try:
                result = future.result()
                summary.results.append(result)
                if result.success:
                    summary.success += 1
                    logger.info(f"✓ {os.path.basename(file_path)}")
                else:
                    summary.failed += 1
                    logger.error(f"✗ {os.path.basename(file_path)}: {result.errors}")
            except Exception as e:
                summary.failed += 1
                summary.results.append(BatchResult(
                    file_path=file_path,
                    success=False,
                    errors=[str(e)],
                    error_count=1,
                ))
                logger.error(f"✗ {os.path.basename(file_path)}: {e}")

    logger.info(f"배치 완료: {summary.success}/{summary.total} 성공 ({summary.success_rate:.1f}%)")
    return summary
