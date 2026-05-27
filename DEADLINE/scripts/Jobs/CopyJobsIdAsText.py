import subprocess
from Deadline.Scripting import *


def __main__(*args):
    jobs = MonitorUtils.GetSelectedJobs()
    if not jobs:
        return
    _copy((" ".join(job.JobId for job in jobs)))


def _copy(text):
    subprocess.run(
        ["clip"],
        input=text.encode("utf-16-le"),
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
