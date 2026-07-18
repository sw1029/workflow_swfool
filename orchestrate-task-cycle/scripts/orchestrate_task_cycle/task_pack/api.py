#!/usr/bin/env python3
"""Stable import and CLI facade for the modular task-pack implementation."""
from __future__ import annotations

# The imports below intentionally preserve the historical module namespace.
# ruff: noqa: F401

# Preserve the historical module-level imports used by downstream callers.
import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from . import replacement_engine as task_pack_replacement
from . import mutation_journal as task_pack_mutation_journal
from .cli import main
from .coherence import (
    _coherence_field_declared,
    _coherence_value,
    _pack_coherence_contract_version,
    pack_coherence_contract_version,
    validate_pack_coherence_contract,
)
from .consumption import (  # noqa: E402
    _command_mark_consumed_locked,
    command_mark_consumed,
)
from .contracts import (  # noqa: E402
    AUTHORITY_RECEIPT_SOURCE_KINDS,
    AUTHORITY_RECEIPT_TEMPORALITIES,
    CONTEMPORANEOUS_AUTHORITY_SOURCE_KINDS,
    CREATION_SNAPSHOT_CANONICALIZATION_VERSION,
    INITIAL_SELECTION_RECEIPT_VERSION,
    ISSUE_MUTATION_STATUSES,
    ISSUE_NOOP_STATUSES,
    ITEM_KIND_PATTERN,
    ITEM_STATUSES,
    OPEN_RESIDUAL_STATUSES,
    PACK_COHERENCE_MUTATIONS,
    PACK_COHERENCE_VERSION,
    PACK_ID_PATTERN,
    PACK_STATUSES,
    PROGRESS_KINDS,
    PROGRESS_TARGETS,
    PROMOTION_ORIGINS,
    PROMOTION_TERMINAL_EXECUTION_STATUSES,
    PROMOTION_VALIDATION_VERDICTS,
    RETIREMENT_BASES,
    SHA256_PATTERN,
    VALIDATION_PROFILES,
    VERDICT_AXES,
    VERDICT_AXIS_STATUSES,
    _CONTENT_ADDRESSED_WRITE_STATE,
    _PACK_MUTATION_THREAD_LOCK,
    normalize_action,
)
from .creation import (  # noqa: E402
    apply_initial_selection_to_new_pack,
    item_planning_contract,
    item_planning_contract_sha256,
    validate_carry_forward_contract,
    validate_retired_items_contract,
)
from .mutation_apply import (  # noqa: E402
    _command_apply_mutation_locked,
    command_apply_mutation,
)
from .legacy_retirement import (  # noqa: E402
    active_retirement_for_pack,
    command_activate_legacy_retirement,
    command_retire_legacy,
    require_pack_not_retired,
    retirement_store_projection,
    validate_activation_binding,
    validate_completion_binding,
)
from .ordering import (  # noqa: E402
    active_in_flight_items,
    evidence_paths_from,
    item_order,
    next_item,
    planned_items,
    refresh_current_item,
    renumber_items,
    sorted_items,
)
from .packet_io import (  # noqa: E402
    load_bound_packet,
    load_json,
    load_plan,
    non_empty,
    normalized_string_list,
    packet_field,
    preserve_verdict_axes,
    require_file_digest,
    scope_fidelity_records,
    truthy,
    verdict_axis_status,
    verify_evidence_files,
    write_bytes_atomic,
    write_content_addressed_file,
    write_json,
)
from .presentation import (  # noqa: E402
    _command_next_locked,
    _command_status_locked,
    _command_validate_locked,
    capability_contract,
    command_capabilities,
    command_next,
    command_recover_replacement,
    command_render,
    command_status,
    command_validate,
)
from .provenance import (  # noqa: E402
    _issue_identifier_present,
    _require_empty_packet_blockers,
    _require_packet_not_blocked,
    _require_packet_task,
    consume_in_flight_for_atomic_promotion,
    mutation_entry,
    validate_initial_selection_provenance,
    validate_promotion_provenance,
)
from .receipts import (  # noqa: E402
    _forbidden_receipt_key_paths,
    _required_sha256,
    load_bound_authority_receipt,
    load_bound_creation_snapshot,
    pack_paths,
    persist_creation_snapshot,
    validate_initial_selection_receipt,
)
from .rendering import (  # noqa: E402
    bounded_render_path,
    render_markdown,
    render_path,
    write_render,
)
from .replacement import (  # noqa: E402
    pack_planning_contract,
    replacement_plan_fingerprint,
    replacement_plan_snapshot_path,
    replacement_postcondition,
    validate_durable_creation_evidence,
    validate_replacement_receipt,
    validate_successor_creation_transition,
)
from .storage import (  # noqa: E402
    ContentAddressedWriteTransaction,
    _require_within,
    _without_volatile_pack_fields,
    bounded_workspace_file,
    bounded_workspace_path,
    canonical_pack_sha256,
    content_addressed_write_transaction,
    creation_receipt_dir,
    creation_snapshot_dir,
    guard_content_addressed_consumer,
    json_bytes,
    now_iso,
    pack_dir,
    pack_mutation_lock,
    pack_snapshot,
    parse_rfc3339,
    preserve_content_addressed_evidence,
    rel_path,
    resolve_pack_path,
    sha256_bytes,
    sha256_file,
    sha256_optional_file,
)
from .store import (  # noqa: E402
    LIVE_PACK_STATUSES,
    active_pack,
    active_pack_candidates,
    status_from_findings,
    task_pack_store_findings,
)
from .validation import publication_findings, validate_pack  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
