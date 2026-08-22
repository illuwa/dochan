"""Parser diagnostic severity classification.

Diagnostics are recoverable by default.  A fatal classification requires an
explicit, anchored severity marker so words such as ``stderr`` or ``parse`` in
a warning body cannot accidentally make a partial conversion unusable.
"""

import re
from enum import Enum
from typing import Any


class DiagnosticSeverity(str, Enum):
    """Severity levels understood by conversion and quality APIs."""

    FATAL = "fatal"
    RECOVERABLE = "recoverable"


_CONTEXT_PREFIX = r"(?:\[[^\]\r\n]{1,128}\]\s*)*"
_WARNING_PREFIX = re.compile(
    rf"^\s*{_CONTEXT_PREFIX}WARN(?:ING)?\s*:",
    flags=re.IGNORECASE,
)
_FATAL_PREFIX = re.compile(
    rf"^\s*{_CONTEXT_PREFIX}(?:"
    r"ERR(?:OR)?\s*:"
    r"|FATAL\s*:"
    r"|FATAL\s+(?:PARSE|PARSER|PARSING)\s+(?:ERROR|FAILURE)\b"
    r"|치명적(?:인)?\s*(?:(?:문서|데이터)\s*)?(?:파싱|파서).*?(?:오류|실패)"
    r")",
    flags=re.IGNORECASE,
)


def classify_diagnostic(diagnostic: Any) -> DiagnosticSeverity:
    """Classify an explicitly marked parser diagnostic.

    Optional leading ``[context]`` tags are supported.  A leading warning
    marker always wins over fatal-looking words later in the message.  Legacy
    unmarked diagnostics remain recoverable for backward compatibility.
    """

    message = str(diagnostic)
    if _WARNING_PREFIX.match(message):
        return DiagnosticSeverity.RECOVERABLE
    if _FATAL_PREFIX.match(message):
        return DiagnosticSeverity.FATAL
    return DiagnosticSeverity.RECOVERABLE


def is_fatal_diagnostic(diagnostic: Any) -> bool:
    """Return whether *diagnostic* has an explicit fatal severity."""

    return classify_diagnostic(diagnostic) is DiagnosticSeverity.FATAL


__all__ = [
    "DiagnosticSeverity",
    "classify_diagnostic",
    "is_fatal_diagnostic",
]
