import os
import subprocess
import hou
from PySide2 import QtCore, QtUiTools, QtWidgets, QtGui

startupinfo = None
creationflags = 0x08000000


def parseOutput(output):
    """
    Decodes the given output bytes and splits it into a list of strings by Windows line endings.

    Args:
        output (bytes): The output from a subprocess, expected as bytes.

    Returns:
        list: List of strings, each representing a line from the decoded output.
    """
    result = output.decode().split("\r\n")
    return result


def insertEnv(parm, env):
    """
    Inserts a new environment variable entry into a Houdini multiparm parameter.

    Args:
        parm: The multiparm parameter to insert the environment variable into.
        env (str): The name of the environment variable to insert.

    Side Effects:
        Modifies the multiparm parameter by adding a new instance and setting its value.
    """
    parm.insertMultiParmInstance(0)
    parm.multiParmInstances()[0].set(env)
    parm.multiParmInstances()[1].set(os.environ[env].replace("\\", "/"))


def setEnv(parm, envs):
    """
    Sets environment variable values for a Houdini multiparm parameter, adding new entries as needed.

    Args:
        parm: The multiparm parameter containing environment variable entries.
        envs (list): List of environment variable names to set.

    Side Effects:
        Updates the multiparm parameter with the values of the specified environment variables.
        Adds new entries for any environment variables not already present.
    """
    instances = parm.multiParmInstances()
    envname_parms = list()
    env_val_parms = list()
    for i in instances:
        if "envname" in i.name():
            envname_parms.append(i)
        else:
            env_val_parms.append(i)

    for idx, i in enumerate(envname_parms):
        env_name = i.eval()
        if i.eval() in envs:
            env_val_parms[idx].set(os.environ[env_name].replace("\\", "/"))
            index = envs.index(env_name)
            envs.pop(index)

    if len(envs) > 0:
        for i in envs:
            insertEnv(parm, i)


class Dialog(QtWidgets.QWidget):
    def __init__(self, node, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.node = node
        self.initUI()

    def initUI(self):
        self.groups_combo = QtWidgets.QComboBox()
        self.pools_combo = QtWidgets.QComboBox()
        self.set_btn = QtWidgets.QPushButton("Set")

        main_v_layout = QtWidgets.QVBoxLayout()
        pools_h_layout = QtWidgets.QHBoxLayout()
        groups_h_layout = QtWidgets.QHBoxLayout()

        pools_h_layout.addWidget(QtWidgets.QLabel("Pools:"))
        pools_h_layout.addWidget(self.pools_combo)

        groups_h_layout.addWidget(QtWidgets.QLabel("Groups:"))
        groups_h_layout.addWidget(self.groups_combo)

        main_v_layout.addWidget(QtWidgets.QLabel(node.path()))
        main_v_layout.addLayout(pools_h_layout)
        main_v_layout.addLayout(groups_h_layout)
        main_v_layout.addWidget(self.set_btn)

        self.setLayout(main_v_layout)

        self.set_btn.clicked.connect(self.auto_fit)

    def setComboBoxItems(self, items, combo_type="groups"):
        if combo_type == "groups":
            combo = self.groups_combo
        elif combo_type == "pools":
            combo = self.pools_combo
        else:
            return

        for ind, item in enumerate(items):
            combo.insertItem(ind, item)

    def auto_fit(self):
        group = self.groups_combo.currentText()
        pool = self.pools_combo.currentText()
        node.parm("deadline_jobgroup").set(group)
        node.parm("deadline_jobpool").set(pool)
        node.parm("deadline_mqjobgroup").set(group)
        node.parm("deadline_mqjobpool").set(pool)
        # node.parm('mqusage').set(0)
        node.parm("deadline_mqjobpriority").set(80)
        node.parm("pdg_rpctimeout").set(10)
        node.parm("pdg_rpcretries").set(5)
        if hou.applicationVersion()[0] == 20 or hou.applicationVersion()[0] == 19:
            node.parm("deadline_overrideplugin").set(1)
            if hou.applicationVersion()[0] == 20 and hou.applicationVersion()[1] == 5:
                node.parm("deadline_plugindirectory").set(
                    "Q:/Resource/H205_PDGDeadline"
                )
            else:
                node.parm("deadline_plugindirectory").set("Q:/Resource/H20_PDGDeadline")
            node.parm("deadline_copyplugin").set(0)
            if node.parm("deadline_cmdinheritlocalenv"):
                node.parm("deadline_cmdinheritlocalenv").set(1)

        self.close()


node = hou.selectedNodes()[0]

if node.type().name() == "deadlinescheduler":
    q_hfs = "Q:/Resource/hfs-" + hou.applicationVersionString()
    hfs = (
        "C:/Program Files/Side Effects Software/Houdini "
        + hou.applicationVersionString()
    )
    exe = "hython\\$PDG_EXE"
    if os.path.exists(q_hfs):
        node.parm("deadline_hfs").set(q_hfs)
    else:
        node.parm("deadline_hfs").set(hfs)
    node.parm("deadline_python").set(exe)
    node.parm("deadline_inheritlocalenv").set(1)
    node.parm("deadline_ignoreexitcode").set(0)
    node.parm("deadline_verboselog").set(1)
    node.parm("deadline_jobpriority").set(80)
    node.parm("deadline_repository").set("//deadline/DeadlineRepository10")

    deadlineBin = os.environ["DEADLINE_PATH"]

    deadlineCommand = os.path.join(deadlineBin, "deadlinecommand.exe -Pools")
    proc = subprocess.Popen(
        deadlineCommand,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        creationflags=creationflags,
    )
    output, err = proc.communicate()
    pools = parseOutput(output)

    deadlineCommand = os.path.join(deadlineBin, "deadlinecommand.exe -Groups")
    proc = subprocess.Popen(
        deadlineCommand,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        creationflags=creationflags,
    )
    output, err = proc.communicate()
    groups = parseOutput(output)

    dialog = Dialog(node=node)
    dialog.setComboBoxItems(groups, combo_type="groups")
    dialog.setComboBoxItems(pools, combo_type="pools")
    dialog.show()
