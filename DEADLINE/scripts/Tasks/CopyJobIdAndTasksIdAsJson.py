import json
import subprocess
from Deadline.Scripting import *


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    tasks = MonitorUtils.GetSelectedTasks()
    if not jobs or not tasks:
        return
    data = {"deadline_renderfarm_manager": {
        "job_id": jobs[-1].JobId,
        "task_ids": [task.TaskId for task in tasks],
    }}
    _copy(json.dumps(data, separators=(",", ":")))


def _copy(text):
    subprocess.run(
        ["clip.exe"],
        input=text.encode("utf-16-le"),
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
