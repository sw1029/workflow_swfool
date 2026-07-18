"""Stable facade for authority-settled legacy task-pack retirement."""

from __future__ import annotations

from .legacy_retirement_commands import (
    command_activate_legacy_retirement,
    command_retire_legacy,
)
from .legacy_retirement_projection import (
    active_retirement_for_pack,
    require_pack_not_retired,
    retirement_store_projection,
)
from .legacy_retirement_validation import (
    validate_activation_binding,
    validate_completion_binding,
)


__all__ = (
    "active_retirement_for_pack",
    "command_activate_legacy_retirement",
    "command_retire_legacy",
    "require_pack_not_retired",
    "retirement_store_projection",
    "validate_activation_binding",
    "validate_completion_binding",
)
