from __future__ import annotations

from ..runtime_dependencies import (
    Path,
    adapter_file_sha256,
    domain_adapter_candidate_paths,
    load_artifact_selection,
    load_changed_files,
    load_domain_adapter,
    registered_adapter_from_scan,
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
    explicit_adapter = getattr(args, "domain_adapter", None)
    scan_handoff = registered_adapter_from_scan(
        root,
        getattr(args, "adapter_scan_json", None),
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    selected_adapter = explicit_adapter
    if not selected_adapter and scan_handoff.get("status") == "ready":
        selected_adapter = scan_handoff.get("implementation_path")
    adapter_candidates = domain_adapter_candidate_paths(root, selected_adapter)
    adapter_registered = bool(
        adapter_candidates or scan_handoff.get("adapter_registered") is True
    )
    adapter_expected_path = (
        adapter_candidates[0].expanduser().resolve().as_posix()
        if adapter_candidates
        else scan_handoff.get("implementation_path")
    )
    domain_adapter = None
    domain_adapter_path = None
    domain_adapter_error = scan_handoff.get("error")
    if selected_adapter:
        domain_adapter, domain_adapter_path, load_error = load_domain_adapter(
            root, selected_adapter
        )
        domain_adapter_error = load_error or domain_adapter_error
    adapter_revision_sha256 = scan_handoff.get("adapter_revision_sha256")
    if not adapter_revision_sha256 and domain_adapter_path:
        adapter_revision_sha256 = adapter_file_sha256(Path(domain_adapter_path))
    frame.update({
        "adapter_expected_path": adapter_expected_path,
        "adapter_registered": adapter_registered,
        "adapter_revision_sha256": adapter_revision_sha256,
        "adapter_scan_handoff": scan_handoff,
        "changed_files": changed_files,
        "decision_artifact_ref": decision_artifact_ref,
        "domain_adapter": domain_adapter,
        "domain_adapter_error": domain_adapter_error,
        "domain_adapter_path": domain_adapter_path,
        "paths": paths,
    })
