"""Public facade for the read-only code-structure audit."""

from .code_structure.audit import audit
from .code_structure.cli import main
from .code_structure.contracts import (
    CLUSTER_KEYWORDS,
    CONVENTION_CONTRACT_KEYS,
    DEFAULT_THRESHOLDS,
    EXEMPT_NAMES,
    EXEMPT_PARTS,
    GLOBAL_REBINDING_PATTERNS,
    MECHANICAL_NAME_PATTERNS,
    SOURCE_SUFFIXES,
    convention_enforced,
    find_contract,
    list_contract_values,
    load_json,
    load_optional_contract,
    normalize_convention_contract,
    numeric_contract_value,
    reuse_root_modules,
)
from .code_structure.semantics import (
    directory_fan_out,
    duplicate_symbol_findings,
    semantic_findings,
)
from .code_structure.source import (
    analyze_file,
    clusters_for,
    collect_changed_files,
    git_files,
    global_rebinding_signals,
    import_reuse_counts,
    is_exempt,
    is_source,
    logical_line_count,
    mechanical_name_signals,
    python_imports,
    python_symbols,
    split_plan,
    suggested_root,
)

__all__ = [
    "CLUSTER_KEYWORDS",
    "CONVENTION_CONTRACT_KEYS",
    "DEFAULT_THRESHOLDS",
    "EXEMPT_NAMES",
    "EXEMPT_PARTS",
    "GLOBAL_REBINDING_PATTERNS",
    "MECHANICAL_NAME_PATTERNS",
    "SOURCE_SUFFIXES",
    "analyze_file",
    "audit",
    "clusters_for",
    "collect_changed_files",
    "convention_enforced",
    "directory_fan_out",
    "duplicate_symbol_findings",
    "find_contract",
    "git_files",
    "global_rebinding_signals",
    "import_reuse_counts",
    "is_exempt",
    "is_source",
    "list_contract_values",
    "load_json",
    "load_optional_contract",
    "logical_line_count",
    "main",
    "mechanical_name_signals",
    "normalize_convention_contract",
    "numeric_contract_value",
    "python_imports",
    "python_symbols",
    "reuse_root_modules",
    "semantic_findings",
    "split_plan",
    "suggested_root",
]


if __name__ == "__main__":
    raise SystemExit(main())
