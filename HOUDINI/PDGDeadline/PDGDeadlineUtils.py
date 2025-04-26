#
# Copyright (c) <2020> Side Effects Software Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# NAME:         PDGDeadlineUtils.py ( Python )
#
# COMMENTS:     Contains utility functions for TOP Deadline scheduler.
#               Requires to be executed with Deadline command.
#				The functions provided by this script allow to use the
#				Deadline Python API as a workaround for lack of the same
#				functionality in the Deadline command itself.

from __future__ import absolute_import

# pylint: disable=import-error,undefined-variable
from Deadline.Scripting import *
from Deadline.Plugins import *

from Deadline.Reports import *

def __main__(*args):
    """
    Deadline command calls this with arguments.
    It parses the first argument and calls the corresponding utility function.
    """
    if not args or len(args) < 2:
        log_err('Bad arguments.')
        return

    func = args[0]

    if func == 'get_task_log':
        return get_task_log(*args)
    else:
        log_err('{} not supported!'.format(func))


def log_err(msg):
    print('Error: {}'.format(msg), flush=True)


def get_task_log(*args):
    """
    Prints out the task report file of specified task of the specified job.
    """
    if len(args) != 3:
        log_err('get_task_log requires 2 arguments: job_id task_id')
        return

    job_id = args[1]
    task_id = args[2]

    if job_id and task_id:
        task_id = int(task_id)

        job_reports = RepositoryUtils.GetJobReports(job_id)
        if job_reports:
            task_reports = job_reports.GetTaskLogReports(task_id)
            if not task_reports:
                # It might have been an error, so try getting the error report
                task_reports = job_reports.GetTaskErrorReports(task_id)
            if task_reports and len(task_reports) > 0:
                print('Report={}'.format(RepositoryUtils.GetJobReportLogFileName(task_reports[0])), flush=True)
                return

    log_err('No report for given job or task!')
