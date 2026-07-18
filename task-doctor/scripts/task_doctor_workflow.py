#!/usr/bin/env python3
"""Stable facade for the task-doctor workflow coordinator."""

from task_doctor_workflow_lib import *  # noqa: F401,F403
from task_doctor_workflow_lib.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
