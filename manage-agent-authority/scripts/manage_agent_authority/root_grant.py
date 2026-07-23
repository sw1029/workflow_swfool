"""Public plan-bound root-grant API with compatibility aliases."""

from .root_decision_seed import (
    compile_root_decision_seed,
    load_root_decision_seed,
)
from .root_authorization_evidence import (
    load_root_authorization_evidence,
    publish_root_authorization_evidence,
)
from .root_grant_materialization import (
    materialize_exact_echo_root_grant,
    materialize_plan_bound_root_grant,
    validate_root_approval_decision,
)
from .root_grant_plan import (
    ROOT_PLAN_ROOT,
    load_root_approval_plan,
    prepare_root_approval_plan,
)


__all__ = (
    "ROOT_PLAN_ROOT",
    "compile_root_decision_seed",
    "load_root_approval_plan",
    "load_root_authorization_evidence",
    "load_root_decision_seed",
    "materialize_exact_echo_root_grant",
    "materialize_plan_bound_root_grant",
    "prepare_root_approval_plan",
    "publish_root_authorization_evidence",
    "validate_root_approval_decision",
)
