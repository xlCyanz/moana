"""Domain error hierarchy shared by every Moana module (MOANA.md sections 12-13, ADR-010).

Each error carries a stable ``code`` for machines, the CLI ``exit_code`` of the
specification, an optional ``json_pointer`` locating the offending document node and
an immutable ``context``. Context values are scalars (``int``, ``bool``, ``str`` or
``None``) or tuples of scalars; strings name fields, reasons or types and never echo
untrusted input or file paths. Numeric geometry values may appear.

A document can fail in several places at once. Such an error also carries ``details``:
one :class:`ErrorDetail` per problem, each with its own code and pointer, sorted by
the reporting module (MOANA-002 orders them by pointer and code).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, ClassVar

__all__ = [
    "BudgetExceeded",
    "EditConflict",
    "ErrorDetail",
    "ExportError",
    "MoanaError",
    "OutOfBoundsError",
    "ReadError",
    "ReferenceError",
    "UnsupportedOperation",
    "UnsupportedVersion",
    "ValidationError",
    "detail_sort_key",
]

_SCALARS = (int, str, type(None))


def _check_context_value(key: str, value: object) -> None:
    items = value if isinstance(value, tuple) else (value,)
    if not all(isinstance(item, _SCALARS) for item in items):
        raise TypeError(f"error context value for {key!r} must be a scalar or tuple of scalars")


def _frozen_context(context: Mapping[str, object] | None) -> Mapping[str, object]:
    copied = dict(context or {})
    for key, value in copied.items():
        _check_context_value(key, value)
    return MappingProxyType(copied)


class ErrorDetail:
    """One located problem inside an aggregated error; immutable and picklable."""

    __slots__ = ("_code", "_context", "_json_pointer", "_message")

    def __init__(
        self,
        code: str,
        message: str,
        *,
        json_pointer: str | None = None,
        context: Mapping[str, object] | None = None,
    ) -> None:
        """Create a detail; ``context`` follows the same rules as :class:`MoanaError`."""
        self._code = code
        self._message = message
        self._json_pointer = json_pointer
        self._context = _frozen_context(context)

    @property
    def code(self) -> str:
        """Stable machine code of this problem (for example ``REFERENCE_ERROR``)."""
        return self._code

    @property
    def message(self) -> str:
        """Human-readable explanation, safe to show to the caller."""
        return self._message

    @property
    def json_pointer(self) -> str | None:
        """Location of the offending node (RFC 6901), when known."""
        return self._json_pointer

    @property
    def context(self) -> Mapping[str, object]:
        """Read-only structured details (field, reason, bounds...)."""
        return self._context

    def _key(self) -> tuple[object, ...]:
        return (self._code, self._message, self._json_pointer, tuple(sorted(self._context.items())))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ErrorDetail):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __repr__(self) -> str:
        return (
            f"ErrorDetail(code={self._code!r}, json_pointer={self._json_pointer!r}, "
            f"message={self._message!r}, context={dict(self._context)!r})"
        )

    def __reduce__(self) -> tuple[Any, ...]:
        return (
            _rebuild_detail,
            (self._code, self._message, self._json_pointer, dict(self._context)),
        )


def _rebuild_detail(
    code: str, message: str, json_pointer: str | None, context: dict[str, object]
) -> ErrorDetail:
    return ErrorDetail(code, message, json_pointer=json_pointer, context=context)


class MoanaError(Exception):
    """Base class for all Moana errors; an unexpected internal failure by default."""

    code: ClassVar[str] = "INTERNAL_ERROR"
    exit_code: ClassVar[int] = 1

    def __init__(
        self,
        message: str,
        *,
        json_pointer: str | None = None,
        context: Mapping[str, object] | None = None,
        details: Iterable[ErrorDetail] = (),
    ) -> None:
        """Create an error.

        ``context`` is copied into a read-only mapping; its values must be scalars or
        tuples of scalars so the error stays immutable, picklable and free of
        sensitive payloads. ``json_pointer`` (RFC 6901) is set by document validation.
        ``details`` lists every located problem when one error reports several.
        """
        super().__init__(message)
        self._message = message
        self._json_pointer = json_pointer
        self._context = _frozen_context(context)
        self._details = tuple(details)
        if not all(isinstance(detail, ErrorDetail) for detail in self._details):
            raise TypeError("error details must be ErrorDetail instances")

    @property
    def message(self) -> str:
        """Human-readable explanation, safe to show to the caller."""
        return self._message

    @property
    def json_pointer(self) -> str | None:
        """Location of the offending node in a document, when known."""
        return self._json_pointer

    @property
    def context(self) -> Mapping[str, object]:
        """Read-only structured details (field, reason, bounds...)."""
        return self._context

    @property
    def details(self) -> tuple[ErrorDetail, ...]:
        """Every located problem, in reporting order; empty for a single-cause error."""
        return self._details

    def __reduce__(self) -> tuple[Any, ...]:
        # Rebuild through the constructor so subclasses survive pickling between
        # isolated worker processes (MOANA.md section 20) and deepcopy.
        return (
            _rebuild,
            (type(self), self._message, self._json_pointer, dict(self._context), self._details),
        )


def _rebuild(
    cls: type[MoanaError],
    message: str,
    json_pointer: str | None,
    context: dict[str, object],
    details: tuple[ErrorDetail, ...] = (),
) -> MoanaError:
    return cls(message, json_pointer=json_pointer, context=context, details=details)


class ValidationError(MoanaError):
    """Input is structurally invalid: wrong type, out of range or inconsistent."""

    code = "VALIDATION_ERROR"
    exit_code = 2


class OutOfBoundsError(ValidationError):
    """Direct pixel access outside the canvas; never wraps like negative indices."""

    code = "OUT_OF_BOUNDS"


class ReferenceError(MoanaError):
    """A referenced ID is missing or the references form a cycle.

    The public name is fixed by MOANA.md section 13 and is unrelated to the builtin
    ``ReferenceError`` (weak references). Importing it by name shadows the builtin in
    the importing module, so prefer ``from moana.core import errors`` and
    ``errors.ReferenceError``.
    """

    code = "REFERENCE_ERROR"
    exit_code = 2


class UnsupportedVersion(MoanaError):
    """The document declares a schema or format version this reader does not support."""

    code = "UNSUPPORTED_VERSION"
    exit_code = 2


class UnsupportedOperation(MoanaError):
    """A recognised capability that is not implemented or not available in this build."""

    code = "UNSUPPORTED_OPERATION"
    exit_code = 2


class BudgetExceeded(MoanaError):
    """Estimated work or memory exceeds the request budget; raised before allocation."""

    code = "BUDGET_EXCEEDED"
    exit_code = 3


class EditConflict(MoanaError):
    """An edit batch targets a revision or snapshot that is not the current one."""

    code = "EDIT_CONFLICT"
    exit_code = 4


class ExportError(MoanaError):
    """Writing an export failed or the destination policy cannot be honoured."""

    code = "EXPORT_ERROR"
    exit_code = 5


class ReadError(MoanaError):
    """An input file chosen by the caller could not be read (missing, not a file, denied).

    Like :class:`ExportError`, its context names the file and the ``errno``, never the
    full path. Added by MOANA-012 (ADR-020), extending the codes of ADR-010.
    """

    code = "READ_ERROR"
    exit_code = 5


def detail_sort_key(detail: ErrorDetail) -> tuple[object, ...]:
    """Order by pointer (array indexes numerically), then code, then message."""
    pointer = detail.json_pointer
    tokens: tuple[tuple[int, int, str], ...] = ()
    if pointer:
        tokens = tuple(
            (0, int(token), "") if token.isascii() and token.isdigit() else (1, 0, token)
            for token in pointer[1:].split("/")
        )
    return (pointer is not None, tokens, detail.code, detail.message)
