from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import discover_contract
from .provider import normalize_provider_result, run_provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a repository output-delta contract through its provider hook."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--contract")
    parser.add_argument("--artifact-paths-json")
    parser.add_argument("--artifact-path", action="append", default=[])
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    contract_path, contract, reason = discover_contract(root, args.contract)
    if contract_path is None or contract is None:
        result = normalize_provider_result(
            root,
            contract_path,
            contract,
            None,
            reason or "not_applicable_no_contract",
            reason,
        )
    else:
        result = run_provider(
            root, contract_path, contract, args.artifact_paths_json, args.artifact_path
        )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return (
        0
        if result["output_delta_status"]
        in {"complete", "not_applicable_no_contract", "not_applicable_no_provider"}
        else 2
    )
