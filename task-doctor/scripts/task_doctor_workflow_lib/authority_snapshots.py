from __future__ import annotations

from pathlib import Path

from .common import read_json, require, workspace_file, workspace_regular_file


def verify_policy_snapshot(root: Path, binding: dict[str, str]) -> None:
    path = workspace_file(root, binding["ref"], binding["sha256"], "policy_snapshot")
    prefix = ".task/authorization/policy_snapshots/policy-" + binding["sha256"]
    require(binding["ref"].startswith(prefix) and path.name.startswith(
        f"policy-{binding['sha256']}"
    ), "invalid_authority_contract",
            "policy snapshot must use the authority owner's content-addressed path")
    metadata_path = workspace_regular_file(
        root, f"{binding['ref']}.json", "policy_snapshot_metadata"
    )
    metadata = read_json(metadata_path, "invalid_authority_contract")
    require(metadata.get("artifact_kind") == "policy_snapshot"
            and metadata.get("snapshot_ref") == binding["ref"]
            and metadata.get("snapshot_sha256") == binding["sha256"],
            "invalid_authority_contract", "policy snapshot metadata mismatch")
