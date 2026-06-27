# Agent Perspectives For OOM Audits

Use these only when the user explicitly authorizes agent-based, delegated, parallel, or multi-agent inspection.

## Count Heuristics

- **3 agents**: data/loading, runtime/concurrency, safeguards/tests.
- **4 agents**: data/loading, model/accelerator, runtime/concurrency/lifecycle, config/CI/operability.
- **5 agents**: add language/framework-specific deep dive or service/API path.
- **6 agents**: only when the repo has clearly independent layers such as frontend, backend, data pipeline, ML training/serving, infrastructure, and CI.

## Perspective Pool

- **Data volume and file formats**: read-all APIs, dataframe/arrow/spark usage, projections, streaming, compression, archive/image expansion.
- **Model and accelerator memory**: model sizes, dtype/quantization, batch/context/token defaults, device placement, per-worker replication, serving limits.
- **Concurrency and lifecycle**: queues, pools, async gather, retries, worker counts, cache lifetime, retained outputs, cleanup.
- **Runtime and service paths**: API endpoints, CLI defaults, scheduled jobs, request limits, pagination, backpressure, cgroup/container awareness.
- **Build/test/CI**: parallelism, heap flags, build contexts, test fixtures, generated artifacts, memory-heavy integration tests.
- **Observability and safeguards**: documented limits, dry-run/sample modes, memory metrics, OOM log handling, regression tests, runbooks.
- **Limit-placement audit**: prove whether caps, filters, and samples apply before or after read-all conversion, executor submission, model prompt construction, or result aggregation.

## Subagent Prompt Template

```text
You are one of [N] agents inspecting the repository at [repo path].

User task:
Audit this repository for possible out-of-memory risks and return evidence-backed findings.

Your assigned OOM perspective:
[perspective]

Focus paths or components:
[paths/components]

Exclude:
Generated/vendor directories, binary artifacts, large datasets, model weights, archives, and full log scans unless specifically relevant by metadata or targeted snippets.

Do not edit files. Do not spawn other agents. Do not run heavy workloads.

Inspect with `rg`, file metadata, and targeted reads. Report:
1. Findings with severity, confidence, memory domain, and file/line references.
2. The allocation/retention mechanism and scaling input.
3. Existing bounds, whether they apply before allocation, and missing safeguards.
4. Commands/evidence used.
5. Areas not inspected.

Keep the response concise and actionable.
```
