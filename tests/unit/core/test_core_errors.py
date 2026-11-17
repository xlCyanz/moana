"""Error hierarchy: stable codes, CLI exit codes and immutable, non-sensitive context."""

import copy
import pickle
from typing import cast

import pytest

from moana.core import errors

PUBLIC = {
    errors.ValidationError: ("VALIDATION_ERROR", 2),
    errors.OutOfBoundsError: ("OUT_OF_BOUNDS", 2),
    errors.ReferenceError: ("REFERENCE_ERROR", 2),
    errors.UnsupportedVersion: ("UNSUPPORTED_VERSION", 2),
    errors.UnsupportedOperation: ("UNSUPPORTED_OPERATION", 2),
    errors.BudgetExceeded: ("BUDGET_EXCEEDED", 3),
    errors.EditConflict: ("EDIT_CONFLICT", 4),
    errors.ExportError: ("EXPORT_ERROR", 5),
}


@pytest.mark.parametrize(("error_type", "expected"), PUBLIC.items())
def test_codes_and_exit_codes_follow_moana_spec(
    error_type: type[errors.MoanaError], expected: tuple[str, int]
) -> None:
    error = error_type("message")
    assert (error.code, error.exit_code) == expected
    assert isinstance(error, errors.MoanaError)
    assert str(error) == "message"


def test_codes_are_unique_and_base_is_internal_failure() -> None:
    codes = [error_type.code for error_type in PUBLIC]
    assert len(set(codes)) == len(codes)
    assert errors.MoanaError("boom").exit_code == 1


def test_bounds_error_is_a_validation_error() -> None:
    assert issubclass(errors.OutOfBoundsError, errors.ValidationError)


def test_context_is_copied_and_read_only() -> None:
    source: dict[str, object] = {"field": "x"}
    error = errors.ValidationError("bad", context=source)
    source["field"] = "changed"
    assert error.context == {"field": "x"}
    with pytest.raises(TypeError):
        cast(dict[str, object], error.context)["field"] = "y"


def test_reference_error_does_not_shadow_builtin_for_callers() -> None:
    assert not issubclass(errors.ReferenceError, ReferenceError)


@pytest.mark.parametrize("error_type", [errors.MoanaError, *PUBLIC])
def test_errors_survive_pickle_and_deepcopy(error_type: type[errors.MoanaError]) -> None:
    original = error_type("bad", json_pointer="/canvas/width", context={"field": "width"})
    for clone in (pickle.loads(pickle.dumps(original)), copy.deepcopy(original)):
        assert type(clone) is error_type
        assert (clone.message, clone.json_pointer, clone.code, clone.exit_code) == (
            "bad",
            "/canvas/width",
            error_type.code,
            error_type.exit_code,
        )
        assert clone.context == {"field": "width"}


def test_error_attributes_are_read_only() -> None:
    error = errors.ValidationError("bad", context={"field": "x"})
    for name in ("context", "message", "json_pointer"):
        with pytest.raises(AttributeError):
            setattr(error, name, None)


@pytest.mark.parametrize("value", [[1], {"a": 1}, (1, [2]), 1.5, object()])
def test_context_rejects_mutable_or_non_scalar_values(value: object) -> None:
    with pytest.raises(TypeError):
        errors.ValidationError("bad", context={"field": value})


def test_context_accepts_scalars_and_tuples() -> None:
    error = errors.ValidationError(
        "bad", context={"a": 1, "b": "x", "c": None, "d": True, "e": (1, "y")}
    )
    assert error.context["e"] == (1, "y")
    assert error.json_pointer is None
