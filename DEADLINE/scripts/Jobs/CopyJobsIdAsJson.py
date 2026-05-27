import json
from Deadline.Scripting import *
import System.Windows.Forms as Forms


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    if not jobs:
        return
    data = {"deadline_renderfarm_manager": {"job_id": [job.JobId for job in jobs]}}
    Forms.Clipboard.SetText(json.dumps(data, separators=(",", ":")))
