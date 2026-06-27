---
name: inspect-oom-risk
description: "Audit a working repository for out-of-memory risk surfaces using at least `reasoning_effort: high` for code/resource analysis agents and `reasoning_effort: xhigh` for important work review, then return prioritized evidence-backed findings. Use when the user asks to inspect, review, audit, or diagnose OOM, memory blowups, RAM/VRAM/GPU failures, container limits, large data loading, batch/concurrency risks, model serving memory, build/test pressure, caches, leaks, or unbounded accumulation."
---

# Inspect OOM Risk

## Overview

Use this skill to inspect any repository for likely OOM failure paths. Prefer static evidence first: code paths, configs, manifests, data/model size hints, logs, and tests. Do not run expensive workloads or load large artifacts unless the user explicitly asks for dynamic profiling.

Report concrete risks, not vague memory advice. Each finding should name the allocation mechanism, scaling input, likely memory domain, evidence, and mitigation direction.

When task-state artifacts exist, use `$manage-task-state-index` as a nonblocking traceability add-on. Lack of ID context must not prevent a normal OOM audit.

## Agent Routing Policy

- Treat OOM code/resource analysis as high-reasoning work. Use `reasoning_effort: high` as the minimum for delegated OOM inspection agents whenever tooling exposes it.
- Treat OOM review as important work review with `reasoning_effort: xhigh` when it supports completion validation, post-implementation governance, model/data pipeline safety, production/runtime reliability, high-severity memory findings, or irreversible task/issue/miss cleanup decisions.
- Keep ID-only traceability agents routed through `$manage-task-state-index` with fixed `reasoning_effort: medium`.
- If tooling cannot enforce the requested effort, include the requirement in the prompt and report the limitation.

## Workflow

1. Map the repository quickly.
   - Run `pwd`, `git status --short` when available, and `rg --files`.
   - Identify languages, entry points, manifests, CI/build config, runtime config, data/model directories, generated/vendor directories, and tests.
   - Inventory large files and scale hints before judging severity: file sizes, row counts, model names/sizes, documented corpus sizes, request concurrency, and container memory limits.
   - Do not read large binaries, model weights, databases, parquet/zst/faiss files, logs, or archives in full. Inspect names, sizes, schemas, metadata, and targeted snippets instead.
   - If `.task/`, `.agent_log/`, or `task.md` exists, run `$manage-task-state-index` `scan` and `audit` to identify active task, audit, run, validation, and miss IDs relevant to OOM evidence.

2. Choose inspection mode.
   - Use local inspection by default.
   - If the user explicitly requests agent-based, delegated, parallel, or multi-agent inspection, use 3-6 read-only explorer agents with distinct OOM perspectives. Load [agent-perspectives.md](references/agent-perspectives.md) for role selection and prompts.
   - Spawn OOM code/resource analysis agents with minimum `reasoning_effort: high`; use `reasoning_effort: xhigh` for important work review.
   - If ID context exists and the workflow authorizes agents, optionally spawn one additional read-only ID consistency agent. It is separate from OOM agents and must only inspect task-state IDs, links, lifecycle status, and whether OOM audit evidence is traceable.
   - Continue useful local work while agents inspect non-overlapping areas.

3. Search for OOM risk signals.
   - Load [risk-catalog.md](references/risk-catalog.md) when selecting search patterns or classifying findings.
   - Start with targeted `rg` searches for read-all APIs, batch/concurrency knobs, model/GPU settings, caches, accumulators, queue sizes, worker counts, joins, `collect()` calls, and memory-limit config.
   - Inspect only the surrounding code needed to confirm flow, defaults, input bounds, and lifecycle.

4. Trace memory growth.
   - For each candidate, identify the memory domain: CPU heap/RSS, GPU/VRAM, shared memory, container/cgroup, browser heap, build tool heap, database temp memory, or disk-backed mmap/page cache.
   - Identify the scaling variable: input file size, row count, document count, token/context length, model size, batch size, worker count, result count, graph size, image dimensions, request concurrency, or retry buffering.
   - Check whether limits exist: pagination, streaming, chunking, backpressure, caps, sampling, `max_*` flags, timeouts, eviction, dtype/quantization, device placement, and container memory requests/limits.
   - Verify where limits apply. A cap applied after `read_*`, `to_pandas()`, `to_pylist()`, `list()`, `sorted()`, `collect()`, executor submission, or model prompt construction does not protect the earlier allocation.
   - Treat sentinel values such as `0 means all`, missing defaults, or user-provided unlimited lists as OOM-relevant when paired with large inputs, high concurrency, or large models.

5. Validate evidence.
   - Prefer file/line references, defaults, config values, documented dataset/model sizes, and existing OOM or memory logs.
   - Distinguish certain defects from scale-dependent risks and from benign large-memory code that is already bounded.
   - Do not claim runtime OOM from static code alone unless the evidence includes an unbounded path plus plausible size or concurrency.

6. Classify severity.
   - **Critical**: default or common path can OOM on documented production-scale input/model, or missing bounds can take down a service/job.
   - **High**: unbounded read/accumulation/concurrency/model context can OOM with realistic user-controlled or repo-documented scale.
   - **Medium**: bounded by defaults but easy to misconfigure, or only OOMs on large optional workloads.
   - **Low**: minor memory inefficiency or missing guardrail without a clear OOM path.
   - Include confidence: high when evidence links code, scale, and limits; medium when one element is inferred; low when exploratory.

7. Return an actionable report.
   - Lead with prioritized findings.
   - Include a coverage summary and explicit gaps.
   - Include task-state IDs and ID audit gaps when available. Keep them separate from OOM risk findings unless missing traceability blocks validation or hides unresolved task_miss evidence.
   - Note positive safeguards separately when they materially reduce risk: streaming iterators, bounded queues, mmap, dry-run/sample modes, telemetry, adaptive downshift, or regression tests.
   - Recommend mitigations that match the mechanism: streaming/chunking, smaller columns/projections, bounded queues, backpressure, batch-size caps, model quantization, mmap/read-only indexes, cache eviction, cleanup, worker limits, container limits, or regression tests.

## ID Traceability Add-on

- Use `$manage-task-state-index` only when task-state artifacts or an active task context are present.
- If no ID context exists, continue the OOM audit without penalty.
- Use `audit --write-report` when the OOM audit is part of completion validation or task governance.
- Do not assign OOM code inspection to an ID agent; it may only identify missing links among active task, OOM audit report, execution logs, validation report, and task_miss records.

## Output Shape

```text
Findings
- [Severity | Confidence] [domain] [file:line] Risk title.
  Mechanism: what allocates or retains memory.
  Scaling input: what makes it grow.
  Evidence: concrete code/config/log facts.
  Mitigation: specific next change or validation.

Risk Map
- CPU/RSS: ...
- GPU/VRAM: ...
- Container/build/test/runtime: ...

Coverage
- Inspected: paths/components and search themes.
- Not inspected: large/generated/external areas skipped.

Next Steps
- Highest-value fixes or profiling commands.
```

## Guardrails

- Do not modify repository files during an OOM audit unless the user also asks for fixes.
- Do not run commands that load full datasets, models, training jobs, benchmarks, or production services without explicit approval from the user.
- Treat generated artifacts, caches, and large logs as evidence sources by metadata and targeted search only.
- If the working directory is not a Git repository, continue the audit and say so in coverage rather than failing.
