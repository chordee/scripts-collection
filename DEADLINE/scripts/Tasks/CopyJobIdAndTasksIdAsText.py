import subprocess
from Deadline.Scripting import *


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    tasks = MonitorUtils.GetSelectedTasks()
    if not jobs or not tasks:
        return
    parts = [jobs[-1].JobId] + [str(task.TaskId) for task in tasks]
    _copy(" ".join(parts))


def _copy(text):
    subprocess.run(
        ["clip.exe"],
        input=text.encode("utf-16-le"),
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
