import clr
clr.AddReference("System.Windows.Forms")
from System.Windows.Forms import Clipboard
from Deadline.Scripting import *


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    if not jobs:
        return
    Clipboard.SetText(" ".join(job.JobId for job in jobs))
