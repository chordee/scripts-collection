from Deadline.Scripting import *
import System.Windows.Forms as Forms


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    tasks = MonitorUtils.GetSelectedTasks()
    if not jobs or not tasks:
        return
    parts = [jobs[-1].JobId] + [str(task.TaskId) for task in tasks]
    Forms.Clipboard.SetText(" ".join(parts))
