"""Version-portable, isolated Python module process construction."""

from __future__ import annotations

from os import PathLike, fspath
from pathlib import Path
import stat
from typing import Sequence


ISOLATED_MODULE_BOOTSTRAP = (
    "import runpy,sys;"
    "count=int(sys.argv[1]);"
    "roots=sys.argv[2:2+count];"
    "module=sys.argv[2+count];"
    "arguments=sys.argv[3+count:];"
    "sys.path[:0]=roots;"
    "sys.argv=[module,*arguments];"
    "runpy.run_module(module,run_name='__main__',alter_sys=True)"
)


def isolated_module_argv(
    executable: str,
    module: str,
    arguments: Sequence[str],
    import_roots: Sequence[str | PathLike[str]],
) -> list[str]:
    """Build a CPython 3.10+ command with no cwd or user import surface."""

    if (
        not isinstance(executable, str)
        or not Path(executable).is_absolute()
        or "\x00" in executable
        or not isinstance(module, str)
        or not module
        or "\x00" in module
        or any(not isinstance(argument, str) or "\x00" in argument for argument in arguments)
    ):
        raise ValueError(
            "Isolated module execution requires an absolute executable and safe strings."
        )
    roots: list[str] = []
    for raw_root in import_roots:
        root = fspath(raw_root)
        if not isinstance(root, str) or "\x00" in root:
            raise ValueError("Isolated module import roots must be text paths.")
        path = Path(root)
        if not path.is_absolute():
            raise ValueError(
                "Isolated module import roots must be canonical real directories."
            )
        try:
            resolved = path.resolve(strict=True)
            mode = path.lstat().st_mode
        except OSError as exc:
            raise ValueError("Isolated module import roots must exist.") from exc
        if (
            path != resolved
            or stat.S_ISLNK(mode)
            or not stat.S_ISDIR(mode)
        ):
            raise ValueError(
                "Isolated module import roots must be canonical real directories."
            )
        roots.append(str(path))
    if not roots:
        raise ValueError("Isolated module execution requires an executable, module, and roots.")
    return [
        executable,
        "-B",
        "-I",
        "-c",
        ISOLATED_MODULE_BOOTSTRAP,
        str(len(roots)),
        *roots,
        module,
        *arguments,
    ]


__all__ = ["ISOLATED_MODULE_BOOTSTRAP", "isolated_module_argv"]
