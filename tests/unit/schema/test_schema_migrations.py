"""MOANA-021: version registry and pure document migrations (ADR-031).

The 0.8 and 0.9 formats are test-only (``tests/fixtures/migration/formats.py``): they
were never published, and the production registry knows schema 1.0 only.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import moana
from moana.core.errors import UnsupportedVersion, ValidationError
from moana.core.limits import MAX_MIGRATION_STEPS
from moana.render import ESTIMATOR_VERSION, RENDERER_VERSION, render
from moana.schema import (
    DOCUMENT_MIGRATIONS,
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    Migration,
    MigrationRegistry,
    ParseLimits,
    canonical_json,
    document_ids,
    migrate_document,
    parse_version,
    validate_document,
)
from tests.fixtures.migration.formats import (
    EXPECTED,
    MARKER,
    OLDEST,
    PREVIOUS,
    STEP_09_10,
    TEST_ONLY_MIGRATIONS,
)


def _tree(path: Any) -> dict[str, Any]:
    tree: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return tree


def _identity(tree: dict[str, object]) -> Mapping[str, object]:
    return tree


_NOT_CALLABLE: Any = 1


# --- the registry -------------------------------------------------------------------


def test_t1_production_registry_claims_no_unpublished_format() -> None:
    assert DOCUMENT_MIGRATIONS.current == SCHEMA_VERSION == "1.0"
    assert DOCUMENT_MIGRATIONS.migrations == ()
    assert DOCUMENT_MIGRATIONS.versions == frozenset({"1.0"}) == SUPPORTED_SCHEMA_VERSIONS
    for version in ("0.8", "0.9"):
        with pytest.raises(UnsupportedVersion) as caught:
            DOCUMENT_MIGRATIONS.path(version)
        assert caught.value.context["reason"] == "unsupported_version"
    assert TEST_ONLY_MIGRATIONS.versions == frozenset({"0.8", "0.9", "1.0"})


def test_t1_format_versions_are_distinct_from_package_and_renderer() -> None:
    # Package, renderer and estimator versions never select a migration.
    assert moana.__version__ == "0.1.0rc1"
    assert RENDERER_VERSION == "render-v1"
    assert ESTIMATOR_VERSION.startswith("budget-v")
    for other in (moana.__version__, RENDERER_VERSION, ESTIMATOR_VERSION):
        assert parse_version(other) is None
        assert other not in DOCUMENT_MIGRATIONS.versions


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.0", (1, 0)),
        ("0.9", (0, 9)),
        ("12.34", (12, 34)),
        ("01.0", None),
        ("1", None),
        ("1.0.0", None),
        ("v1.0", None),
        ("10000.0", None),
        (1.0, None),
    ],
)
def test_t1_parse_version(text: object, expected: tuple[int, int] | None) -> None:
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    ("version", "relation"),
    [("1.1", "future"), ("2.0", "future"), ("0.7", "past"), ("latest", "unknown")],
)
def test_t1_future_and_unknown_versions_are_rejected(
    minimal: dict[str, Any], version: str, relation: str
) -> None:
    minimal["schema_version"] = version
    minimal["unknown_member"] = True  # the grammar of that version is not reported
    for call in (
        lambda: validate_document(minimal),
        lambda: migrate_document(minimal, registry=TEST_ONLY_MIGRATIONS),
    ):
        with pytest.raises(UnsupportedVersion) as caught:
            call()
        error = caught.value
        assert error.json_pointer == "/schema_version"
        assert error.context == {
            "field": "schema_version",
            "reason": "unsupported_version",
            "relation": relation,
            "supported": ("1.0",),
        }
        assert version not in error.message and version not in repr(error.context)


def test_t1_registered_older_version_requires_explicit_migration() -> None:
    tree = _tree(PREVIOUS)
    with pytest.raises(UnsupportedVersion) as caught:
        TEST_ONLY_MIGRATIONS.check(tree)
    assert caught.value.context == {
        "field": "schema_version",
        "reason": "migration_required",
        "supported": ("1.0",),
        "target": "1.0",
        "migrations": ("test-only-0-9-to-1-0",),
    }
    TEST_ONLY_MIGRATIONS.check(_tree(EXPECTED))
    TEST_ONLY_MIGRATIONS.check({"schema_version": 1})  # left to structural validation
    # The production reader does not know the test-only version at all.
    with pytest.raises(UnsupportedVersion) as caught:
        validate_document(tree)
    assert caught.value.context["reason"] == "unsupported_version"


@pytest.mark.parametrize(
    ("build", "error"),
    [
        (lambda: Migration(id="Bad", source="0.9", target="1.0", apply=_identity), ValueError),
        (lambda: Migration(id="m", source="1.0", target="1.0", apply=_identity), ValueError),
        (lambda: Migration(id="m", source="1.0", target="0.9", apply=_identity), ValueError),
        (lambda: Migration(id="m", source="x", target="1.0", apply=_identity), ValueError),
        (lambda: Migration(id="m", source="0.9", target="1.0", apply=_NOT_CALLABLE), TypeError),
        (lambda: MigrationRegistry(member="version", current="1.0"), ValueError),
        (lambda: MigrationRegistry(member="schema_version", current="one"), ValueError),
        (
            lambda: MigrationRegistry(
                member="schema_version",
                current="1.0",
                migrations=[STEP_09_10],  # type: ignore[arg-type]  # deliberate misuse
            ),
            TypeError,
        ),
        (
            lambda: MigrationRegistry(
                member="schema_version", current="1.0", migrations=(STEP_09_10, STEP_09_10)
            ),
            ValueError,
        ),
        (
            lambda: MigrationRegistry(
                member="schema_version",
                current="1.0",
                migrations=(Migration(id="m", source="0.9", target="2.0", apply=_identity),),
            ),
            ValueError,
        ),
        (
            lambda: MigrationRegistry(
                member="schema_version",
                current="1.0",
                migrations=(Migration(id="m", source="0.8", target="0.9", apply=_identity),),
            ),
            ValueError,
        ),
    ],
)
def test_t1_registry_is_checked_on_construction(build: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        build()


def test_t1_chains_longer_than_the_limit_are_rejected() -> None:
    def chain(length: int) -> tuple[Migration, ...]:
        steps = [
            Migration(id=f"m{index}", source=f"0.{index}", target=f"0.{index + 1}", apply=_identity)
            for index in range(length - 1)
        ]
        last = Migration(id="last", source=f"0.{length - 1}", target="1.0", apply=_identity)
        return (*steps, last)

    accepted = MigrationRegistry(
        member="schema_version", current="1.0", migrations=chain(MAX_MIGRATION_STEPS)
    )
    assert len(accepted.path("0.0")) == MAX_MIGRATION_STEPS
    with pytest.raises(ValueError, match="does not reach"):
        MigrationRegistry(
            member="schema_version", current="1.0", migrations=chain(MAX_MIGRATION_STEPS + 1)
        )


# --- migration ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "steps"),
    [
        (PREVIOUS, ("test-only-0-9-to-1-0",)),
        (OLDEST, ("test-only-0-8-to-0-9", "test-only-0-9-to-1-0")),
    ],
    ids=["0.9", "0.8"],
)
def test_ac1_test_only_fixture_migrates_to_v1_keeping_semantics_and_render(
    fixture: Any, steps: tuple[str, ...]
) -> None:
    source = _tree(fixture)
    original = copy.deepcopy(source)
    migration = migrate_document(source, registry=TEST_ONLY_MIGRATIONS)
    assert source == original  # pure: the input is never modified
    assert migration.steps == steps
    assert migration.source_version == fixture.name.removeprefix("test-only-")[:3]
    assert migration.target_version == "1.0"
    # Oracle: the hand-written 1.0 equivalent of the fixture.
    expected = validate_document(_tree(EXPECTED))
    assert canonical_json(migration.document) == canonical_json(expected)
    assert document_ids(migration.document) == {
        "legacy_sprite",
        "legacy_palette",
        "ink",
        "cloth",
        "body",
        "body_fill",
        "eye",
    }
    result = render(migration.document)
    assert result.digest == render(expected).digest

    def pixel(x: int, y: int) -> bytes:
        offset = (y * result.width + x) * 4
        return result.rgba[offset : offset + 4]

    assert pixel(2, 3) == pixel(9, 11) == bytes.fromhex("36AFA5FF")  # rect [2,3,10,12)
    assert pixel(5, 6) == bytes.fromhex("182338FF")  # the pixel drawn after the rect
    assert pixel(10, 12) == pixel(1, 3) == bytes(4)  # half-open box, transparent outside


def test_t1_migrating_the_destination_again_is_the_identity() -> None:
    first = migrate_document(_tree(OLDEST), registry=TEST_ONLY_MIGRATIONS)
    again = migrate_document(
        json.loads(canonical_json(first.document)), registry=TEST_ONLY_MIGRATIONS
    )
    assert again.steps == ()
    assert again.source_version == again.target_version == "1.0"
    assert again.document == first.document
    # With the production registry, a current document is just validated.
    assert migrate_document(_tree(EXPECTED)).steps == ()


def test_t1_step_failures_are_domain_errors() -> None:
    not_test_only = _tree(PREVIOUS)
    del not_test_only[MARKER]
    with pytest.raises(ValidationError) as caught:
        migrate_document(not_test_only, registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context == {
        "field": "schema_version",
        "reason": "migration_failed",
        "migration": "test-only-0-9-to-1-0",
    }

    def returns_list(tree: dict[str, object]) -> Mapping[str, object]:
        return [tree]  # type: ignore[return-value]  # deliberate misuse

    broken = MigrationRegistry(
        member="schema_version",
        current="1.0",
        migrations=(Migration(id="broken", source="0.9", target="1.0", apply=returns_list),),
    )
    with pytest.raises(ValidationError) as caught:
        migrate_document(_tree(PREVIOUS), registry=broken)
    assert caught.value.context["migration"] == "broken"


def test_t1_intermediate_trees_stay_bounded() -> None:
    def inflate(tree: dict[str, object]) -> Mapping[str, object]:
        return {**tree, "padding": list(range(100))}

    inflating = MigrationRegistry(
        member="schema_version",
        current="1.0",
        migrations=(Migration(id="inflate", source="0.9", target="1.0", apply=inflate),),
    )
    with pytest.raises(ValidationError) as caught:
        migrate_document(_tree(PREVIOUS), registry=inflating, limits=ParseLimits(max_nodes=80))
    assert caught.value.context == {
        "field": "schema_version",
        "reason": "migration_failed",
        "migration": "inflate",
        "cause": "too_many_nodes",
    }


def _cyclic(tree: dict[str, object]) -> Mapping[str, object]:
    tree["self"] = tree
    return tree


def _non_json(tree: dict[str, object]) -> Mapping[str, object]:
    return {**tree, "tags": {"a", "b"}}


@pytest.mark.parametrize(("apply", "cause"), [(_cyclic, "too_deep"), (_non_json, "invalid_value")])
def test_t1_hostile_step_output_is_a_migration_failure(
    apply: Callable[[dict[str, object]], Mapping[str, object]], cause: str
) -> None:
    registry = MigrationRegistry(
        member="schema_version",
        current="1.0",
        migrations=(Migration(id="hostile", source="0.9", target="1.0", apply=apply),),
    )
    with pytest.raises(ValidationError) as caught:
        migrate_document(_tree(PREVIOUS), registry=registry)
    assert caught.value.context["reason"] == "migration_failed"
    assert caught.value.context["migration"] == "hostile"
    assert caught.value.context["cause"] == cause


def _set_member(tree: dict[str, Any], pointer: tuple[str | int, ...], value: object) -> None:
    *parents, last = pointer
    node: Any = tree
    for token in parents:
        node = node[token]
    node[last] = value


@pytest.mark.parametrize(
    ("fixture", "pointer", "value", "migration"),
    [
        (OLDEST, ("canvas",), "x", "test-only-0-8-to-0-9"),
        (OLDEST, ("canvas",), 5, "test-only-0-8-to-0-9"),
        (OLDEST, ("canvas",), None, "test-only-0-8-to-0-9"),
        (OLDEST, ("canvas", "size"), [16], "test-only-0-8-to-0-9"),
        (PREVIOUS, ("palette", "colors"), "ab", "test-only-0-9-to-1-0"),
        (PREVIOUS, ("palette", "colors"), [1], "test-only-0-9-to-1-0"),
        (PREVIOUS, ("layers",), [5], "test-only-0-9-to-1-0"),
        (PREVIOUS, ("palette",), None, "test-only-0-9-to-1-0"),
    ],
)
def test_t1_malformed_test_only_sources_fail_with_the_step_id(
    fixture: Any, pointer: tuple[str | int, ...], value: object, migration: str
) -> None:
    tree = _tree(fixture)
    _set_member(tree, pointer, value)
    with pytest.raises(ValidationError) as caught:
        migrate_document(tree, registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context["reason"] == "migration_failed"
    assert caught.value.context["migration"] == migration
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_t1_step_exceptions_never_leak_document_data() -> None:
    def leaky(tree: dict[str, object]) -> Mapping[str, object]:
        raise RecursionError("secret-token " + json.dumps(tree))

    def domain(tree: dict[str, object]) -> Mapping[str, object]:
        raise UnsupportedVersion("nested", context={"reason": "own"})

    for apply, expected in ((leaky, ValidationError), (domain, UnsupportedVersion)):
        registry = MigrationRegistry(
            member="schema_version",
            current="1.0",
            migrations=(Migration(id="step", source="0.9", target="1.0", apply=apply),),
        )
        with pytest.raises(expected) as caught:
            migrate_document(_tree(PREVIOUS), registry=registry)
        error = caught.value
        assert "secret" not in error.message and "secret" not in repr(error.context)
        assert error.__cause__ is None
        if expected is ValidationError:
            assert error.__suppress_context__
        else:
            assert error.context == {"reason": "own"}  # a MoanaError keeps its own code


def test_t1_non_json_input_is_rejected_before_any_step() -> None:
    tree = _tree(PREVIOUS)
    tree["layers"][0]["tags"] = {"mutable"}
    snapshot = copy.deepcopy(tree)
    with pytest.raises(ValidationError) as caught:
        migrate_document(tree, registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.context == {"reason": "invalid_value"}
    assert caught.value.json_pointer == "/layers/0/tags"
    assert tree == snapshot
    escaped = _tree(PREVIOUS)
    escaped["a/b~c"] = object()
    with pytest.raises(ValidationError) as caught:
        migrate_document(escaped, registry=TEST_ONLY_MIGRATIONS)
    assert caught.value.json_pointer == "/a~1b~0c"


def test_t1_migration_result_is_validated() -> None:
    def keep_marker(tree: dict[str, object]) -> Mapping[str, object]:
        return tree  # leaves 0.9 members: the 1.0 grammar rejects them

    lazy = MigrationRegistry(
        member="schema_version",
        current="1.0",
        migrations=(Migration(id="lazy", source="0.9", target="1.0", apply=keep_marker),),
    )
    with pytest.raises(ValidationError):
        migrate_document(_tree(PREVIOUS), registry=lazy)


def test_t1_registry_must_target_the_current_document_schema() -> None:
    with pytest.raises(TypeError):
        migrate_document(_tree(EXPECTED), registry=_NOT_CALLABLE)
    envelope = MigrationRegistry(member="project_version", current="1.0")
    with pytest.raises(TypeError):
        migrate_document(_tree(EXPECTED), registry=envelope)
    with pytest.raises(ValueError, match="current schema"):
        migrate_document(
            _tree(EXPECTED), registry=MigrationRegistry(member="schema_version", current="2.0")
        )


@pytest.mark.parametrize("version", [1, 1.0, True, None, "absent"])
def test_t1_non_string_version_is_left_to_validation(version: object) -> None:
    tree = _tree(EXPECTED)
    if version == "absent":
        del tree["schema_version"]
    else:
        tree["schema_version"] = version
    for call in (
        lambda: migrate_document(tree, registry=TEST_ONLY_MIGRATIONS),
        lambda: validate_document(tree),
    ):
        with pytest.raises(ValidationError) as caught:
            call()
        assert not isinstance(caught.value, UnsupportedVersion)


@pytest.mark.parametrize(
    "version", ["1.0 ", " 1.0", "1.00", "", "1.0\n", "\uff11.\uff10", "1,0", "1.0.0"]
)
def test_t1_version_spelling_variants_are_unknown(minimal: dict[str, Any], version: str) -> None:
    assert parse_version(version) is None
    minimal["schema_version"] = version
    with pytest.raises(UnsupportedVersion) as caught:
        validate_document(minimal)
    assert caught.value.context["relation"] == "unknown"


def test_t1_supported_versions_have_one_source() -> None:
    assert frozenset({DOCUMENT_MIGRATIONS.current}) == SUPPORTED_SCHEMA_VERSIONS


_ID = st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True)
_HEX = st.from_regex(r"#[0-9A-F]{8}", fullmatch=True)


@settings(max_examples=40, deadline=None)
@given(
    rects=st.lists(
        st.tuples(st.integers(0, 15), st.integers(0, 15), st.integers(1, 16), st.integers(1, 16)),
        min_size=1,
        max_size=6,
    ),
    colors=st.lists(_HEX, min_size=1, max_size=4),
    seed=st.integers(0, 2**64 - 1),
    layer=_ID,
)
def test_t1_property_migration_preserves_ids_and_is_idempotent(
    rects: list[tuple[int, int, int, int]], colors: list[str], seed: int, layer: str
) -> None:
    tree = _tree(PREVIOUS)
    tree["seed"] = seed
    tree["canvas"]["profile"] = "rgba"
    tree["palette"]["colors"] = [
        {"id": f"c{index}", "value": rgba} for index, rgba in enumerate(colors)
    ]
    operations = [
        {
            "id": f"op{index}",
            "type": "rect",
            "box": [x, y, max(x + 1, x1), max(y + 1, y1)],
            "color": f"c{index % len(colors)}",
        }
        for index, (x, y, x1, y1) in enumerate(rects)
    ]
    tree["layers"] = [{"id": f"layer_{layer}", "name": layer, "ops": operations}]
    first = migrate_document(tree, registry=TEST_ONLY_MIGRATIONS)
    second = migrate_document(tree, registry=TEST_ONLY_MIGRATIONS)
    assert canonical_json(first.document) == canonical_json(second.document)  # deterministic
    assert [op.id for op in first.document.layers[0].operations] == [op["id"] for op in operations]
    assert [color.rgba for color in first.document.palette.colors] == colors
    again = migrate_document(
        json.loads(canonical_json(first.document)), registry=TEST_ONLY_MIGRATIONS
    )
    assert again.steps == () and again.document == first.document
    # Independent oracle: the same inputs written by hand in 1.0.
    expected = _tree(EXPECTED)
    expected["seed"] = seed
    expected["canvas"]["profile"] = "rgba"
    expected["palette"]["colors"] = [
        {"id": f"c{index}", "rgba": rgba} for index, rgba in enumerate(colors)
    ]
    expected["layers"] = [{"id": f"layer_{layer}", "name": layer, "operations": operations}]
    oracle = validate_document(expected)
    assert canonical_json(first.document) == canonical_json(oracle)
    assert render(first.document).digest == render(oracle).digest
