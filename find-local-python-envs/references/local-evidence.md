# Local Dependency Evidence

Use this reference when ranking environments against repo-local dependency clues.

## Files To Inspect

- `pyproject.toml`: project dependencies, optional dependency groups, build backend, Python version constraints, Poetry/uv/PDM config.
- `requirements*.txt`: pip requirements, constraints, extra index URLs, editable installs with `-e`.
- `environment*.yml`, `conda*.yml`: conda env name, channels, Python version, conda packages, nested pip packages.
- `Pipfile`, `Pipfile.lock`: Pipenv packages and Python version.
- `poetry.lock`, `uv.lock`, `pdm.lock`: locked packages and env manager hints.
- `setup.py`, `setup.cfg`: install requirements, extras, console scripts, package discovery.
- `tox.ini`, `noxfile.py`: test matrix Python versions and dependency groups.
- `.python-version`, `.tool-versions`: pyenv/asdf version hints.
- Notebooks and scripts: imports that may not appear in manifests.

## Ranking Guidance

- Prefer project-local `.venv` or documented envs when they satisfy imports.
- Prefer conda envs for CUDA, compiled scientific packages, FAISS, PyTorch, TensorFlow, geospatial, and system-library-heavy stacks.
- Prefer lockfile-backed environments over global interpreters when dependency versions matter.
- Treat editable installs and repo-local packages as satisfied only when the chosen command runs from the correct working directory or has the package on `PYTHONPATH`.
- Separate Python package availability from external binaries and shared libraries; report system tools such as `ffmpeg`, `tesseract`, `cuda`, `nvcc`, `java`, or `node` as additional checks.

## Non-Mutating Checks

Use one-shot commands:

```bash
conda run -n ENV python -c "import importlib.util; print(importlib.util.find_spec('pkg') is not None)"
/path/to/.venv/bin/python -c "import sys; print(sys.executable); print(sys.version)"
poetry env info -p
pipenv --venv
uv python list
```

Avoid `pip install`, `poetry install`, `uv sync`, `conda install`, and lockfile updates unless the user explicitly asks to create or repair an environment.
