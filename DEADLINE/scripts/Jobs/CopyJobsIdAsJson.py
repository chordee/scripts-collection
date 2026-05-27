import clr
clr.AddReference("System.Windows.Forms")
from System.Windows.Forms import Clipboard
import json
from Deadline.Scripting import *


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    if not jobs:
        return
    data = {"deadline_renderfarm_manager": {"job_id": [job.JobId for job in jobs]}}
    Clipboard.SetText(json.dumps(data, separators=(",", ":")))
