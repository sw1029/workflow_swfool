from __future__ import annotations

from typing import Any

from .canonical import object_sha256


def root_grant_request_binding_covers(
    grant: dict[str, Any], request: dict[str, Any]
) -> bool:
    """Return whether a plan-bound root grant covers this exact request.

    Schema-v3 grants are emitted only by the signed root-plan materializer and
    carry the compilation request digest from their exact per-grant projection.
    The canonical authority request includes ``cycle_id`` as a required field,
    so digest equality also proves the exact cycle binding without changing the
    historical schema-v2 grant contract.
    """

    if grant.get("schema_version") != 3:
        return True
    return grant.get("request_sha256") == object_sha256(request)
