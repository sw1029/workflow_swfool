from __future__ import annotations

import argparse
import json

from .policy import load_json_arg
from .routing import select_route


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select a governed configured model/effort tier for an orchestrated agent role."
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--request", help="JSON object, JSON file, or '-' for stdin.")
    parser.add_argument(
        "--model-bindings", help="Optional model-ref binding JSON object or file."
    )
    args = parser.parse_args(argv)
    try:
        request = load_json_arg(args.request)
        if args.model_bindings:
            request["model_bindings"] = load_json_arg(args.model_bindings)
        result = select_route(args.profile, request)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2
            )
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["routing_violations"] else 0
