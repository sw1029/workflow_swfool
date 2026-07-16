"""Compatibility surface for independently reconstructed migration evidence.

The implementation is split by evidence responsibility; this module intentionally
keeps the established private import surface used by verifier fixtures.
"""

from .correction_evidence import (
    _anchor_event,
    _bind_quarantine_corrections,
    _correction_identity,
    _make_corrections,
    _manifest,
    _validate_quarantine_bindings,
)
from .mapping_evidence import (
    _classify_prefix,
    _infer_event,
    _mapping_entry,
    _normalize_legacy,
    _preserve_legacy_token,
    _strict_reader_reason,
    _token,
    _validate_mapping,
)
from .projection_evidence import _current_projection, _render_markdown

__all__ = [
    "_anchor_event",
    "_bind_quarantine_corrections",
    "_classify_prefix",
    "_correction_identity",
    "_current_projection",
    "_infer_event",
    "_make_corrections",
    "_manifest",
    "_mapping_entry",
    "_normalize_legacy",
    "_preserve_legacy_token",
    "_render_markdown",
    "_strict_reader_reason",
    "_token",
    "_validate_mapping",
    "_validate_quarantine_bindings",
]
