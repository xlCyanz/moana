"""Bounded reader: limits enforced before parsing, duplicates, constants and mappings."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

import pytest

from moanart.core import errors
from moanart.schema._pointers import MAX_POINTER_TOKEN, ROOT, child_pointer
from moanart.schema._reader import (
    DEFAULT_PARSE_LIMITS,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_DEPTH,
    MAX_DOCUMENT_NODES,
    ParseLimits,
    read_json_bytes,
    read_mapping,
)

pytestmark = pytest.mark.security


def reason_of(raised: pytest.ExceptionInfo[errors.ValidationError]) -> object:
    return raised.value.context["reason"]


def nested(depth: int) -> bytes:
    """An object whose innermost container sits at ``depth``."""
    return b'{"a":' + b"[" * (depth - 1) + b"]" * (depth - 1) + b"}"


def test_defaults_match_section_20() -> None:
    assert (MAX_DOCUMENT_BYTES, MAX_DOCUMENT_DEPTH, MAX_DOCUMENT_NODES) == (
        8 * 1024 * 1024,
        32,
        20_000,
    )
    assert ParseLimits() == DEFAULT_PARSE_LIMITS


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_bytes": MAX_DOCUMENT_BYTES + 1},
        {"max_depth": MAX_DOCUMENT_DEPTH + 1},
        {"max_nodes": MAX_DOCUMENT_NODES + 1},
        {"max_depth": 0},
        {"max_nodes": True},
    ],
)
def test_limits_can_only_be_lowered(overrides: dict[str, Any]) -> None:
    with pytest.raises(errors.ValidationError):
        ParseLimits(**overrides)


def test_size_is_checked_before_decoding() -> None:
    limits = ParseLimits(max_bytes=16)
    assert read_json_bytes(b'{"a":"0123456"}', limits) == {"a": "0123456"}
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(b'{"a":"' + b"\xff" * 9 + b'"}', limits)  # 17 bytes, invalid UTF-8
    assert reason_of(raised) == "too_large"
    assert raised.value.context["maximum"] == 16


def test_depth_limit_is_inclusive_and_checked_before_parsing() -> None:
    assert read_json_bytes(nested(MAX_DOCUMENT_DEPTH))
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(nested(MAX_DOCUMENT_DEPTH + 1))
    assert reason_of(raised) == "too_deep"
    # Far deeper than the interpreter recursion limit: rejected by the scan, not json.
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(b"[" * 200_000)
    assert reason_of(raised) == "too_deep"


def test_brackets_inside_strings_do_not_count_as_depth() -> None:
    text = '{"a":"' + "[" * 100 + '\\"' + "{" * 100 + '"}'
    assert read_json_bytes(text.encode()) == {"a": "[" * 100 + '"' + "{" * 100}


def test_node_limit_counts_values_not_member_names() -> None:
    limits = ParseLimits(max_nodes=4)
    assert read_json_bytes(b'{"a":1,"b":"x","c":[]}', limits)  # 4 values
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(b'{"a":1,"b":"x","c":[null]}', limits)
    assert reason_of(raised) == "too_many_nodes"


def test_unterminated_strings_scan_in_linear_time() -> None:
    hostile = b'{"a":"' + b'\\"' * 1_000_000
    started = time.perf_counter()
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(hostile)
    assert reason_of(raised) == "invalid_json"
    assert time.perf_counter() - started < 5


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b'{"a":NaN}', "non_finite_number"),
        (b'{"a":-Infinity}', "non_finite_number"),
        (b'{"a":1,}', "invalid_json"),
        (b'{"a":1} // comment', "invalid_json"),
        (b"\xef\xbb\xbf{}", "invalid_json"),
        (b'{"a":"\xc3"}', "invalid_utf8"),
        (b"[]", "root_not_object"),
        (b'"text"', "root_not_object"),
        (b'{"a":' + b"9" * 5000 + b"}", "invalid_json"),
    ],
)
def test_rejects_non_json_data(data: bytes, reason: str) -> None:
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(data)
    assert reason_of(raised) == reason
    assert raised.value.code == "VALIDATION_ERROR"


def test_rejects_non_bytes_source() -> None:
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(bytearray(b"{}"))  # type: ignore[arg-type]  # runtime guard
    assert reason_of(raised) == "not_bytes"


def test_duplicate_keys_are_reported_with_pointers() -> None:
    data = b'{"b":{"x/y":1,"x/y":2},"a":[{"k":1,"k":2,"k":3}]}'
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(data)
    pointers = [detail.json_pointer for detail in raised.value.details]
    assert pointers == ["/a/0/k", "/a/0/k", "/b/x~1y"]
    assert raised.value.json_pointer == "/a/0/k"
    assert {detail.context["reason"] for detail in raised.value.details} == {"duplicate_key"}


def test_reader_returns_plain_containers() -> None:
    tree = read_json_bytes(b'{"a":{"b":[1,true,null,"s",1.5]}}')
    assert type(tree) is dict
    inner = tree["a"]
    assert type(inner) is dict
    assert inner == {"b": [1, True, None, "s", 1.5]}


def test_mapping_is_copied_and_tuples_become_lists() -> None:
    source: dict[str, object] = {"a": OrderedDict(b=(1, (2, 3)))}
    tree = read_mapping(source)
    assert tree == {"a": {"b": [1, [2, 3]]}}
    assert type(tree["a"]) is dict
    assert tree is not source


def test_mapping_limits_and_keys() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(errors.ValidationError) as raised:
        read_mapping(cyclic)
    assert reason_of(raised) == "too_deep"
    with pytest.raises(errors.ValidationError) as raised:
        read_mapping({"a": {1: "x"}})
    assert reason_of(raised) == "non_string_key"
    assert raised.value.json_pointer == "/a"
    with pytest.raises(errors.ValidationError) as raised:
        read_mapping({"a": list(range(10))}, ParseLimits(max_nodes=5))
    assert reason_of(raised) == "too_many_nodes"
    with pytest.raises(errors.ValidationError) as raised:
        read_mapping([1])  # type: ignore[arg-type]  # runtime guard
    assert reason_of(raised) == "root_not_object"


def test_mapping_and_bytes_share_depth_semantics() -> None:
    limits = ParseLimits(max_depth=3)
    ok: dict[str, object] = {"a": [[1]]}
    too_deep: dict[str, object] = {"a": [[[1]]]}
    assert read_mapping(ok, limits) == read_json_bytes(b'{"a":[[1]]}', limits)
    with pytest.raises(errors.ValidationError) as raised:
        read_mapping(too_deep, limits)
    assert reason_of(raised) == "too_deep"
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(b'{"a":[[[1]]]}', limits)
    assert reason_of(raised) == "too_deep"


@pytest.mark.parametrize(("token", "escaped"), [("a/b", "a~1b"), ("m~n", "m~0n"), (3, "3")])
def test_pointer_tokens_follow_rfc_6901(token: str | int, escaped: str) -> None:
    assert child_pointer(ROOT, token) == (f"/{escaped}", True)


def test_duplicates_sort_numerically_and_long_names_stay_out_of_pointers() -> None:
    items = ",".join('{"k":1,"k":2}' for _ in range(12))
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(f'{{"l":[{items}]}}'.encode())
    assert [d.json_pointer for d in raised.value.details] == [f"/l/{i}/k" for i in range(12)]
    long_name = "x" * (MAX_POINTER_TOKEN + 1)
    with pytest.raises(errors.ValidationError) as raised:
        read_json_bytes(f'{{"a":{{"{long_name}":{{"k":1,"k":2}}}}}}'.encode())
    (detail,) = raised.value.details
    assert detail.json_pointer == "/a"
    assert detail.context["exact_pointer"] is False
    assert long_name not in repr(raised.value.details)
