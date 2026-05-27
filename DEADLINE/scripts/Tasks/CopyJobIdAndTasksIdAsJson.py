import clr
clr.AddReference("System.Windows.Forms")
from System.Windows.Forms import Clipboard
import json
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
    Clipboard.SetText(json.dumps(data, separators=(",", ":")))
