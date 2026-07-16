from __future__ import annotations

from ..runtime_dependencies import (
    domain_adapter_candidate_paths,
    load_artifact_selection,
    load_changed_files,
    load_domain_adapter,
)

from ..evaluation_frame import _EvaluationFrame


def _prepare_artifact_state(frame: _EvaluationFrame) -> None:
    (
        args, root,
    ) = frame.require(
        'args', 'root',
    )
    paths, decision_artifact_ref = load_artifact_selection(
        root,
        args.artifact_paths_json,
        args.artifact_path,
        artifact_ref_json=getattr(args, "artifact_ref_json", None),
        artifact_family=args.artifact_family,
    )
    changed_files = load_changed_files(
        root,
        getattr(args, "changed_files_json", None),
        getattr(args, "changed_file", []) or [],
    )
    adapter_candidates = domain_adapter_candidate_paths(root, getattr(args, "domain_adapter", None))
    adapter_registered = bool(adapter_candidates)
    adapter_expected_path = adapter_candidates[0].expanduser().resolve().as_posix() if adapter_candidates else None
    domain_adapter, domain_adapter_path, domain_adapter_error = load_domain_adapter(root, getattr(args, "domain_adapter", None))
    frame.update({
        "adapter_expected_path": adapter_expected_path,
        "adapter_registered": adapter_registered,
        "changed_files": changed_files,
        "decision_artifact_ref": decision_artifact_ref,
        "domain_adapter": domain_adapter,
        "domain_adapter_error": domain_adapter_error,
        "domain_adapter_path": domain_adapter_path,
        "paths": paths,
    })
