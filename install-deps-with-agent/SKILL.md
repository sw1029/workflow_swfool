---
name: install-deps-with-agent
description: Assign exactly one agent to install missing dependencies or perform long-running downloads only after cache-first local discovery. Use when a user task needs unavailable Python packages, model checkpoints, datasets, wheels, build assets, or other slow/cacheable downloads; when imports fail and installation may be needed; or when an implementation/run task would block on dependency setup. Always use `$find-local-python-envs` first to check existing local Python environments and reusable cache-like evidence before installing.
---

# Install Deps With Agent

## Overview

Use this skill to keep dependency setup separate from implementation work. The coordinator first checks for reusable local environments and caches, then assigns one agent to install or download only what is still missing.

The preferred outcome is reuse of an existing environment or cache. Installation is the fallback, not the first step.

## Authority Boundary

Use `authority.operations.json` with the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). Cache and environment inspection is read-only. An install and an artifact download are distinct grant-controlled operations; bind the exact dependency subject, destination/environment, effect, risk, attempt, budget, and external-input state before assigning the install agent. Reserve and reverify immediately before the first write or dispatch, consume when an install/download effect occurred, and release only on verified no-effect. Network, license, credential, global-environment, system-package, destructive-cleanup, and lockfile effects remain separate and cannot be inferred from a generic dependency request.

## Workflow

1. Define the requirement.
   - Extract required packages, import names, versions, Python version, GPU/CUDA needs, system tools, model or dataset IDs, expected artifact paths, and the command that will consume the dependency.
   - Classify the need as `python_package`, `model_cache`, `dataset_cache`, `build_asset`, `system_tool`, or `unknown`.
   - If the requirement is unclear, inspect local project manifests before asking the user.

2. Check local Python environments first.
   - Use `$find-local-python-envs` before any install or download attempt.
   - Ask it to inspect the current project and rank environments for the required imports/packages.
   - Treat an environment as usable when it can run the intended command or import checks without installation.
   - If a usable environment exists, return its command and stop; do not install.

3. Check cache-like local evidence.
   - Inspect relevant cache roots without deleting or mutating them:
     - Python package caches: `pip cache dir`, `uv cache dir`, conda `pkgs_dirs`.
     - Model and dataset caches: `$HF_HOME`, `$HF_DATASETS_CACHE`, `$TRANSFORMERS_CACHE`, `$TORCH_HOME`, `~/.cache/huggingface`, `~/.cache/torch`, and project-local cache directories.
     - Tool caches when relevant: npm, pnpm, yarn, Maven, Gradle, cargo, Go module cache, or documented project cache paths.
   - Treat a cache as usable only when the expected artifact exists and the consuming command can be pointed at it without a download.
   - Prefer project-documented cache locations and lockfiles over global guesses.

4. Decide whether to install.
   - Do not install when a ranked environment or cache can satisfy the task.
   - Do not install system packages with `sudo`, mutate global shells, delete caches, or change lockfiles unless the user explicitly requested that scope.
   - Prefer project-local or user-local installs over global installs.
   - For large downloads, choose a stable cache directory and log path before starting.

5. Assign exactly one install agent.
   - Use available subagent or multi-agent tooling to start one agent whose only job is dependency setup.
   - Keep implementation, code edits, task derivation, and validation outside this install agent unless the user explicitly combined those goals.
   - Give the agent the raw requirement, workspace path, cache findings, selected environment candidate if any, allowed install/cache path, verification command, and logging expectations.
   - Do not spawn additional install agents. If the first install agent fails, inspect the failure and either retry yourself with the same scope or ask the user when the next action is risky.

6. Install or download in the agent.
   - The agent should install only the missing dependency or download only the missing artifact.
   - The agent should capture command lines, exit status, package versions, artifact paths, cache paths, and any PID/log path for long-running work.
   - The agent should verify with the cheapest meaningful check, such as `python -c "import pkg"`, `pip show`, checksum/file existence, or an offline load test.
   - For long-running downloads, the agent should report monitor and stop commands when possible.

7. Report the result.
   - State whether the requirement was satisfied by existing cache/environment or by agent install.
   - Provide the exact run command or environment activation command for downstream work.
   - Include cache paths, installed versions, verification command/results, and remaining gaps.
   - If installation was not performed, state the reason.

## Install Agent Prompt Shape

Use this shape for the single install agent:

```text
Use $install-deps-with-agent as the install worker for this dependency setup only.

Workspace:
- <absolute path>

Requirement:
- <packages/imports/model IDs/dataset IDs/artifact names/versions>

Cache-first findings:
- <find-local-python-envs result and cache paths checked>

Allowed actions:
- Install/download only the missing dependency or artifact.
- Prefer <project-local/user-local/cache path>.
- Do not edit implementation code or unrelated project files.
- Do not use sudo, delete caches, or modify lockfiles unless explicitly listed here.

Verification:
- Run <cheap verification command>.
- Report command, exit status, version/artifact path, cache path, and any remaining blocker.
```

## Output Shape

```text
Dependency Setup Result
- Requirement:
- Resolution: existing_environment | existing_cache | installed_by_agent | not_installed
- Agent used: yes | no
- Environment/run command:
- Cache/artifact paths:
- Verification:
- Remaining blockers:
```

## Guardrails

- Always run `$find-local-python-envs` before installation for Python-related requirements.
- Prefer reuse of existing environments and caches over downloading again.
- Never run destructive cleanup of environments, package caches, model caches, or datasets.
- Never install secrets, private tokens, credentials, or license-restricted artifacts without explicit user-provided access instructions.
- Never use `sudo` or global package managers for system-level changes unless the user explicitly requests that exact scope.
- Never let the install agent modify source code to make an import pass; code changes belong to the implementation workflow.
- If network access, disk space, license acceptance, or authentication blocks installation, report the blocker instead of inventing credentials or alternate sources.
