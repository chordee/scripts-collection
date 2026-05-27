import clr
clr.AddReference("System.Windows.Forms")
from System.Windows.Forms import Clipboard
from Deadline.Scripting import *


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    tasks = MonitorUtils.GetSelectedTasks()
    if not jobs or not tasks:
        return
    parts = [jobs[-1].JobId] + [str(task.TaskId) for task in tasks]
    Clipboard.SetText(" ".join(parts))
