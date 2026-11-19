"""JSON → modelo and resolución → render: hostile documents (T1, AC1).

Oracles are built independently of the engine: the pointer of a planted duplicate is
the path where the test planted it; the depth of a generated nesting is counted by the
generator; MOANA.md section 20 fixes the limits (32 levels, 20 000 nodes, 8 MiB).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from moana.api import load_document, render
from moana.core.errors import MoanaError, ReferenceError, ValidationError
from moana.project import load_project
from moana.schema import Document

from .corpus import ROOT, SECRET, minimal_bytes, minimal_tree
from .guards import (
    assert_clean_error,
    bounded_settings,
    forbid,
    forbid_effects,
    pointers,
    reasons,
)

pytestmark = pytest.mark.security

BOUNDED = bounded_settings(40)


# --- structure is measured before json.loads builds any object -------------------------


def _nesting(kinds: list[bool]) -> bytes:
    """A root object, then one container per flag (True: object, False: array)."""
    opening = "".join('{"k":' if is_object else "[" for is_object in kinds)
    closing = "".join("}" if is_object else "]" for is_object in reversed(kinds))
    return ('{"k":' + opening + "0" + closing + "}").encode("ascii")


@BOUNDED
@given(st.lists(st.booleans(), min_size=32, max_size=2_000))
def test_t1_property_nesting_beyond_32_is_rejected_before_parsing(kinds: list[bool]) -> None:
    payload = _nesting(kinds)  # depth = 1 + len(kinds) > 32
    with forbid(json, "loads"), forbid_effects(), pytest.raises(ValidationError) as caught:
        load_document(payload)
    assert caught.value.context["reason"] == "too_deep"
    assert caught.value.context["maximum"] == 32


@BOUNDED
@given(st.integers(0, 31))
def test_t1_property_nesting_within_32_reaches_the_model(extra: int) -> None:
    payload = _nesting([True] * extra)  # depth = 1 + extra <= 32: shape accepted
    with pytest.raises(ValidationError) as caught:
        load_document(payload)
    assert caught.value.context.get("reason") not in ("too_deep", "too_many_nodes")


def test_t1_node_count_and_size_are_checked_before_parsing() -> None:
    nodes = ('{"a":[' + ",".join(["0"] * 20_000) + "]}").encode("ascii")  # 20 001 nodes
    with forbid(json, "loads"), forbid_effects(), pytest.raises(ValidationError) as caught:
        load_document(nodes)
    assert caught.value.context["reason"] == "too_many_nodes"
    oversized = b" " * (8 * 1024 * 1024 + 1)
    with forbid(json, "loads"), forbid_effects(), pytest.raises(ValidationError) as caught:
        load_document(oversized)
    assert caught.value.context["reason"] == "too_large"


def test_t1_project_manifest_shape_is_checked_before_parsing(tmp_path: Path) -> None:
    source = tmp_path / "deep.moana.json"
    source.write_bytes(_nesting([False] * 40))
    with forbid(json, "loads"), forbid_effects(), pytest.raises(ValidationError) as caught:
        load_project(source)
    assert caught.value.context["reason"] == "too_deep"
    assert_clean_error(caught.value, tmp_path)


# --- duplicates and non-finite numbers wherever they are planted ----------------------


def _objects(tree: object, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    """Every (object path, member name) pair of ``tree``."""
    found: list[tuple[tuple[str, ...], str]] = []
    if isinstance(tree, dict):
        for key, value in tree.items():
            found.append((path, key))
            found.extend(_objects(value, (*path, key)))
    elif isinstance(tree, list):
        for index, value in enumerate(tree):
            found.extend(_objects(value, (*path, str(index))))
    return found


def _dump(tree: object, path: tuple[str, ...], target: tuple[str, ...], key: str) -> str:
    """JSON text of ``tree`` where the object at ``target`` repeats member ``key``."""
    if isinstance(tree, dict):
        members = [
            json.dumps(name) + ":" + _dump(value, (*path, name), target, key)
            for name, value in tree.items()
        ]
        if path == target:
            members.append(json.dumps(key) + ":" + json.dumps(tree[key]))
        return "{" + ",".join(members) + "}"
    if isinstance(tree, list):
        items = [_dump(value, (*path, str(i)), target, key) for i, value in enumerate(tree)]
        return "[" + ",".join(items) + "]"
    return json.dumps(tree)


_MEMBERS = _objects(minimal_tree())


@BOUNDED
@given(st.sampled_from(_MEMBERS))
def test_t1_property_duplicate_member_is_located_wherever_planted(
    member: tuple[tuple[str, ...], str],
) -> None:
    target, key = member
    payload = _dump(minimal_tree(), (), target, key).encode("utf-8")
    with forbid_effects(), pytest.raises(ValidationError) as caught:
        load_document(payload)
    assert caught.value.context["reason"] == "duplicate_key"
    expected = "/" + "/".join((*target, key))  # no "~" or "/" in the example's names
    assert expected in pointers(caught.value)


_INTEGER_FIELDS = (
    ("seed",),
    ("revision",),
    ("canvas", "width"),
    ("layers", "0", "opacity"),
    ("layers", "0", "operations", "0", "box", "2"),
)


def _set(tree: Any, path: tuple[str, ...], value: object) -> None:
    for step in path[:-1]:
        tree = tree[int(step)] if isinstance(tree, list) else tree[step]
    last = path[-1]
    if isinstance(tree, list):
        tree[int(last)] = value
    else:
        tree[last] = value


@BOUNDED
@given(
    st.sampled_from(_INTEGER_FIELDS),
    st.sampled_from(["NaN", "Infinity", "-Infinity"]),
)
def test_t1_property_nan_and_infinity_are_rejected_anywhere(
    field: tuple[str, ...], token: str
) -> None:
    tree = minimal_tree()
    _set(tree, field, SECRET)
    payload = json.dumps(tree).replace(json.dumps(SECRET), token).encode("utf-8")
    with forbid_effects(), pytest.raises(ValidationError) as caught:
        load_document(payload)
    assert caught.value.context["reason"] == "non_finite_number"


@BOUNDED
@given(
    st.sampled_from(_INTEGER_FIELDS),
    st.integers(309, 100_000),
    st.booleans(),
)
def test_t1_property_overflowing_numbers_never_become_values(
    field: tuple[str, ...], exponent: int, negative: bool
) -> None:
    tree = minimal_tree()
    _set(tree, field, SECRET)
    number = ("-" if negative else "") + f"1e{exponent}"
    payload = json.dumps(tree).replace(json.dumps(SECRET), number).encode("utf-8")
    with forbid_effects(), pytest.raises(ValidationError) as caught:
        load_document(payload)
    assert "/" + "/".join(field) in pointers(caught.value)


@BOUNDED
@given(st.binary(max_size=512))
def test_t1_property_arbitrary_bytes_fail_only_with_domain_errors(payload: bytes) -> None:
    with forbid_effects():
        try:
            load_document(payload)
        except MoanaError as error:
            assert_clean_error(error, SECRET)


@BOUNDED
@given(st.data())
def test_t1_property_mutated_documents_fail_only_with_domain_errors(data: st.DataObject) -> None:
    original = bytearray(minimal_bytes())
    for _ in range(data.draw(st.integers(1, 8))):
        index = data.draw(st.integers(0, len(original) - 1))
        original[index] = data.draw(st.integers(0, 255))
    with forbid_effects():
        try:
            document = load_document(bytes(original))
        except MoanaError:
            return
    assert isinstance(document, Document)


def test_t1_self_referencing_mappings_fail_the_depth_limit() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    as_list: list[object] = []
    as_list.append(as_list)
    hidden = minimal_tree()
    hidden["layers"] = as_list
    for source in (cyclic, hidden):
        with forbid_effects(), pytest.raises(ValidationError) as caught:
            load_document(source)
        assert caught.value.context["reason"] == "too_deep"


# --- references: cycles, depth and identity --------------------------------------------


def _with_masks(masks: list[dict[str, object]], layer_mask: str | None = None) -> dict[str, Any]:
    tree = minimal_tree()
    tree["masks"] = masks
    if layer_mask is not None:
        tree["layers"][0]["mask_id"] = layer_mask
    return tree


@BOUNDED
@given(st.integers(1, 24), st.data())
def test_t1_property_mask_reference_cycles_never_reach_the_renderer(
    length: int, data: st.DataObject
) -> None:
    names = [f"m{index}" for index in range(length)]
    order = data.draw(st.permutations(names))
    masks: list[dict[str, object]] = [
        {"id": order[i], "type": "union", "masks": [order[(i + 1) % length], "leaf"]}
        for i in range(length)
    ]
    masks.append({"id": "leaf", "type": "rect", "box": [0, 0, 4, 4]})
    tree = _with_masks(masks, layer_mask=order[0])
    with forbid_effects(), pytest.raises(ReferenceError) as caught:
        render(load_document(tree))
    # Oracle by construction: every union of the ring names the next one first, so each
    # member of the cycle is reported at its first operand, and nothing else is.
    assert reasons(caught.value) - {None} == {"mask_cycle"}
    expected = {f"/masks/{index}/masks/0" for index in range(length)}
    assert pointers(caught.value) - {None} == expected


def test_t1_mask_reference_chain_beyond_depth_16_is_rejected() -> None:
    chain: list[dict[str, object]] = [
        {"id": f"m{index}", "type": "union", "masks": [f"m{index + 1}", "leaf"]}
        for index in range(16)
    ]
    chain.append({"id": "m16", "type": "rect", "box": [0, 0, 1, 1]})  # 17 levels
    chain.append({"id": "leaf", "type": "rect", "box": [1, 1, 2, 2]})
    with forbid_effects(), pytest.raises(ValidationError) as caught:
        render(load_document(_with_masks(chain, layer_mask="m0")))
    assert_clean_error(caught.value, SECRET)
    (detail,) = caught.value.details
    assert (detail.json_pointer, detail.context["reason"]) == ("/masks/0", "too_deep")
    assert detail.context["maximum"] == 16  # MOANA.md section 11
    accepted = chain[1:]  # 16 levels: the contract maximum loads
    load_document(_with_masks(accepted, layer_mask="m1"))


def test_t1_hidden_references_cannot_alias_or_dangle() -> None:
    hostile_id = SECRET.replace("-", "_")
    dangling = _with_masks([], layer_mask=hostile_id)
    with forbid_effects(), pytest.raises(ReferenceError) as caught:
        load_document(dangling)
    assert_clean_error(caught.value, hostile_id)  # the unknown ID is never echoed
    assert reasons(caught.value) - {None} == {"unknown_mask"}
    assert "/layers/0/mask_id" in pointers(caught.value)
    aliased = _with_masks([{"id": "ink", "type": "rect", "box": [0, 0, 1, 1]}])
    with forbid_effects(), pytest.raises(ValidationError) as caught_alias:
        load_document(aliased)  # a mask may not reuse a palette colour ID
    assert reasons(caught_alias.value) - {None} == {"duplicate_id"}
    assert "/masks/0/id" in pointers(caught_alias.value)


# --- documents are data: no code path can evaluate them --------------------------------

_FORBIDDEN_CALLS = frozenset({"eval", "exec", "compile", "__import__"})
_FORBIDDEN_MODULES = frozenset(
    {"pickle", "marshal", "shelve", "subprocess", "socket", "urllib", "http", "ctypes"}
)


def _constant_names(tree: ast.Module) -> set[str]:
    """Module-level names bound to a string literal (``_MODULE: Final = "aggdraw"``)."""
    names: set[str] = set()
    for node in tree.body:
        value: ast.expr | None
        targets: list[ast.expr]
        if isinstance(node, ast.Assign):
            value, targets = node.value, node.targets
        elif isinstance(node, ast.AnnAssign):
            value, targets = node.value, [node.target]
        else:
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _dynamic_import(node: ast.Call, constants: set[str]) -> bool:
    """An ``import_module`` whose module name is not a literal fixed in the source."""
    function = node.func
    name = function.attr if isinstance(function, ast.Attribute) else None
    if name != "import_module":
        return False
    argument = node.args[0] if node.args else None
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return False
    return not (isinstance(argument, ast.Name) and argument.id in constants)


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    constants = _constant_names(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _dynamic_import(node, constants):
            found.append(f"{path.name}:{node.lineno} import_module(<variable>)")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _FORBIDDEN_CALLS:
                found.append(f"{path.name}:{node.lineno} {node.func.id}()")
        elif isinstance(node, ast.Import):
            found.extend(
                f"{path.name}:{node.lineno} import {alias.name}"
                for alias in node.names
                if alias.name.split(".")[0] in _FORBIDDEN_MODULES
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.split(".")[0] in _FORBIDDEN_MODULES
        ):
            found.append(f"{path.name}:{node.lineno} from {node.module}")
    return found


def test_ac1_engine_has_no_evaluation_deserialisation_or_network_path() -> None:
    sources = sorted((ROOT / "src/moana").rglob("*.py"))
    assert sources
    violations = [item for path in sources for item in _violations(path)]
    assert violations == []


def test_t1_code_like_strings_stay_inert_data(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    tree = minimal_tree()
    tree["layers"][0]["name"] = f"__import__('pathlib').Path({str(marker)!r}).touch()"
    document = load_document(tree)
    render(document)
    assert document.layers[0].name == tree["layers"][0]["name"]
    assert not marker.exists()
