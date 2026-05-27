from Deadline.Scripting import *
import System.Windows.Forms as Forms


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    if not jobs:
        return
    Forms.Clipboard.SetText(" ".join(job.JobId for job in jobs))
