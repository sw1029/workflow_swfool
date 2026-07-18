---
name: find-local-python-envs
description: Inventory local Python execution environments and rank usable candidates for code that requires specific dependencies. Use when the user asks which conda env, virtualenv, venv, system Python, Poetry/Pipenv/uv-managed environment, local editable package, or dependency stack can run a script/test/notebook/tool; when imports fail and Codex needs to find an existing environment rather than install packages; or when Codex needs to return commands such as `conda run -n ...`, `path/to/python ...`, or activation instructions for a dependency-constrained execution.
---

# Find Local Python Envs

## Overview

Use this skill to find local Python environments that can execute code with required dependencies. Prefer existing environments and local dependency evidence before proposing installation.

The main output is a ranked list of runnable environment candidates with evidence, missing dependencies, and exact execution commands.

`authority.operations.json` declares the read-only inventory operation under the shared [authority v2 contract](../manage-agent-authority/references/authority-v2-contract.md). It grants no write capability; any durable task-index or work-log update remains a separate operation owned by the corresponding writer skill.

When a task-state index exists, record environment evidence through `$manage-task-state-index` as an optional traceability add-on. If no ID context exists, perform the normal environment discovery unchanged.

## Workflow

1. Identify the execution requirement.
   - Extract required imports, package distributions, Python version constraints, GPU/CPU needs, system tools, entry command, and project path.
   - If the user gives code, scan imports and dependency files before running anything.
   - If dependency names are ambiguous, load [dependency-name-mapping.md](references/dependency-name-mapping.md).

2. Inspect local dependency evidence.
   - Check project files such as `pyproject.toml`, `requirements*.txt`, `environment*.yml`, `conda*.yml`, `Pipfile`, `poetry.lock`, `uv.lock`, `setup.py`, `setup.cfg`, `tox.ini`, `noxfile.py`, and notebooks.
   - Note editable/local packages, repo-relative imports, environment variables, CUDA/toolchain hints, and documented activation commands.
   - Load [local-evidence.md](references/local-evidence.md) when multiple project managers or local editable dependencies are present.

3. Inventory available environments.
   - Run the bundled scanner when Python dependencies are involved:

     ```bash
     SKILLS_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
     PYTHONPATH="$SKILLS_ROOT/find-local-python-envs/scripts" \
       python3 -m find_local_python_envs inventory --root . --dep pandas --dep pyarrow --json
     ```

   - Replace dependencies with the user's required packages. Use `--dep distribution=import_name` when the pip/conda distribution name differs from the import name.
   - If the script is unavailable or insufficient, manually inspect `conda env list --json`, `VIRTUAL_ENV`, `CONDA_PREFIX`, common `.venv` paths, `which -a python python3`, and project manager commands such as `poetry env info -p`, `pipenv --venv`, or `uv python list`.

4. Verify candidates lightly.
   - Prefer import/version checks over running the user's workload.
   - Use commands that do not install or mutate state, such as `python -c "import pkg; print(pkg.__version__)"`.
   - For GPU dependencies, verify module availability separately from GPU runtime availability; a package can import while CUDA is unusable.

5. Rank environments.
   - Rank highest when all required imports resolve, Python version matches, the env is project-local or documented by the repo, and the execution command is direct.
   - Rank lower when only distributions are present without import proof, when Python version is mismatched, when CUDA/system libraries are uncertain, or when the env is global and unrelated.
   - Mark unusable environments explicitly when key dependencies are missing.

6. Return commands and caveats.
   - Provide exact commands, for example `conda run -n ENV python script.py`, `/path/to/.venv/bin/python -m pytest`, or `source .venv/bin/activate`.
   - Include missing dependency names, uncertain system requirements, and any checks not performed.
   - Do not install packages, create environments, or modify activation files unless the user asks.

7. Update task-state IDs when possible.
   - If `.task/index.jsonl`, `.task/index.md`, `task.md`, or `.agent_log/` exists, run `$manage-task-state-index` `scan` and `audit`.
   - If an active task ID exists and the environment result is persisted as a report or `.agent_log` entry, add an `environment` artifact and link it with `environment_for:<task-id>` or `environment_for:<run-id>`.
   - If the environment result is only returned in chat and no durable artifact exists, do not invent a path; report that ID linkage was skipped.
   - If the workflow authorizes agents and ID context exists, an additional read-only ID insight agent may suggest links. Do not give that agent dependency discovery or environment ranking work.

## Output Shape

```text
Best Candidates
- [Rank] [env name/type] [python version] [path]
  Fit: all required deps present / missing ...
  Evidence: import/version checks, local manifest match, documented command.
  Run: exact command to execute the requested code.

Other Candidates
- Env and reason it is weaker or unusable.

Dependency Evidence
- Project files and local packages inspected.

Gaps
- Checks not performed, system/CUDA uncertainty, or dependency-name ambiguity.
- ID traceability skipped or unresolved, when applicable.
```

## Guardrails

- Do not run package installation, environment creation, lockfile updates, or destructive cleanup during environment discovery.
- Do not activate an environment in a way that changes the user's shell session; prefer one-shot commands such as `conda run` or absolute interpreter paths.
- Avoid importing heavy modules just to inspect availability when `importlib.util.find_spec` and package metadata are enough.
- If a command could start training, serving, notebooks, or a long benchmark, only return the command unless the user explicitly asks to execute it.
