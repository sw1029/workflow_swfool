"""Public selection-publication GC API.

The implementation is partitioned by ownership boundary: bounded scanning and
planning, no-follow storage, archive handling, authority validation, and the two
effect directions.
"""

from .selection_publication_gc_apply import apply_gc
from .selection_publication_gc_archive import archive_bytes, archive_payloads
from .selection_publication_gc_authority import (
    expected_subject,
    validate_effect_authority,
)
from .selection_publication_gc_contract import (
    archive_path,
    plan_path,
    receipt_path,
    restore_receipt_path,
)
from .selection_publication_gc_restore import restore_gc
from .selection_publication_gc_scan import load_plan, plan_gc


_archive_bytes = archive_bytes
_archive_path = archive_path
_archive_payloads = archive_payloads
_expected_subject = expected_subject
_load_plan = load_plan
_plan_path = plan_path
_receipt_path = receipt_path
_restore_receipt_path = restore_receipt_path
_validate_effect_authority = validate_effect_authority


__all__ = ("apply_gc", "plan_gc", "restore_gc")
