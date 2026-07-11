#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from anti_loop_provider import api as _api  # noqa: E402


_DOMAIN_ADAPTER_MODULE: Any | None = None


def _sync_runtime_to_api() -> None:
    _api.set_runtime_caches(
        {
            "_DOMAIN_ADAPTER_MODULE": globals().get("_DOMAIN_ADAPTER_MODULE"),
        }
    )


def _sync_runtime_from_api() -> None:
    caches = _api.get_runtime_caches()
    globals()["_DOMAIN_ADAPTER_MODULE"] = caches.get("_DOMAIN_ADAPTER_MODULE")


def evaluate(args: Any) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    _sync_runtime_to_api()
    result = _api.evaluate(args)
    _sync_runtime_from_api()
    return result


def main(argv: list[str] | None = None) -> int:
    _sync_runtime_to_api()
    result = _api.main(argv)
    _sync_runtime_from_api()
    return result


for _name in _api.__all__:
    if _name in {"evaluate", "main"}:
        continue
    globals()[_name] = getattr(_api, _name)


__all__ = sorted(
    {
        "evaluate",
        "main",
        "_DOMAIN_ADAPTER_MODULE",
        *[name for name in _api.__all__ if name not in {"evaluate", "main"}],
    }
)


if __name__ == "__main__":
    raise SystemExit(main())
