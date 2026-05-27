import json
import subprocess
from Deadline.Scripting import *


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    if not jobs:
        return
    data = {"deadline_renderfarm_manager": {"job_id": [job.JobId for job in jobs]}}
    _copy(json.dumps(data, separators=(",", ":")))


def _copy(text):
    subprocess.run(
        ["clip.exe"],
        input=text.encode("utf-16-le"),
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
