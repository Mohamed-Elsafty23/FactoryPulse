"""Summarise a Databricks job run from `runs/get` JSON on stdin.

Prints one line: `<life_cycle_state> | task:state task:state ...`
Used by deploy-databricks.sh so the shell never has to parse JSON.
"""

import json
import sys

run = json.load(sys.stdin)
tasks = sorted(run.get("tasks", []), key=lambda t: t["task_key"])


def state_of(task: dict) -> str:
    state = task.get("state", {})
    return state.get("result_state") or state.get("life_cycle_state") or "?"


summary = " ".join(f"{t['task_key']}:{state_of(t)}" for t in tasks)
print(run.get("state", {}).get("life_cycle_state", "?"), "|", summary)
