"""Bounded reads for untrusted OLE streams."""

import inspect
import os
from dataclasses import dataclass
from typing import Any, Optional


MAX_OLE_STREAM_SIZE = 100 * 1024 * 1024
MAX_OLE_DOCUMENT_SIZE = 200 * 1024 * 1024


class BoundedIOError(ValueError):
    """Base error for bounded stream validation failures."""


class ResourceLimitError(BoundedIOError):
    """Raised before an untrusted stream can exceed a configured byte limit."""


class StreamSizeError(BoundedIOError):
    """Raised when a stream does not match its declared or required size."""


@dataclass
class ByteBudget:
    """Cumulative byte budget shared by all streams in one document."""

    limit: int
    used: int = 0

    def __post_init__(self) -> None:
        _validate_limit(self.limit, "limit")
        _validate_limit(self.used, "used")
        if self.used > self.limit:
            raise ValueError("used cannot exceed limit")

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def consume(self, size: int, label: str) -> None:
        _validate_limit(size, "size")
        if size > self.remaining:
            raise ResourceLimitError(
                f"{label} exceeds document stream budget: "
                f"{self.used} + {size} > {self.limit} bytes"
            )
        self.used += size


def validate_file_size(file_path: str, max_bytes: int = MAX_OLE_DOCUMENT_SIZE) -> None:
    """Reject an oversized OLE file before ``olefile`` parses its allocation tables."""

    _validate_limit(max_bytes, "max_bytes")
    try:
        size = os.path.getsize(file_path)
    except OSError:
        # The format reader owns path/open error normalization.  Returning here
        # preserves its Document.errors contract without weakening stream caps.
        return
    if size > max_bytes:
        raise ResourceLimitError(
            f"OLE file exceeds size limit: {size} > {max_bytes} bytes"
        )


def read_ole_stream(
    ole: Any,
    name: str,
    *,
    max_bytes: int = MAX_OLE_STREAM_SIZE,
    budget: Optional[ByteBudget] = None,
    expected_size: Optional[int] = None,
) -> bytes:
    """Read one OLE stream with a ``limit + 1`` overrun probe.

    Real ``olefile`` objects expose ``get_size``.  That metadata is checked before
    ``openstream`` so an oversized stream is rejected without allocating its
    payload.  Small test doubles that omit ``get_size`` remain supported and are
    bounded by the actual read.
    """

    _validate_limit(max_bytes, "max_bytes")
    if expected_size is not None:
        _validate_limit(expected_size, "expected_size")

    label = str(name)
    declared_size = _ole_declared_size(ole, name)
    if expected_size is not None and declared_size is not None:
        if declared_size != expected_size:
            raise StreamSizeError(
                f"{label} size mismatch: declared={declared_size}, "
                f"expected={expected_size} bytes"
            )
    if declared_size is not None and declared_size > max_bytes:
        raise ResourceLimitError(
            f"{label} exceeds per-stream limit: "
            f"{declared_size} > {max_bytes} bytes"
        )
    if budget is not None and declared_size is not None:
        if declared_size > budget.remaining:
            raise ResourceLimitError(
                f"{label} exceeds document stream budget: "
                f"{budget.used} + {declared_size} > {budget.limit} bytes"
            )

    effective_limit = max_bytes
    if budget is not None:
        effective_limit = min(effective_limit, budget.remaining)

    stream = ole.openstream(name)
    data = read_bounded(stream, effective_limit, label=label)
    if declared_size is not None and len(data) != declared_size:
        raise StreamSizeError(
            f"{label} size mismatch: declared={declared_size}, read={len(data)} bytes"
        )
    if expected_size is not None and len(data) != expected_size:
        raise StreamSizeError(
            f"{label} size mismatch: read={len(data)}, expected={expected_size} bytes"
        )
    if budget is not None:
        budget.consume(len(data), label)
    return data


def read_bounded(stream: Any, max_bytes: int, *, label: str = "stream") -> bytes:
    """Return bytes from a stream, rejecting the first byte beyond ``max_bytes``."""

    _validate_limit(max_bytes, "max_bytes")
    if isinstance(stream, (bytes, bytearray, memoryview)):
        if len(stream) > max_bytes:
            raise ResourceLimitError(
                f"{label} exceeds read limit: {len(stream)} > {max_bytes} bytes"
            )
        return bytes(stream)

    read = getattr(stream, "read", None)
    if not callable(read):
        raise TypeError(f"{label} is not a readable binary stream")

    try:
        data = read(max_bytes + 1)
    except TypeError as exc:
        # Compatibility for existing in-memory OLE test doubles whose read()
        # method intentionally has the same no-argument shape as bytes access.
        # A TypeError raised *inside* a size-aware reader must not trigger this
        # fallback because that could turn a bounded production read into read().
        try:
            signature = inspect.signature(read)
            signature.bind(max_bytes + 1)
        except (TypeError, ValueError):
            pass
        else:
            raise exc
        data = read()

    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError(f"{label} did not return bytes")
    if len(data) > max_bytes:
        raise ResourceLimitError(
            f"{label} exceeds read limit: {len(data)} > {max_bytes} bytes"
        )
    return bytes(data)


def _ole_declared_size(ole: Any, name: str) -> Optional[int]:
    get_size = getattr(ole, "get_size", None)
    if not callable(get_size):
        return None
    try:
        size = get_size(name)
    except (AttributeError, KeyError, OSError, TypeError):
        return None
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise StreamSizeError(f"{name} has invalid declared size: {size!r}")
    return size


def _validate_limit(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
