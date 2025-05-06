#!/usr/bin/env python3
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
# NAME:         PDGDeadline.py ( Python )
#
# COMMENTS:     Custom Deadline plugin for Houdini TOP Deadline scheduler.
#               Supports PDG work items as tasks inside a single PDG job.
#               Task data is provided via a task file that the caller has written out.
#               The current frame corresponds to the task file's identity.
#               Evaluates PDG variables locally and sets process environment.

import os
import shlex
import sys
import json
import re
import traceback
import glob

# pylint: disable=import-error,no-member,undefined-variable
from System import DateTime, TimeSpan
from System.IO import *
from System.Text.RegularExpressions import *

from Deadline.Scripting import *
from Deadline.Plugins import *

from FranticX.Processes import *

# MQ server connection expression
conn_reg = re.compile(r'PDG_MQ (\S+) (\d+) (\d+)')
conn_reg_pdgutilset = re.compile(r'PDG_MQ (\S+) (\d+) (\d+) (\d+)')

def GetDeadlinePlugin():
    return PDGDeadlinePlugin()

def CleanupDeadlinePlugin(deadlinePlugin):
    deadlinePlugin.Cleanup()
    
## PDG_PATHMAP string generator -- Chordee
def PDG_PATHMAP_Generator():
    pathmap_data = {}
    pathmap_data["version"] = 3
    pathmap_data["paths"] = []
    for disk_letter in "HIJKLMNOPQRSTZ":
        path_data = {}
        sub_data = {}
        sub_data['path'] = '/mnt/{0}'.format(disk_letter)
        sub_data['zone'] = "LINUX"
        sub_data['scheduler'] = ""
        sub_data['matchtype'] = 0
        path_data[disk_letter + ":"] = sub_data
        pathmap_data['paths'].append(path_data)
    return str(pathmap_data).replace("'", '"')

class PDGDeadlinePlugin(DeadlinePlugin):
    def __init__(self):
        super(PDGDeadlinePlugin, self).__init__()

        self.InitializeProcessCallback += self.InitializeProcess
        self.RenderTasksCallback += self.RenderTasks

        # Timeout for waiting on task file (milliseconds)
        self.taskFileTimeout = 1E5

        #Managed process handle.
        self.wProcess = None

    def Cleanup(self):
        for stdoutHandler in self.StdoutHandlers:
            del stdoutHandler.HandleCallback

        del self.InitializeProcessCallback
        del self.RenderTasksCallback
        del self.EndJobCallback
        del self.MonitoredProgramExitCallback

        #Clean up managed process:
        if self.wProcess:
            self.wProcess.Cleanup()
            del self.wProcess

    def InitializeProcess(self):
        self.LogInfo('*********** PDGDeadline InitializeProcess')
        self.SingleFramesOnly = False
        self.PluginType = PluginType.Advanced
        self.StdoutHandling = True

    def _exeValue(self):
        """
        Based on os return exe extention.
        """
        if sys.platform == 'win32':
            return '.exe'
        return ''
        
    def _hythonPath(self, hfs_env):
        """
        Based on os, return hython path.
        """
        # Chordee Linux Mapping
        re_pattern = '\d\d\.\d\.\d\d\d'
        version = re.findall(re_pattern, hfs_env)[0]
        win_hfs = 'Q:/Resource/hfs-' + version
        lin_hfs = '/mnt/Q/Resource/hfs-' + version + '-linux'
        if sys.platform == 'win32':
            #return hfs_env + '/bin/hython.exe'
            return win_hfs + '/bin/hython.exe'
        #return hfs_env + '/bin/hython'
        return lin_hfs + '/bin/hython'

    def RenderTasks(self):
        """
        Executes a single frame as a task by looking up the task info file
        and parsing the command, expands local environment variables,
        and executes as a child process.
        """
        try:
            startFrame = self.GetStartFrame()
            self.LogInfo('StartFrame: {}'.format(startFrame))
            #self.LogInfo ('ThreadNumber: {}'.format(self.GetThreadNumber()))
            #self.LogInfo ('Current Task: {}'.format(self.GetCurrentTaskId()))

            startupDir = self.GetStartupDirectory()

            path_combine = ':'
            if sys.platform == 'win32':
                path_combine = ';'

            job = self.GetJob()
            if not job:
                self.FailRender("No job is running!")
            json_obj = None

            pdgJobType = job.GetJobExtraInfoKeyValue('PDGJobType')
            if pdgJobType == 'MQJob':
                executable = job.GetJobExtraInfoKeyValue('MQExecutable')
                arguments = job.GetJobExtraInfoKeyValue('MQArgs')
                if not executable or not arguments:
                    self.FailRender('No MQExecutable or MQArgs in job key-values.')

                executable = RepositoryUtils.CheckPathMapping(executable)
                arguments = RepositoryUtils.CheckPathMapping(arguments)
            elif pdgJobType == 'ServiceJob':
                executable = job.GetJobExtraInfoKeyValue('ServiceExecutable')
                arguments = job.GetJobExtraInfoKeyValue('ServiceArgs')
                if not executable or not arguments:
                    self.FailRender('No MQExecutable or MQArgs in job key-values.')

                executable = RepositoryUtils.CheckPathMapping(executable)
                arguments = RepositoryUtils.CheckPathMapping(arguments)
            else:
                # The PDG job directory will contain the task file
                jobDir = self.GetPluginInfoEntryWithDefault('PDGJobDirectory', '')
                if not jobDir:
                    self.FailRender('PDGJobDirectory is not specified. Unable to get task file.')

                jobDir = RepositoryUtils.CheckPathMapping(jobDir)

                # Task job
                taskFile = job.GetJobExtraInfoKeyValue("PDG_TaskFile")
                taskFilePath = os.path.join(jobDir, taskFile)

                self.LogInfo('Looking for task file: {}'.format(taskFilePath))

                # Wait until task file has been synchronized.
                taskFileTimeout = job.GetJobExtraInfoKeyValue("PDG_TaskFileTimeout")
                if taskFileTimeout:
                    self.taskFileTimeout = int(taskFileTimeout)
                line = self.WaitForCommandFile(taskFilePath, False, self.taskFileTimeout)
                if not line:
                    self.FailRender('Task file not found at {}'.format(taskFilePath))

                executable = None
                arguments = ''

                try:
                    # Load the task file's data as json dict and process properties
                    json_obj = json.loads(line)

                    platform = ''
                    if sys.platform.startswith('win'):
                        platform = 'windows'
                    elif sys.platform.startswith('linux'):
                        platform = 'linux'
                    elif sys.platform.startswith('darwin'):
                        platform = 'macosx'

                    try:
                        executable_key = 'executable_{}'.format(platform)
                        arg_key = 'arguments_{}'.format(platform)

                        executable = RepositoryUtils.CheckPathMapping(
                            json_obj[executable_key].replace( "\"", "" ))

                        str_args = json_obj[arg_key]
                    except:
                        executable = RepositoryUtils.CheckPathMapping(
                            json_obj['executable'].replace( "\"", "" ))

                        str_args = json_obj['arguments']


                    # We have to path map each argument individually.
                    # We cannot path map the entire argument string because Deadline
                    # fails to path map multiple paths found in the same string.
                    if sys.platform == "win32":
                        cmd_args = shlex.split(str_args, posix=False)
                    else:
                        cmd_args = ['\"{}\"'.format(item) for item in shlex.split(str_args, posix=True)]
                    mapped_cmd_args = []
                    for arg in cmd_args:
                        mapped_cmd_args.append(RepositoryUtils.CheckPathMapping(arg))

                    # shelx.join() treats enclosing double quotes around each
                    # argument as a part of the argument value, which is the 
                    # correct behavior for Windows but is unwanted for our 
                    # case because the call then adds additional enclosing
                    # single quotes around each argument.  We want the
                    # enclosing double quotes to *not* be treated as a part 
                    # of the argument value when joining so we call " ".join()
                    # instead.
                    arguments = " ".join(mapped_cmd_args)
                except:
                    self.FailRender('Unable to parse task file as json\n\t {}'.format(traceback.format_exc(1)))

            work_item_path = None

            # Set the PDG work item environment variables from the task file.
            # Note that this needs to be done before the SetProcessEnvironmentVariable that
            # come after since those should properly override the work item env vars.
            
            #Chordee PDG_PATHMAP  *** if-block below this line edited ***
            if json_obj and 'pdg_item_env' in json_obj:
                pdg_item_env = json_obj['pdg_item_env']
                
                if sys.platform.startswith('linux'):
                    ## Inject PDG_PATHMAP into pdg_item_env dict Before SetProcessEnvironmentVariable -- Chordee
                    pdg_pathmap_val = PDG_PATHMAP_Generator()
                    pdg_item_env['PDG_PATHMAP'] = pdg_pathmap_val
                    self.LogInfo('PDG_PATHMAP set {0}'.format(pdg_pathmap_val))
                    

                try:
                    for key, var in pdg_item_env.items():
                        if key.startswith('AVALON') or key.startswith('PDG_') or str(key) == 'PYTHONPATH': 
                            # only AVALON and PDG env vars are set to the task - Chordee
                            
                            ## Force check linux path via Deadline - Chordee
                            if var and sys.platform.startswith('linux'):
                                if 'http' not in str(var) and str(key) != 'PDG_PATHMAP':
                                    if str(key) == 'PYTHONPATH':
                                        # Remove any python module cause conflicts with HTOA
                                        vars = [v for v in str(var).split(';') if not v.endswith('lib/python_modules/python3')]
                                        var = ';'.join(vars)
                                        var = RepositoryUtils.CheckPathMapping(str(var))
                                    elif str(key) == 'AVALON_DEADLINE_AUTH':
                                        # Avoid path mapping with AVALON_DEADLINE_AUTH
                                        # since it is a string and not a path
                                        var = var
                                    else:
                                        var = RepositoryUtils.CheckPathMapping(str(var))
                            ##
                            if key == 'HOUDINI_PATH':
                                # Instead of stomping HOUDINI_PATH we prepend it
                                var_local = os.environ.get(key, '')
                                if var_local:
                                    var = var.replace(';&', '')
                                    var = var + path_combine + var_local
                                if 'HTOA' in pdg_item_env:
                                    # HTOA is a special case since it is not a path - Chordee
                                    if platform == 'windows':
                                        var = str(pdg_item_env['HTOA']) + ";" + var
                                    elif platform == 'linux':
                                        var =  RepositoryUtils.CheckPathMapping(str(pdg_item_env['HTOA'])).replace('platform-windows','platform-linux') + ":" + var
                            # null json value mean unsetenv
                            if var is None:
                                self.SetProcessEnvironmentVariable(str(key), None)
                            else:
                                self.SetProcessEnvironmentVariable(str(key), str(var) if platform == 'windows' else str(var).replace('platform-windows', 'platform-linux').replace('\\', '/').replace(';',':'))

                    if 'PATH' in pdg_item_env:
                        work_item_path = pdg_item_env['PATH'].replace('__PDG_PATHSEP__', path_combine)
                        self.LogInfo('Changing work item PATH {0} to {1}'.format(pdg_item_env['PATH'], work_item_path))
                except:
                    self.LogWarning('Exception when trying to set env var from task!\n\t {}'.format(traceback.format_exc(1)))

            # Have to add $HFS to sys path otherwise dll loading issues when
            # importing python modules
            hfs_bin = None
            hfs_env = job.GetJobEnvironmentKeyValue('PDG_HFS')
            if not hfs_env:
                self.LogWarning(
                    "$PDG_HFS not found in job environment. "
                    "Houdini jobs might fail.")
                hfs_env = ''
            else:
                # Evaluate HFS to local and append to end of PATH
                hfs_env = RepositoryUtils.CheckPathMapping(hfs_env)
                # Chordee Linux Mapping
                if sys.platform.startswith('linux'):
                    if os.path.exists(hfs_env + '-linux'):
                        hfs_env += '-linux'
                    else:
                        re_pattern = '\d\d\.\d\.\d\d\d'
                        version = re.findall(re_pattern, hfs_env)[0]
                        all_ver_hfs_linux = glob.glob('/mnt/Q/Resource/hfs-' + version[:4] + '*-linux')
                        if all_ver_hfs_linux:
                            max_version_hfs = sorted(all_ver_hfs_linux, reverse=True)[0]
                            hfs_env = max_version_hfs
                            
                hfs_bin = hfs_env + '/bin'
                self.LogInfo('HFS set to {0}, Houdini Bin set to {1}.'.format(hfs_env, hfs_bin))

            # Set PATH environment if it was set in work item environment and/or
            # if HFS was found in the environment.
            # Note that work item environment PATH takes precendance over local PATH.
            set_path = None
            if hfs_bin:
                if work_item_path:
                    set_path = '{}{}{}'.format(work_item_path, path_combine, hfs_bin)
                    self.LogInfo('Setting work item PATH with HFS: {}'.format(set_path))
                elif 'PATH' in os.environ:
                    set_path = '{}{}{}'.format(os.environ['PATH'], path_combine, hfs_bin)
                    self.LogInfo('Setting os PATH with HFS: {}'.format(set_path))
                else:
                    set_path = hfs_bin
            elif work_item_path:
                set_path = work_item_path
                self.LogInfo('Setting work item PATH: {}'.format(set_path))

            if set_path:
                self.SetProcessEnvironmentVariable('PATH', set_path)

            executable = executable.replace('$PDG_EXE', self._exeValue())

            if sys.platform == 'darwin':
                if hfs_env:
                    # Append $PYTHONPATH if not set
                    houdini_python_libs = hfs_env + '/Frameworks/Houdini.framework' \
                        '/Versions/Current/Resources/houdini/python2.7libs'
                    python_path = self.GetProcessEnvironmentVariable('PYTHONPATH')
                    if python_path:
                        if houdini_python_libs not in python_path:
                            python_path.append(path_combine + houdini_python_libs)
                    else:
                        python_path = houdini_python_libs

                    self.LogInfo('Setting PYTHONPATH: {}'.format(python_path))
                    self.SetProcessEnvironmentVariable('PYTHONPATH', python_path)


            if executable == '$HYTHON' and hfs_env:
                # Map Hython for local platform
                executable = executable.replace('$HYTHON', self._hythonPath(hfs_env))
                self.LogInfo('$HYTHON mapped to: {}'.format(executable))

            arguments = arguments.replace('\\', '/')

            # Evaluate all PDG job vars
            self.ConvertEnv(job, 'PDG_TEMP')
            self.ConvertEnv(job, 'PDG_SHARED_TEMP')
            self.ConvertEnv(job, 'PDG_SCRIPTDIR')
            self.ConvertEnv(job, 'PDG_DIR')
            self.ConvertEnv(job, 'PDG_HFS')
            self.ConvertEnv(job, 'PYTHON')

            # set pythonlibs, 
            
            python_version_major = job.GetJobEnvironmentKeyValue('PYTHON_VERSION_MAJOR')
            python_version_minor = job.GetJobEnvironmentKeyValue('PYTHON_VERSION_MINOR')
            self.SetProcessEnvironmentVariable( "HHP", 
                                                "{}/houdini/python{}.{}libs".format(hfs_env, 
                                                                                    python_version_major, 
                                                                                    python_version_minor) )

            # Convert PDG_JOBID to actual job ID
            self.SetProcessEnvironmentVariable('PDG_JOBID', job.JobId)

            # Set batch name which is used when using SubmitAsJob
            self.SetProcessEnvironmentVariable("PDG_JOB_BATCH_NAME", str(job.JobBatchName))

            submit_as_job = False

            if json_obj:
                # Evaluate work item specific PDG vars
                self.SetPDGEnvFromJson(json_obj, 'pdg_item_name', 'PDG_ITEM_NAME')
                self.SetPDGEnvFromJson(json_obj, 'pdg_index', 'PDG_INDEX')
                self.SetPDGEnvFromJson(json_obj, 'pdg_item_id', 'PDG_ITEM_ID')

                submit_as_job = json_obj.get('submit_as_job', 'False') == 'True'
                self.LogInfo("Submit as job: {}".format(submit_as_job))
                
                # Set for making the subsequent job use local MQ
                self.SetProcessEnvironmentVariable("PDG_SUBMIT_AS_JOB", str(submit_as_job))

                if not submit_as_job:

                    # The HTTP port might not be set when using CommandServer,
                    # so force waiting for the connection file in that case.
                    env_httpport = job.GetJobEnvironmentKeyValue( 'PDG_HTTP_PORT' )
                    if env_httpport == 'None':
                        env_httpport = None

                    if not json_obj.get('pdg_result_server', None) or not env_httpport:
                        # Wait for connection file since we don't have server address
                        mq_conn_file_path = job.GetJobEnvironmentKeyValue( 'PDG_MQ_CONN_FILE' )
                        mq_conn_file_path = RepositoryUtils.CheckPathMapping( mq_conn_file_path )
                        self.LogInfo('Waiting for MQ connection file {}'.format(mq_conn_file_path))
                        mqinfo = self.WaitForCommandFile(mq_conn_file_path, False, self.taskFileTimeout)
                        if not mqinfo:
                            self.FailRender('Timed out waiting for MQ connection file at {}'.format(mq_conn_file_path))

                        parsed = self.ParseMQStdout(mqinfo)
                        if parsed:
                            host, rpcport, _, httpport = parsed
                            json_obj['pdg_result_server'] = '{}:{}'.format(host, rpcport)
                            json_obj['pdg_http_port'] = httpport

                    self.SetPDGEnvFromJson(json_obj, 'pdg_result_server', 'PDG_RESULT_SERVER')
                    self.LogInfo('PDG_RESULT_SERVER: {}'.format(json_obj.get('pdg_result_server', None)))

                    self.SetPDGEnvFromJson(json_obj, 'pdg_http_port', 'PDG_HTTP_PORT')
                    self.LogInfo('PDG_HTTP_PORT: {}'.format(json_obj.get('pdg_http_port', 0)))
                
                # Set GPU overrides if specified and valid for this worker
                gpu_list = self.GetGpuOverrides(json_obj)
                if gpu_list and len(gpu_list) > 0:
                    gpus = ",".join(gpu_list)

                    # Set the gpus argument for rop.py which does the render
                    if arguments.find('rop.py') >= 0:
                        self.SetProcessEnvironmentVariable("HOUDINI_GPU_LIST",
                                                           gpus)

                    # Set OpenCL override in environment
                    if json_obj.get('opencl_forcegpu', 0) > 0:
                        self.SetProcessEnvironmentVariable("HOUDINI_OCL_DEVICETYPE", "GPU")
                        self.SetProcessEnvironmentVariable("HOUDINI_OCL_VENDOR", "")
                    self.SetProcessEnvironmentVariable("HOUDINI_OCL_DEVICENUMBER",
                            gpu_list[self.GetThreadNumber() % len(gpu_list)])
                
                if 'extra_infos' in json_obj:
                    task = self.GetCurrentTask()
                    extra_infos = json_obj['extra_infos']
 
                    print('extra infos: ', extra_infos)
                    for attr_name, value in extra_infos.items():
                        setattr(task.Properties, attr_name, value)

                    RepositoryUtils.UpdateTaskProperties(task.JobID, task)

            if "$HYTHON" in arguments and hfs_env:
                # Map Hython for local platform
                arguments = arguments.replace('$HYTHON', self._hythonPath(hfs_env))
            
            arguments = arguments.replace('$PDG_EXE', self._exeValue())
            
            # if it is a rop cooking, add rpcstart option, 
            # so the start time recorded for cookDuration calculation.
            if arguments.find('rop.py') >= 0:
                tokens = arguments.split(" ")
                if tokens[-1]=="":
                    tokens.pop(-1)
                if "args" in tokens[-1] or "json" in tokens[-1]:
                    tokens.append("--rpcstart")
                    arguments = ' '.join(tokens)

            self.LogInfo('Task Executable: %s' % executable)
            self.LogInfo('Task Arguments: %s' % arguments)

            self.LogInfo("Invoking: Run Managed Process")
            self.wProcess = WorkItemProcess(self, executable, arguments, startupDir, hfs_bin)            
            self.RunManagedProcess(self.wProcess)
            exitCode = self.wProcess.ExitCode
            # exitCode = self.RunProcess( executable, arguments, startupDir, -1 )

            if exitCode != 0:
                # In some situations, user wants to ignore the exit code (such as with 3dscmd)
                if json_obj and json_obj.get('dl_ignoreexit', 0) == 0:
                    self.FailRender('Process returned non-zero exit code: {}'.format(exitCode))
                else:
                    self.LogWarning('Process returned non-zero exit code: {}'.format(exitCode))
        except:
            self.FailRender('PDGDeadline exception: {}'.format(traceback.format_exc(1)))

    def GetStartupDirectory(self):
        startupDir = self.GetPluginInfoEntryWithDefault('StartupDirectory', '').strip()
        if startupDir != '':
            startupDir = RepositoryUtils.CheckPathMapping(startupDir)
            self.LogInfo('Startup Directory: %s' % startupDir)
        return startupDir


    def ConvertEnv( self, job, varname ):
        """
        Updates given job's varname environment value with converted mapping.
        The converted value should have been set in the Mapped Paths
        of Deadline's Repository Options .
        """
        incomingEnvVar = job.GetJobEnvironmentKeyValue( varname )
        convertedEnvVar = RepositoryUtils.CheckPathMapping( incomingEnvVar )
        self.SetProcessEnvironmentVariable( varname, convertedEnvVar )

    def SetPDGEnvFromJson(self, json_obj, json_key, pdg_key):
        if json_key in json_obj:
            self.SetProcessEnvironmentVariable( pdg_key, str(json_obj[json_key]) )

    def GetGpuOverrides(self, json_obj):
        """
        Return list of gpu IDs that should be used for this task.
        """
        resultGPUs = []

        # If the number of gpus per task is set, then need to calculate the gpus to use.
        gpusPerTask = json_obj.get("gpus_per_task", 0)
        gpusSelectDevices = json_obj.get("gpus_select_devices", "")

        # Check slave's GPU override to match those specified by user for this job
        if self.OverrideGpuAffinity():
            overrideGPUs = self.GpuAffinity()
            if gpusPerTask == 0 and gpusSelectDevices != "":
                gpus = gpusSelectDevices.split( "," )
                notFoundGPUs = []
                for gpu in gpus:
                    if int( gpu ) in overrideGPUs:
                        resultGPUs.append( gpu )
                    else:
                        notFoundGPUs.append( gpu )

                if len( notFoundGPUs ) > 0:
                    self.LogWarning( "The Slave is overriding its GPU affinity and the following GPUs do not match the Slaves affinity so they will not be used: " + ",".join( notFoundGPUs ) )
                if len( resultGPUs ) == 0:
                    self.FailRender( "The Slave does not have affinity for any of the GPUs specified in the job." )
            elif gpusPerTask > 0:
                if gpusPerTask > len( overrideGPUs ):
                    self.LogWarning( "The Slave is overriding its GPU affinity and the Slave only has affinity for " + str( len( overrideGPUs ) ) + " gpus of the " + str( gpusPerTask ) + " requested." )
                    resultGPUs =  [ str( gpu ) for gpu in overrideGPUs ]
                else:
                    resultGPUs = [ str( gpu ) for gpu in overrideGPUs if gpu < gpusPerTask ]
            else:
                resultGPUs = [ str( gpu ) for gpu in overrideGPUs ]
        elif gpusPerTask == 0 and gpusSelectDevices != "":
            resultGPUs = gpusSelectDevices.split( "," )

        elif gpusPerTask > 0:
            gpuList = []
            #self.LogInfo("!!! GPU: " + str(( self.GetThreadNumber() * gpusPerTask )) + " to " + str(( self.GetThreadNumber() * gpusPerTask ) + gpusPerTask))
            for i in range( ( self.GetThreadNumber() * gpusPerTask ), ( self.GetThreadNumber() * gpusPerTask ) + gpusPerTask ):
                gpuList.append( str( i ) )
            resultGPUs = gpuList

        resultGPUs = list( resultGPUs )
        return resultGPUs


    @staticmethod
    def ParseMQStdout(txt):
        """
        Parse and return the MQ server's connection info
        """
        m = conn_reg_pdgutilset.search(txt)
        if m:
            return (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))
        return None

class WorkItemProcess(ManagedProcess):
    """
    Custom managed process to run in RenderTasks,
    so we can handle output/error and other callbacks in the subprocess.
    """
    deadlinePlugin = None

    def __init__(self, deadlinePlugin, executable, argument, directory, hfs_bin):
        super(WorkItemProcess, self).__init__()

        self.deadlinePlugin = deadlinePlugin
        # hython executable has to be full path
        if executable == "hython":
            executable = os.path.join(hfs_bin, executable)
        self.Executable = RepositoryUtils.CheckPathMapping(executable)
        self.Argument = argument
        self.Directory = directory
        self.ExitCode = -1

        self.InitializeProcessCallback += self.InitializeProcess
        self.RenderExecutableCallback += self.RenderExecutable
        self.RenderArgumentCallback += self.RenderArgument
        self.StartupDirectoryCallback += self.StartupDirectory
        self.CheckExitCodeCallback += self.CheckExitCode

    def Cleanup(self):
        for stdoutHandler in self.StdoutHandlers:
            del stdoutHandler.HandleCallback

        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback
        del self.StartupDirectoryCallback
        del self.CheckExitCodeCallback

    def InitializeProcess(self):
        self.StdoutHandling = True
        # Ensure child processes are killed and the parent process is terminated on exit
        self.UseProcessTree = True
        self.TerminateOnExit = True

        self.AddStdoutHandlerCallback(
            '.*[Ee]rror: .*'
        ).HandleCallback += self.HandleStdoutError
        self.AddStdoutHandlerCallback(
            '.*ERROR[: ].*'
        ).HandleCallback += self.HandleStdoutError
        self.AddStdoutHandlerCallback(
            '.*Fatal error: Segmentation fault.*'
        ).HandleCallback += self.HandleStdoutError
        self.AddStdoutHandlerCallback(
            '.*(No licenses could be found to run this application).*'
        ).HandleCallback += self.HandleStdoutLicense
        self.AddStdoutHandlerCallback(
            '.*TRACEBACK.*'
        ).HandleCallback += self.HandleStdoutError
        self.AddStdoutHandlerCallback(
            r'.*Progress: (\d+)%.*'
        ).HandleCallback += self.HandleProgress

    def RenderExecutable(self):
        return self.Executable

    def RenderArgument(self):
        return self.Argument

    def HandleStdoutError(self):
        self.deadlinePlugin.FailRender(self.GetRegexMatch(0))

    def HandleStdoutLicense(self):
        self.deadlinePlugin.FailRender(self.GetRegexMatch(1))

    def StartupDirectory(self):
        return self.Directory

    def CheckExitCode(self, exitCode):
        self.ExitCode = exitCode

    def HandleProgress(self):
        progress = float(self.GetRegexMatch(1))
        self.deadlinePlugin.SetProgress(progress)
