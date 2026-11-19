"""Threat-model coverage of MOANA-030: each boundary, its tests and the mitigation exercised.

Keys are the *Frontera* column of ``docs/architecture/SECURITY_MODEL.md``;
``test_threat_coverage.py`` fails when a boundary has no entry, an entry names a test
that does not exist, or ``tests/security/README.md`` omits one of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["COVERAGE", "Coverage"]


@dataclass(frozen=True, slots=True)
class Coverage:
    """Tests (``module::function``) that exercise one mitigation of a boundary."""

    mitigation: str
    tests: tuple[str, ...]


COVERAGE: Final[dict[str, Coverage]] = {
    "JSON → modelo": Coverage(
        "bytes, profundidad y nodos antes de json.loads; duplicados, NaN/Infinity y "
        "desbordes rechazados; extra forbid; sin eval/pickle/red",
        (
            "test_corpus::test_ac1_t1_corpus_case_is_rejected_before_buffers_and_io",
            "test_documents::test_t1_property_nesting_beyond_32_is_rejected_before_parsing",
            "test_documents::test_t1_node_count_and_size_are_checked_before_parsing",
            "test_documents::test_t1_project_manifest_shape_is_checked_before_parsing",
            "test_documents::test_t1_property_duplicate_member_is_located_wherever_planted",
            "test_documents::test_t1_property_nan_and_infinity_are_rejected_anywhere",
            "test_documents::test_t1_property_overflowing_numbers_never_become_values",
            "test_documents::test_t1_property_arbitrary_bytes_fail_only_with_domain_errors",
            "test_documents::test_ac1_engine_has_no_evaluation_deserialisation_or_network_path",
            "test_documents::test_t1_code_like_strings_stay_inert_data",
        ),
    ),
    "modelo → plan": Coverage(
        "contrato de coordenadas/dimensiones en el modelo y coste antes de buffers",
        (
            "test_budgets::test_t1_coordinates_beyond_the_contract_are_rejected_by_the_model",
            "test_budgets::test_t1_canvas_area_beyond_the_contract_is_rejected_by_the_model",
            "test_budgets::test_t1_huge_unclipped_lines_are_charged_before_clipping",
            "test_budgets::test_t2_lowered_geometry_limits_reject_before_allocation",
        ),
    ),
    "resolución → render": Coverage(
        "DAG de máscaras, profundidad 16, IDs globales únicos y referencias resueltas",
        (
            "test_documents::test_t1_property_mask_reference_cycles_never_reach_the_renderer",
            "test_documents::test_t1_mask_reference_chain_beyond_depth_16_is_rejected",
            "test_documents::test_t1_hidden_references_cannot_alias_or_dangle",
            "test_documents::test_t1_self_referencing_mappings_fail_the_depth_limit",
        ),
    ),
    "plan → raster": Coverage(
        "presupuesto de bytes, visitas, operaciones, frames y deadline antes de reservar",
        (
            "test_budgets::test_t2_property_canvas_over_the_byte_budget_never_allocates",
            "test_budgets::test_t2_property_canvas_over_the_visit_budget_never_allocates",
            "test_budgets::test_t2_operation_count_is_budgeted_before_rasterising",
            "test_budgets::test_t2_budget_cannot_be_raised_by_a_request_without_the_host",
            "test_budgets::test_t2_expired_deadline_stops_before_any_buffer",
            "test_budgets::test_t2_hostile_canvas_is_rejected_within_bounded_memory",
            "test_budgets::test_t2_animation_over_the_frame_budget_renders_no_frame",
            "test_budgets::test_t2_export_over_budget_writes_nothing_and_allocates_nothing",
        ),
    ),
    "asset → Pillow": Coverage(
        "IHDR, contrato 2048 y presupuesto de píxeles antes de Pillow; límites de Pillow "
        "intactos; digest antes del decode",
        (
            "test_assets_integrity::test_t2_bomb_headers_are_rejected_before_pillow",
            "test_assets_integrity::test_t2_pixel_budget_is_checked_from_the_header",
            "test_assets_integrity::"
            "test_t2_idat_expanding_beyond_the_header_decodes_only_declared_pixels",
            "test_assets_integrity::test_t2_pillow_bomb_protection_stays_active_and_is_mapped",
            "test_assets_integrity::test_t2_loading_projects_never_changes_pillow_limits",
            "test_assets_integrity::test_t2_checksum_failure_of_any_stored_file_loads_nothing",
            "test_corpus::test_ac1_t1_corpus_case_is_rejected_before_buffers_and_io",
        ),
    ),
    "spritesheet → frames": Coverage(
        "manifiesto acotado (1 MiB) y estricto (duplicados), IHDR del atlas y presupuesto "
        "antes del decode, rects dentro del atlas, digests de atlas y frames",
        (
            "test_corpus::test_ac1_t1_corpus_case_is_rejected_before_buffers_and_io",
            "test_assets_integrity::test_t2_tampered_spritesheet_atlas_fails_its_digests",
        ),
    ),
    "ZIP → filesystem": Coverage(
        "directorio central inspeccionado antes de descomprimir; nombres, enlaces, ratio, "
        "total expandido, entradas y lecturas acotadas; nunca se extrae a disco",
        (
            "test_archives::test_t1_property_traversal_names_are_refused_before_extraction",
            "test_archives::test_t1_symlink_entry_is_refused_even_with_a_layout_name",
            "test_archives::test_t1_expanded_total_is_budgeted_before_any_entry_is_decompressed",
            "test_archives::test_t1_declared_ratio_bomb_is_refused_before_decompression",
            "test_archives::test_t1_entry_count_is_budgeted_from_the_end_record",
            "test_archives::test_t2_oversized_sources_are_read_only_up_to_their_bound",
            "test_assets_integrity::test_t2_tampered_archive_entry_fails_its_crc",
        ),
    ),
    "export/project → disco": Coverage(
        "temporal hermano, commit atómico, sin overwrite implícito, presupuesto antes de "
        "escribir, enlaces rechazados, digests verificados al cargar",
        (
            "test_persistence::test_t2_property_injected_io_failure_keeps_the_previous_output",
            "test_persistence::test_t2_existing_destination_is_never_replaced_implicitly",
            "test_persistence::test_t2_save_budget_is_checked_before_any_write",
            "test_persistence::test_t2_migration_into_an_existing_project_keeps_both_sides",
            "test_persistence::test_t2_linked_project_directory_never_redirects_writes",
            "test_assets_integrity::test_t2_checksum_failure_of_any_stored_file_loads_nothing",
            "test_assets_integrity::test_t2_preserved_migration_original_is_verified",
            "test_assets_integrity::test_t2_manifest_rewritten_without_its_history_is_rejected",
            "test_assets_integrity::test_t2_property_any_flipped_byte_is_detected_or_harmless",
        ),
    ),
    "batch → documento": Coverage(
        "base_revision + base_snapshot y aplicación transaccional; historial acotado",
        (
            "test_editing::test_t2_property_failing_command_anywhere_mutates_nothing",
            "test_editing::test_t2_stale_batch_is_a_conflict_without_side_effects",
            "test_editing::test_t2_history_budget_rejects_before_adding",
            "test_editing::test_t2_hostile_frame_override_fails_before_any_frame_buffer",
        ),
    ),
    "instalación/CI": Coverage(
        "lock con hashes SHA-256 de PyPI, CI con token de lectura, acciones fijadas por SHA",
        (
            "test_supply_chain::test_ac1_every_locked_artifact_is_pinned_by_sha256",
            "test_supply_chain::test_ac1_ci_has_a_read_only_token_pinned_actions_and_no_secrets",
            "test_supply_chain::test_ac1_uses_pinning_accepts_only_local_commit_or_digest",
        ),
    ),
}
"""Boundary → mitigation and tests. Cross-cutting checks (error hygiene in
``test_errors``, tripwire controls in ``test_guards``) apply to every boundary."""
