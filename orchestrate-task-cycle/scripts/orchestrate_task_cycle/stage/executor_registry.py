"""Closed executor and routing registry for every compiled stage target."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType

from ..result_contract.configuration import (
    AGENT_ROUTING_TARGETS,
    MODEL_EFFORT_POLICY,
    TARGETS,
)
from .v2_specs import (
    DETERMINISTIC_TARGETS,
    HYBRID_TARGETS,
    dependency_selectors,
)


@dataclass(frozen=True, slots=True)
class ExecutorSpec:
    target: str
    executor_kind: str
    command_id: str
    owner_id: str
    routing_policy_id: str | None
    allowed_routing_profiles: tuple[str, ...]
    input_selector_id: str
    output_adapter_id: str
    semantic_schema_id: str | None
    side_effect_class: str

    @property
    def routing_required(self) -> bool:
        return self.routing_policy_id is not None

    def projection(self) -> dict[str, object]:
        projected = asdict(self)
        projected["allowed_routing_profiles"] = list(
            self.allowed_routing_profiles
        )
        return {**projected, "routing_required": self.routing_required}


@dataclass(frozen=True, slots=True)
class OwnerEffectPolicy:
    """Continuation effect and recovery contract for one owner target."""

    side_effect_class: str
    action_effect_classes: tuple[str, ...]
    recovery_strategy: str


def _local(
    side_effect_class: str = "workspace_metadata_write",
) -> OwnerEffectPolicy:
    return OwnerEffectPolicy(
        side_effect_class,
        ("local_reversible",),
        "uncertain",
    )


def _git(*, verified_closeout: bool = False) -> OwnerEffectPolicy:
    return OwnerEffectPolicy(
        "git_mutation",
        ("local_commit",),
        (
            "verify_closeout_anchor"
            if verified_closeout
            else "uncertain"
        ),
    )


OWNER_EFFECT_MATRIX = MappingProxyType(
    {
        "authority": _local(),
        "acceptance": _local(),
        "validation_scope_plan": _local(),
        "validation_set_plan": _local(),
        "governance": _local("workspace_mutation"),
        "run": OwnerEffectPolicy(
            "external_or_long_running_effect",
            ("unknown", "local_long_run"),
            "uncertain",
        ),
        "validation_set_build": _local("workspace_mutation"),
        "visible_increment": _local(),
        "validation_scope_finalize": _local(),
        "index_pre_validate": _local(),
        "issue": _local(),
        "schema_pre_derive": _local(),
        "schema_post_derive": _local(),
        "index": _local(),
        "commit": _git(),
        "closeout_commit": _git(verified_closeout=True),
        "qualitative_review": OwnerEffectPolicy(
            "observe_only",
            ("observe_only",),
            "safe_reissue",
        ),
        "loopback_audit": _local(),
        "derive": _local(),
        "validate": _local(),
    }
)


_COMMAND_IDS = {
    "repo_skill_adapter_scan": "repo_skill_adapter.scan.v2",
    "repo_skill_adapter_validate": "repo_skill_adapter.validate.v2",
    "code_structure_audit": "code_structure.audit.v2",
    "repo_skill_gap_analysis": "repo_skill_gap.render.v1",
    "cycle_efficiency_profile": "cycle_efficiency.analyze.v1",
    "dashboard": "cycle_dashboard.render.v1",
    "report": "cycle_report.assemble.v1",
    "authority": "manage_agent_authority.owner.v2",
    "acceptance": "normalize_acceptance.owner.v2",
    "validation_scope_plan": "validation_scope.plan.owner.v1",
    "validation_set_plan": "validation_set.plan.owner.v1",
    "governance": "task_governance.owner.v1",
    "run": "task_run.owner.v1",
    "validation_set_build": "validation_set.build.owner.v1",
    "visible_increment": "visible_increment.owner.v1",
    "validation_scope_finalize": "validation_scope.finalize.owner.v1",
    "index_pre_validate": "task_index.prevalidate.owner.v3",
    "issue": "implementation_issue.owner.v1",
    "schema_pre_derive": "schema.prederive.owner.v1",
    "schema_post_derive": "schema.postderive.owner.v1",
    "index": "task_index.owner.v2",
    "commit": "repo_commit.owner.v1",
    "closeout_commit": "repo_commit.closeout.owner.v1",
    "qualitative_review": "qualitative_review.hybrid.v1",
    "loopback_audit": "loopback_audit.hybrid.v1",
    "derive": "improvement_task.derive.hybrid.v1",
    "validate": "task_completion.validate.hybrid.v1",
}

_OWNERS = {
    "authority": "manage-agent-authority",
    "acceptance": "normalize-acceptance-and-demo",
    "validation_scope_plan": "plan-validation-scope",
    "validation_scope_finalize": "plan-validation-scope",
    "validation_set_plan": "build-validation-set-with-agents",
    "validation_set_build": "build-validation-set-with-agents",
    "governance": "task-md-agent-governance",
    "run": "run-task-code-and-log",
    "visible_increment": "record-visible-increment",
    "issue": "manage-implementation-issues",
    "index_pre_validate": "manage-task-state-index",
    "index": "manage-task-state-index",
    "schema_pre_derive": "manage-schema-contracts",
    "schema_post_derive": "manage-schema-contracts",
    "commit": "repo-change-commit",
    "closeout_commit": "repo-change-commit",
    "qualitative_review": "review-cycle-output-quality",
    "loopback_audit": "audit-cycle-loopback",
    "derive": "derive-improvement-task",
    "validate": "validate-task-completion",
}

_DETERMINISTIC_SIDE_EFFECTS = MappingProxyType(
    {
        "repo_skill_adapter_scan": "observe_only",
        "repo_skill_adapter_validate": "observe_only",
        "code_structure_audit": "observe_only",
        "repo_skill_gap_analysis": "observe_only",
        "cycle_efficiency_profile": "observe_only",
        "dashboard": "workspace_projection_write",
        "report": "workspace_projection_write",
    }
)


# Exact selectors which an already-executed, contract-valid owner result may
# move between preparation and publication. Every unlisted selector remains a
# precondition and must still equal the preparation-bound fingerprint. Empty
# rows are deliberate for content-addressed producer writes which do not alter
# selected repository state.
_POST_EFFECT_SELECTORS = {
    "authority": (),
    "acceptance": (),
    "validation_scope_plan": (),
    "validation_set_plan": (),
    "governance": ("task", "git_worktree"),
    "run": ("git_worktree", "session"),
    "validation_set_build": ("validation",),
    "visible_increment": ("git_worktree",),
    "validation_scope_finalize": (),
    "index_pre_validate": (),
    "issue": ("issue",),
    "schema_pre_derive": ("schema",),
    "schema_post_derive": ("schema",),
    "index": ("task_state", "selection"),
    "commit": ("git_head", "git_worktree"),
    "dashboard": (),
    "report": (),
    "closeout_commit": ("git_head", "git_worktree"),
    "loopback_audit": (),
    "derive": (),
    "validate": (),
}


def allowed_post_effect_selectors(target: str) -> tuple[str, ...]:
    if target not in EXECUTOR_REGISTRY:
        raise ValueError(f"unregistered stage executor: {target}")
    return _POST_EFFECT_SELECTORS.get(target, ())


def _kind(target: str) -> str:
    if target in DETERMINISTIC_TARGETS:
        return "deterministic"
    if target in HYBRID_TARGETS:
        return "hybrid"
    return "owner"


def _spec(target: str) -> ExecutorSpec:
    kind = _kind(target)
    routed = target in AGENT_ROUTING_TARGETS
    side_effect = (
        _DETERMINISTIC_SIDE_EFFECTS[target]
        if kind == "deterministic"
        else OWNER_EFFECT_MATRIX[target].side_effect_class
    )
    return ExecutorSpec(
        target=target,
        executor_kind=kind,
        command_id=_COMMAND_IDS[target],
        owner_id=_OWNERS.get(target, "orchestrate-task-cycle"),
        routing_policy_id=(
            str(MODEL_EFFORT_POLICY["policy_id"]) if routed else None
        ),
        allowed_routing_profiles=(
            tuple(
                str(item)
                for item in MODEL_EFFORT_POLICY["target_profiles"][target]
            )
            if routed
            else ()
        ),
        input_selector_id=f"stage-context-{target}-v1",
        output_adapter_id=(
            f"native-{target}-v1"
            if kind == "deterministic"
            else "stage-hybrid-result-v1"
            if kind == "hybrid"
            else "stage-owner-result-v1"
        ),
        semantic_schema_id=(f"stage-semantic-{target}-v1" if kind == "hybrid" else None),
        side_effect_class=side_effect,
    )


EXECUTOR_REGISTRY = {target: _spec(target) for target in TARGETS}

if set(EXECUTOR_REGISTRY) != set(TARGETS):
    raise RuntimeError("executor registry must cover every result target")
if {name for name, spec in EXECUTOR_REGISTRY.items() if spec.executor_kind == "deterministic"} != set(DETERMINISTIC_TARGETS):
    raise RuntimeError("executor registry deterministic target set is incomplete")
if {name for name, spec in EXECUTOR_REGISTRY.items() if spec.executor_kind == "hybrid"} != set(HYBRID_TARGETS):
    raise RuntimeError("executor registry hybrid target set is incomplete")
if {name for name, spec in EXECUTOR_REGISTRY.items() if spec.routing_required} != set(AGENT_ROUTING_TARGETS):
    raise RuntimeError("executor registry routing target set is incomplete")
if any(
    spec.routing_required != bool(spec.allowed_routing_profiles)
    for spec in EXECUTOR_REGISTRY.values()
):
    raise RuntimeError("executor registry routing policy/profile binding is incomplete")
if any(
    spec.executor_kind == "deterministic"
    and (spec.routing_policy_id is not None or spec.allowed_routing_profiles)
    for spec in EXECUTOR_REGISTRY.values()
):
    raise RuntimeError("deterministic executors must not declare model routing")
if any(not spec.command_id or not spec.output_adapter_id for spec in EXECUTOR_REGISTRY.values()):
    raise RuntimeError("executor registry contains an unbound executor")
if set(OWNER_EFFECT_MATRIX) != set(TARGETS) - set(DETERMINISTIC_TARGETS):
    raise RuntimeError("owner effect matrix must cover every owner and hybrid target")
if set(_DETERMINISTIC_SIDE_EFFECTS) != set(DETERMINISTIC_TARGETS):
    raise RuntimeError("deterministic side-effect matrix is incomplete")
_EFFECTFUL_TARGETS = {
    target
    for target, spec in EXECUTOR_REGISTRY.items()
    if spec.side_effect_class != "observe_only"
}
if set(_POST_EFFECT_SELECTORS) != _EFFECTFUL_TARGETS:
    raise RuntimeError("side-effecting executors require an explicit post-effect boundary")
if any(
    not set(selectors) <= set(dependency_selectors(target))
    for target, selectors in _POST_EFFECT_SELECTORS.items()
):
    raise RuntimeError("post-effect selectors must be target precondition selectors")


def executor_spec(target: str) -> ExecutorSpec:
    try:
        return EXECUTOR_REGISTRY[target]
    except KeyError as exc:
        raise ValueError(f"unregistered stage executor: {target}") from exc


def continuation_effect_class(
    target: str,
    *,
    executor_kind: str,
    side_effect_class: str,
    local_long_run_authorized: bool = False,
) -> str:
    """Resolve an owner action effect only from the closed target policy."""

    registered = EXECUTOR_REGISTRY.get(target)
    policy = OWNER_EFFECT_MATRIX.get(target)
    if (
        registered is None
        or policy is None
        or registered.executor_kind not in {"owner", "hybrid"}
        or executor_kind != registered.executor_kind
        or side_effect_class != policy.side_effect_class
    ):
        return "unknown"
    if target == "run" and local_long_run_authorized:
        return "local_long_run"
    return policy.action_effect_classes[0]


def owner_recovery_strategy(target: str, effect_class: str) -> str:
    """Return a safe recovery strategy, defaulting to typed uncertainty."""

    policy = OWNER_EFFECT_MATRIX.get(target)
    if policy is None or effect_class not in policy.action_effect_classes:
        return "uncertain"
    return policy.recovery_strategy


__all__ = [
    "EXECUTOR_REGISTRY",
    "ExecutorSpec",
    "OWNER_EFFECT_MATRIX",
    "OwnerEffectPolicy",
    "allowed_post_effect_selectors",
    "continuation_effect_class",
    "executor_spec",
    "owner_recovery_strategy",
]
