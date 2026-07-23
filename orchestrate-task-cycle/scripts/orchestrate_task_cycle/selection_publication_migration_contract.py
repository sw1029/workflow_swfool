"""Hard resource limits for one explicit selection-history migration."""

from __future__ import annotations

from dataclasses import dataclass
import stat
from pathlib import Path


MAX_MIGRATION_TRANSACTIONS = 4096
MAX_MIGRATION_ENTRIES = 16_384
MAX_MIGRATION_FILE_BYTES = 32 * 1024 * 1024
MAX_MIGRATION_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MIGRATION_JOURNAL_BYTES = 8 * 1024 * 1024


@dataclass
class MigrationBudget:
    entries: int = 0
    bytes_read: int = 0

    def consume_stat(self, observed: object, label: str) -> None:
        self.entries += 1
        if self.entries > MAX_MIGRATION_ENTRIES:
            raise ValueError(
                "selection-publication migration exceeds entry-count bound"
            )
        mode = getattr(observed, "st_mode")
        if stat.S_ISLNK(mode):
            raise ValueError(f"{label} cannot be a symlink")
        if stat.S_ISREG(mode):
            size = int(getattr(observed, "st_size"))
            if size > MAX_MIGRATION_FILE_BYTES:
                raise ValueError(f"{label} exceeds migration file-size bound")
            self.bytes_read += size
            if self.bytes_read > MAX_MIGRATION_TOTAL_BYTES:
                raise ValueError(
                    "selection-publication migration exceeds total-byte bound"
                )

    def consume_path(self, path: Path, label: str) -> None:
        try:
            observed = path.lstat()
        except OSError as exc:
            raise ValueError(f"{label} is unavailable during migration") from exc
        self.consume_stat(observed, label)


__all__ = (
    "MAX_MIGRATION_ENTRIES",
    "MAX_MIGRATION_FILE_BYTES",
    "MAX_MIGRATION_JOURNAL_BYTES",
    "MAX_MIGRATION_TOTAL_BYTES",
    "MAX_MIGRATION_TRANSACTIONS",
    "MigrationBudget",
)
