# Completion Gate Matrix

## Gate Status Values

Use these values in validation reports:

- `passed`: evidence satisfies the gate.
- `partial`: evidence exists but has nonblocking gaps.
- `failed`: evidence shows a blocking defect.
- `missing`: required evidence was not produced.
- `blocked`: validation could not run because of an external blocker.
- `not_applicable`: gate is not relevant to this task.

## Progress Verdict Values

Report progress separately from validation status:

- `advanced`: the task moved a blocker, execution state, schema/contract state, issue state, or final-goal state forward with `terminal_outcome_changed=true` or strict observed `changed_vs_previous=true` plus `semantic_progress=true`.
- `safety_only`: validation passed, but the task only proved fail-closed/no-live behavior or added a defensive guard without reducing the active blocker.
- `no_progress`: the task did not produce meaningful new evidence or state movement.
- `regressed`: the task weakened, broke, or contradicted a required state.

Validation can be `complete` while progress is only `safety_only`; do not describe that as final-goal completion or issue closure unless the task explicitly defined that safety proof as the required state transition. `observed_producer_claim`, self-declared `produced_domain_delta`, fixture-only success, non-empty counts, blocker label movement, stale expectation anchors, parity-unverified comparison/adoption, majority-vote adoption without axis classification, failed gating adoption axes, resolution-downgraded surrogate evidence, divergent duplicate report keys, contradictory terminal classification, same-input mismatch, unresolved `diagnostics_unavailable`, unresolved instrumentation exercise, uncovered acceptance scenarios, acceptance inversion hidden by green tests, missing command argv provenance for comparison/baseline claims, repeated opaque blockers, stochastic exact-match/floor-edge infeasibility, live-run acceptance satisfied by derived/report evidence, non-disjoint independent verification, `pass_with_coupled_verifier`, guard-stacking hardening past cap, `candidate_degraded` without independently verified consumable axes, `producer_attested_fields`, or `attested_only_movement` cannot make progress `advanced` without adapter-recomputed truth, later non-coupled verifier evidence, disjoint verification inputs, fresh run evidence, rebaseline/contract repair/residual scope, `terminal_outcome_changed=true`, or strict observed changed-and-semantic output-delta evidence.

## Validation Profiles

Honor the `task.md` validation profile before requiring historical reruns:

- `current_only`: validate only the current task surface and its direct acceptance criteria.
- `affected_chain`: validate the current surface plus changed or newly dependent prerequisites named in the prerequisite manifest.
- `full_chain`: rerun the full prerequisite/history chain only for live dispatch, readiness promotion, shared validator/runtime changes, issue closure, or explicit user request.

If a task includes a prerequisite manifest with unchanged command, path, input, and check hashes, reuse prior passing evidence when the profile permits it. Missing, changed, or failed prerequisite evidence must be reported as `missing`, `partial`, or `failed` rather than silently reused.

## Required Gates

| Gate | Complete Requires | Partial When | Failed When |
| --- | --- | --- | --- |
| Task scope | All explicit `task.md` requirements and acceptance criteria are addressed. | Scope is mostly addressed but edge cases or minor requirements remain. | Core requested behavior is absent or contradicted. |
| Environment | Required runtime is identified and usable, or no runtime is needed. | Runtime likely exists but dependencies or activation are unverified. | Required runtime is unavailable and blocks validation. |
| Execution | Required commands/tests/scripts ran and passed with logs. | Some validation ran, but important commands were skipped or inconclusive. | Required execution fails or cannot start. |
| Repo audit | `$inspect-repo-with-agents` finds no blocking governance, regression, or generalization issue. | Audit was degraded or finds nonblocking risks. | Audit finds blocking defects, regressions, or severe overfitting. |
| Goal schema contract | Relevant schema/module/script contract changes satisfy `.agent_goal/goal_schema_contract.md`, and `.schema/` or `.contract/` evidence is current. | Goal schema-contract compliance is partly evidenced but has nonblocking missing fields, stale links, or unclear applicability. | Required schema-contract evidence is absent, stale, unsupported, or contradicts `.agent_goal/goal_schema_contract.md`. |
| External advice | Task-referenced `.agent_advice` was incorporated, rejected, deferred, or intentionally left active with rationale, and no advice was used as GT or authority. | Advice relevance is plausible but lifecycle links or rationale are incomplete. | Advice was ignored without rationale, applied despite higher-priority conflict, or treated as GT/authority. |
| Acceptance provenance | Measurable directive-derived work meets the original target, or an explicit descope decision preserves residual scope in an open follow-up. | The work is useful but original target achievement is incomplete, comparison evidence is degraded, or residual scope remains open. | `acceptance_diluted=true`, original target is unmet without descope, or a narrowed item has no residual follow-up. |
| Acceptance scenario | Every scenario-shaped criterion has at least one premise-satisfying fixture or live run, and the observed terminal state equals the expected state. | Scenario evidence is missing, incomplete, or needs validation-set planning. | A premise-satisfying input observes or asserts the opposite terminal state, or completion relies on tests that never satisfy the premise. |
| Acceptance envelope | Any adapter-supplied `acceptance_envelope_contract.envelope_floor` was satisfied by the selected or executed envelope, or the hook was absent/not comparable and the old acceptance basis remains. | The envelope comparison is present but degraded, indeterminate, or explicitly deferred with residual scope. | The selected or executed envelope is below the minimum needed for the target without explicit descope/residual scope or user escalation. |
| Acceptance verifier | Every required live verifier for a measurable target evaluated to `pass`, the verifier source was not modified in the same change set, or no target-to-verifier mapping was available and the old acceptance basis remains. | A required verifier is `not_evaluated`, `pass_with_coupled_verifier`, deferred, or incomplete but residual verifier work or explicit descope remains open. | The task consumes, applies, or completes a measurable target while its required verifier is `not_evaluated`, failed, or only passed through a same-changeset verifier-source modification. |
| Required gate hooks | Acceptance-referenced gates have their SKILL.md-required adapter hooks supplied and evaluated, or no measurable acceptance/caller contract requires the gate. | Hook supply is incomplete or deferred with residual hook work preserved. | The task consumes, applies, or completes a measurable target while an acceptance-required gate hook is absent, unloaded, fail-quiet, or `not_evaluated`. |
| Evidence provenance | High-water movement, measurable progress, and goal-productive support are backed by `independently_verified` evidence or a later independent recalculation. | Evidence exists but some moved fields are `producer_attested`; cap progress and preserve residual verification. | Completion, progress, high-water reset, or `goal_productive` relies on `producer_attested_fields` or `attested_only_movement` alone. |
| Verification source separation | `independently_verified_fields` have `verification_input_paths` disjoint from verified artifacts, or the adapter marks the affected axis `self_grounded=true`. | Source separation is missing/overlapping but affected fields are downgraded to attested and residual verification remains open. | Completion, progress, high-water reset, or `goal_productive` relies on independently verified fields whose inputs are missing, overlapping, or auto-downgraded. |
| Goal-axis completeness | Review-backed measurable goals have at least one adapter-owned observing axis when `goal_axis_map` is supplied, or axis mapping is not required/available and legacy review semantics apply. | Axis mapping is incomplete but adapter axis-supply work, residual scope, terminal blocker, or user escalation is preserved. | A qualitative review pass is consumed for a measurable goal whose mapped observing axis set is empty. |
| Count-key hygiene | Family novelty, stall reset, hypothesis exhaustion, and seals use generation-independent effective keys: adapter-collapsed root plus dominant parameter, or terminal-outcome family fallback. | Raw generation-dependent keys are present but preserved only as trace evidence and not used for close/progress claims. | A workflow claim treats task/advice/pack/cycle/run/date/hash/version key churn as a new family, stall reset, or seal escape. |
| Failure surface stage | Count/close keys include the adapter-collapsed root, dominant parameter, and observed `failure_surface_stage`; terminal classification agrees with the stage map. | Stage evidence is incomplete but no terminal/close/progress claim depends on it. | A task closes, counts, or seals a failure whose terminal classification contradicts the observed failure surface stage, or whose same-condition input set differs. |
| Instrumentation supply | Repeated `diagnostics_unavailable` was resolved by instrumentation supply or an explicit observability rationale proving success/failure is already measurable. | Diagnostics remain unavailable but the next residual task reserves instrumentation supply. | Progress advances or a family closes while `instrumentation_supply_required=true` remains unresolved. |
| Instrumentation exercise | Supplied instrumentation was exercised by a fresh run id after the supply item with non-empty scalar fields per `instrumentation_field_map`, or an explicit observability rationale proves the supplied fields are unnecessary. | Supply landed but exercise is reserved as the next residual item. | Dependent measurement, comparison, adoption, baseline, or close work advances while `instrumentation_exercise_required=true`, or existing artifact reinterpretation is counted as exercise. |
| Instrumentation first fire | A fresh run first emitted non-empty supplied instrumentation fields and the credit is assigned to one item only. | First-fire evidence exists but the consuming item or residual follow-up is unclear. | First-fire evidence is double-counted as goal progress, instrumentation-supply consumption, or multiple item consumption. |
| Acceptance encoding | Original measurable quantifiers and `evidence_kind` were preserved; `live_run` criteria are satisfied by a post-item run id. | Encoding is incomplete or live-run evidence is deferred with residual scope preserved. | Quantifiers were silently changed, or a `live_run` criterion is consumed through `derived_artifact`, `code_contract`, or `report_only` evidence without explicit descope/residual scope. |
| Verifier-surface hardening | Guard/verifier/report-only work over the same target is within cap or followed by fresh execution-output evidence. | Cap is reached but residual execution/descope/terminal/escalation work is preserved. | Another same-target guard, verifier, consistency check, or report is consumed as `goal_productive` after the cap with no fresh run id. |
| Run disposition | Unsafe output is `failed_closed`; quality-miss output is preserved as `candidate_degraded` without canonical promotion; successful output is `candidate_written`. | Disposition is present but independent verification for candidate axes is pending. | A `candidate_degraded` artifact replaces the canonical baseline or satisfies completion/progress without independent verification, or safety and quality failures are collapsed into one discard path. |
| Runtime config echo | Safe scalar runtime settings and `config_overrides` are used only for failure/root-cause routing. | Echo is missing or partial but not required for the completion claim. | A plausible `code_default` override blocker is ignored, or runtime echo is used as completion/progress proof. |
| Command provenance | Live execution evidence used for baseline, A/B, comparison, reproduction, or run-specific acceptance includes full body-free argv with argument names retained. | The run is useful for other scalar facts but lacks reproducible argv, so comparison/baseline claims remain open. | Completion, comparison, baseline, A/B, or reproduction relies on summarized, `...`, or missing argv evidence. |
| Blocker actionability | Gate/validator blockers used for routing or closure include violated relation, observed scalar values, expected relation, or minimum input delta. | A blocker is state-name-only but preserved as `blocker_opacity` and not used as resolved/actionable evidence. | Completion or routing claims the blocker is actionable/resolved while only an opaque reason code exists, especially after repeated same-gate opacity. |
| Stochastic feasibility | Exact-match or floor-edge contracts have no observed variance conflict, or were revised/descoped/escalated with residual scope. | Variance evidence exists and contract revision remains open. | Completion or retry claims depend on an exact equality or floor slack smaller than observed stochastic variance. |
| Expectation lineage | Output-derived scalar expectations are bound to a current non-superseded `expectation_anchor`, or were rebaselined against `designated_baseline`. | The expectation anchor is missing or stale, but residual rebaseline/descope/terminal/escalation work remains open. | Completion, live execution promotion, or progress depends on an `expectation_lineage_stale` scalar without rebaseline, explicit residual scope, terminal blocker, or user escalation. |
| Comparison parity | Comparison/adoption work has `parity_axes` and each required axis is controlled or measured; unknown axes are resolved before final adoption. | Parity axes are missing/unknown but the decision is explicitly provisional with residual axis-resolution scope. | Final adoption, baseline promotion, or comparison-winner claims proceed with `parity_unverified=true` or unknown required parity axes. |
| Adoption axis | Required output classes are represented as `gating` axes and all gating axes pass before adoption; tradable axes are compared only after gating passes. | Axis classification is incomplete or adoption remains `provisional_adoption` with residual work. | Majority-vote adoption consumes unclassified axes, a failed gating axis, or `measured_but_disqualified=true` candidate as accepted. |
| Resolution downgrade | Evidence resolution matches the original id/set/intersection/row contract, or the contract was explicitly revised with residual high-resolution scope. | A lower-resolution surrogate is preserved as provisional/warning evidence with resolution-restoration follow-up. | A high-resolution contract is completed from `resolution_downgrade=true` surrogate evidence without restoration, revision, or residual scope. |
| Report key integrity | Reports consumed for pass/close/adoption/baseline/comparison have no divergent duplicate terminal keys. | Duplicate terminal keys exist but values match and are recorded as schema debt. | `report_key_divergence=true`, or duplicate terminal keys inside one report have conflicting values and the report is still consumed. |
| Execution starvation | Recent no-run starvation informed derive ranking or execution was blocked by safety, authority, or terminal evidence. | Another no-run task completed but execution-producing residual work remains open. | A no-run guard/report/contract task is claimed `advanced` despite `execution_starvation=true` and no blocking safety/authority/terminal rationale. |
| Envelope thaw | Frozen-envelope-unreachable acceptance has a reserved `envelope_thaw_item`, thaw condition/schedule, explicit descope with residual scope, terminal blocker, or user escalation. | Thaw path exists but remains open as residual work. | Completion consumes unreachable frozen-envelope acceptance without thaw/residual/escalation. |
| Residual gap marginality | Residual measurable gaps are either met, explicitly descoped with residual scope, or repaired because adapter-owned marginal value, including value per cycle cost when available, outranks descope plus the next capability rung. | Residual gap comparison or cycle-cost evidence exists but is incomplete or deferred with residual scope preserved. | A below-threshold residual gap is repeatedly repaired or consumed as `goal_productive` without explicit descope, next-rung consideration, higher marginal-value evidence, or sufficient value per cycle cost. |
| Convention conformance | Changed code satisfies the repo-owned `code_convention_contract`, or the contract is absent and findings are recorded warn-only with any repeated gap preserved for derive. | Contract evidence is incomplete, missing, or deferred, but no contract-backed blocker is proven. | Unresolved contract-backed naming, reuse, placement, dependency-direction, duplicate-definition, global-rebinding, depth/fan-out, or forbidden-pattern violations contradict the task objective. |
| Structure effect | Behavior-preserving refactor/consolidation moved an adapter-supplied structure high-water target enough to satisfy the task objective, such as lower shard/coupling/duplicate/depth/fan-out burden, better reuse ratio, lower max LOC, or moved global invariants when `structure_high_water_key_scope=global_invariant`. | Refactor code and tests are useful but structure high-water movement is missing, weak, producer-local only, local-scope-only under a global-invariant key, or deferred. | The task claims structural reduction while target structure metrics are flat or worse, file-count growth/mechanical splitting/token avoidance is the only claimed progress, or global-invariant structure keys remain flat for a global structure objective. |
| Disposition task-kind | When anti-loop gates constrain `goal_productive` to `allowed_task_kinds`, the completed work's `selected_task_kind` is in that set. | The work is useful but outside the allowed kind set, with residual allowed correction preserved. | The task claims `goal_productive` using only the label while the actual task kind is outside the constrained allowed set. |
| Behavior-change live evidence | Runtime gate/router/validator/dispatch behavior-change fixes have fresh live before/after evidence, or the task explicitly did not require live behavior proof. | Live evidence is deferred with a recorded reason and follow-up. | A behavior-change fix is claimed complete from unit/static evidence alone while live result change is required. |
| Issue tracking | Linked implementation issues are either resolved by evidence, not applicable, or intentionally handed off to `$manage-implementation-issues` after validation. | Issue evidence exists but links, close evidence, or handoff state are incomplete. | An active issue proves the task objective is still blocked or contradicts the claimed completion. |
| OOM risk | `$inspect-oom-risk` passed or is not applicable. | Relevant OOM risk was not fully audited or has mitigated concerns. | Audit finds likely unbounded memory failure or unsafe resource behavior. |
| task_miss | No active linked miss is open, partial, or unverified. | Nonblocking misses remain and are recorded. | Severe active miss blocks the task objective. |
| Logs/index | `.agent_log` and `.task/index` link important evidence. | Some links are missing but evidence is recoverable. | Evidence is absent or cannot be traced. |
| ID consistency | `$manage-task-state-index` audit has no high-severity issues for the active workflow, or ID context is not applicable. | ID audit has low/medium issues or an ID insight agent was unavailable but deterministic evidence is recoverable. | Broken IDs, multiple active tasks, missing required task/run/audit/validation/miss links, or stale/deleted artifact ambiguity blocks completion evidence. |
| Progress | The task's declared progress target is met and progress verdict is `advanced`, or the target explicitly required only a safety proof. | Validation passed but progress is `safety_only` or the blocker movement is incomplete. | Progress is `no_progress` or `regressed`, or the evidence contradicts the declared progress target. |
| Producer progress truth-source | Producer self-report fields are stored only as `observed_producer_claim`, and authoritative progress comes from adapter recomputation, loopback/output-delta, or validation evidence. | A producer claim exists but the adapter/output-delta comparison is incomplete; preserve `split_brain_progress_claim` as a warning and cap progress conservatively. | Completion or progress relies on a producer label such as `goal_productive`, `advanced`, `effective_progress_kind`, or `produced_domain_delta` without authoritative recomputation. |

## Verdict Rules

Return `complete` only when every required gate is `passed` or `not_applicable` and the progress gate does not contradict the task's declared progress target.

Return `partial` when measurable acceptance was intentionally narrowed with residual scope, when behavior-change live evidence is explicitly deferred, when convention conformance is warn-only/incomplete, or when structural refactor evidence is useful but below the original target. These states may be valid progress, but they must not consume the original target.

Return `partial` when a measurable target's required verifier is `not_evaluated` and residual verifier work remains open. Return `failed` if the task claims the target consumed despite the required verifier being failed or not evaluated.

Return `partial` when a verifier pass is `pass_with_coupled_verifier` and residual non-coupled revalidation remains open. Return `failed` if the task consumes that coupled pass as complete, progress, or high-water movement without later non-coupled evidence or independent recalculation.

Return `partial` when claimed metric movement is producer-attested and independent recalculation remains open. Return `failed` if `attested_only_movement` or `producer_attested_fields` are used as the only basis for completion, `advanced`, high-water reset, or `goal_productive`.

Return `partial` when an independently verified field lacks disjoint verification inputs but is downgraded to attested with residual verification open. Return `failed` if non-disjoint or missing verification inputs still support completion, `advanced`, high-water reset, or `goal_productive`.

Return `partial` when a review-backed measurable target has `pass_with_unobserved_axes=true` and adapter axis-supply or residual scope remains open. Return `failed` if the task consumes that review pass as complete for the unobserved target.

Return `partial` when raw generation-dependent key evidence exists but the effective key preserves family continuity. Return `failed` if completion or next-task closure depends on counter reset or family novelty from generation-dependent key material.

Return `partial` when failure-surface stage or same-input evidence is incomplete and residual classification/input-contract repair remains open. Return `failed` if completion, closure, or family counting depends on a contradictory terminal classification or mismatched input set.

Return `partial` when repeated diagnostics remain unavailable and instrumentation supply is the next open residual. Return `failed` if progress advances or the family closes while `instrumentation_supply_required=true` remains unresolved.

Return `partial` when instrumentation supply landed but fresh exercise remains the next open residual. Return `failed` if dependent measurement/adoption work advances while `instrumentation_exercise_required=true` remains unresolved.

Return `partial` when scenario-shaped acceptance lacks premise-satisfying evidence. Return `failed` if the task claims the scenario met while tests or outputs assert the opposite state for a premise-satisfying input.

Return `partial` when full argv is missing for a run needed only as future reproduction evidence. Return `failed` if completion or comparison depends on a summarized or omitted argv command.

Return `partial` when blocker actionability fields are missing but the blocker is only warning evidence. Return `failed` if the task claims an opaque blocker was resolved or actionable without relation/observed/expected/minimum-delta fields.

Return `partial` when stochastic variance evidence requires contract revision. Return `failed` if completion or retry ignores `predetermined_unreachable` or `floor_edge_envelope`.

Return `partial` when first-fire instrumentation credit exists but residual exercise/consumption is still open. Return `failed` if the same first-fire run is double-counted.

Return `partial` when an output-derived expectation is missing an anchor or needs rebaseline. Return `failed` if a stale anchored expectation is consumed for completion, live execution promotion, or progress without rebaseline, explicit residual scope, terminal blocker, or user escalation.

Return `partial` when parity axes are incomplete and the adoption/comparison decision is explicitly provisional. Return `failed` if final adoption, baseline promotion, or comparison-winner claims consume `parity_unverified` evidence.

Return `partial` when adoption-axis classification is incomplete but residual classification work remains open. Return `failed` if majority vote consumes a candidate with unclassified axes, a failed gating axis, or `measured_but_disqualified=true`.

Return `partial` when evidence resolution was downgraded and high-resolution restoration or contract revision remains open. Return `failed` if the task completes the original high-resolution contract from surrogate evidence alone.

Return `failed` when `report_key_divergence=true` affects any report consumed by the task's pass, close, adoption, baseline, comparison, or high-water claim. Matching duplicate keys may be `partial` or warn-only schema debt.

Return `partial` when live-run acceptance evidence is deferred with residual scope. Return `failed` if a live-run criterion is consumed by derived artifacts, code contracts, or reports without explicit descope and residual tracking.

Return `partial` when guard-stacking cap is reached and execution/descope/terminal work remains open. Return `failed` if another same-target guard/verifier/report task is consumed as goal-productive after the cap.

Return `partial` when `candidate_degraded` evidence is preserved but independent verification remains open. Return `failed` if the degraded candidate is promoted as canonical success without independent verification.

Return `partial` when frozen-envelope thaw work is reserved but not complete. Return `failed` if unreachable acceptance under a frozen envelope is consumed without `envelope_thaw_item`, residual descope, terminal blocker, or user escalation.

Return `partial` when residual-gap value-per-cycle-cost evidence is incomplete but residual scope remains open. Return `failed` if below-policy value per cycle cost is ignored to consume another same-gap repair as complete or goal-productive.

Return `failed` when any gate has a blocking `failed` status for the active task objective.

Return `partial` for every other state, including degraded audits, missing noncritical evidence, unresolved nonblocking task_miss, or skipped OOM/env checks that are relevant but not fatal.

When in doubt between `complete` and `partial`, choose `partial` and record the missing evidence.

If validation is complete but progress is `safety_only`, report the cycle as technically validated but not final-goal-progress unless the task itself was intentionally a safety gate. If progress is `no_progress` or `regressed`, do not return final completion even when commands passed.
