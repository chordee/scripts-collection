"""Submit the current Nuke script to Afanasy.

Each checked Write node becomes one block of a single Afanasy job, rendered on
the farm with ``Nuke -x -X <write> -F <range> <script>``.
"""

import os
from pathlib import Path
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SubmissionSettings:
    job_name: str
    nuke_path: str
    write_names: tuple
    frame_start: int
    frame_end: int
    frame_step: int = 1
    frames_per_task: int = 1
    capacity: int = 800
    priority: int = 80
    use_nukex: bool = False
    # Writes whose block renders the Write's own Limit to Range instead of
    # Frame Start - Frame End.
    write_range_names: tuple = ()


AFANASY_SERVICE = "nuke"
WRITE_CLASS = "Write"

# PATH is deliberately absent: setEnv replaces the value on the worker rather
# than appending to it, so propagating the workstation's PATH wipes out
# whatever the farm put on the worker's own -- including directories Windows
# searches for DLLs. The worker's environment is the farm's to configure.
#
# Nuke-specific variables are listed by name, never by a NUKE_ / FN_ prefix:
# a running Nuke adds its own to the process environment -- a long license
# hash (NUKE_R_<build date>), NUKE_TEMP_DIR pointing at this workstation's temp
# folder, FN_ENT_* flags -- none of which belong on another machine.
ALLOWED_ENV_NAMES = frozenset({"NUKE_PATH", "PYTHONPATH", "OFX_PLUGIN_PATH", "OCIO"})
ALLOWED_ENV_PREFIXES = (
    "CGRU_",
    "RP_",
    "PUB_",
    "JOB_",
    "AXIOM_",
    "REZ_",
)
DISALLOWED_ENV_SUBSTRINGS = (
    "KEY",
    "TOKEN",
    "PASSWORD",
    "PASS",
    "SECRET",
    "PASSWD",
    "PWD",
    "CREDENTIAL",
    "AUTH",
    # License servers are the farm's to configure: a workstation serving its
    # own licenses has foundry_LICENSE set to 5053@localhost.
    "LICENSE",
)


def is_allowed_env_var(name: str) -> bool:
    """Return True if the environment variable is approved for farm propagation."""
    upper_name = name.upper()
    if any(sub in upper_name for sub in DISALLOWED_ENV_SUBSTRINGS):
        return False
    return upper_name in ALLOWED_ENV_NAMES or any(
        upper_name.startswith(prefix) for prefix in ALLOWED_ENV_PREFIXES
    )


def is_path_list_env_var(name: str) -> bool:
    """Return True if this variable's value is a list of paths."""
    upper_name = name.upper()
    return upper_name.endswith("PATH") or upper_name == "OCIO"


def expand_short_paths(value: str, platform_name=os.name) -> str:
    """Expand Windows 8.3 short path components ("PROGRA~1") to their long form.

    Short aliases are generated per volume on the machine that created the
    directory, so a farm worker may resolve one to a different directory, or
    not at all when 8dot3name is disabled. Only entries that contain "~" and
    exist on disk are rewritten, so non-path tokens pass through untouched.
    """
    if platform_name != "nt" or "~" not in value:
        return value
    expanded = []
    for part in value.split(os.pathsep):
        if "~" in part and os.path.exists(part):
            try:
                expanded.append(str(Path(part).resolve()))
            except OSError:
                expanded.append(part)
        else:
            expanded.append(part)
    return os.pathsep.join(expanded)


def to_forward_slashes(value: str, platform_name=os.name) -> str:
    """Rewrite Windows backslashes as forward slashes, which Nuke and Python accept."""
    if platform_name != "nt":
        return value
    return value.replace("\\", "/")


def farm_environment(environ=None, platform_name=os.name) -> dict:
    """The approved subset of ``environ``, with path lists made portable."""
    environ = os.environ if environ is None else environ
    result = {}
    for name, value in environ.items():
        if not is_allowed_env_var(name):
            continue
        value = str(value)
        if is_path_list_env_var(name):
            value = to_forward_slashes(
                expand_short_paths(value, platform_name), platform_name)
        result[name] = value
    return result


def list_write_nodes(nuke_module):
    # allNodes() with a class filter does not descend into groups even with
    # recurseGroups=True (confirmed in Nuke 17.0v1), so filter by hand.
    return [
        node for node in nuke_module.allNodes(recurseGroups=True)
        if node.Class() == WRITE_CLASS
    ]


def is_disabled(node) -> bool:
    knob = node.knobs().get("disable")
    return bool(knob.value()) if knob is not None else False


def default_write_names(nuke_module):
    """Selected Write nodes, or every enabled one when none is selected."""
    writes = list_write_nodes(nuke_module)
    selected = [node for node in writes if node.isSelected()]
    chosen = selected or [node for node in writes if not is_disabled(node)]
    return tuple(node.fullName() for node in chosen)


def limit_range(node):
    """The Write's (first, last) when Limit to Range is on, else None."""
    knobs = node.knobs()
    use_limit = knobs.get("use_limit")
    if use_limit is not None and use_limit.value():
        return int(knobs["first"].value()), int(knobs["last"].value())
    return None


def write_frame_range(node, frame_start, frame_end):
    """The Write's own range when Limit to Range is on, else the job's range."""
    return limit_range(node) or (frame_start, frame_end)


def block_frame_range(settings, node):
    """The range a Write's block renders, honouring ``write_range_names``."""
    if node.fullName() in settings.write_range_names:
        return write_frame_range(node, settings.frame_start, settings.frame_end)
    return settings.frame_start, settings.frame_end


def validate_settings(settings, nuke_module, is_file=os.path.isfile):
    if not settings.job_name.strip():
        raise ValueError("Job Name is required.")
    if not is_file(settings.nuke_path):
        raise ValueError("Nuke executable does not exist.")
    if nuke_module.root().name() == "Root":
        raise ValueError("Save the script before submitting an untitled Nuke script.")
    if not settings.write_names:
        raise ValueError("Check at least one Write node.")
    if settings.frame_start > settings.frame_end:
        raise ValueError("Frame Start must not exceed Frame End.")
    if settings.frame_step <= 0:
        raise ValueError("Frame Step must be greater than zero.")
    if settings.frames_per_task <= 0:
        raise ValueError("Frames per task must be greater than zero.")
    if settings.capacity <= 0:
        raise ValueError("Capacity must be greater than zero.")
    if settings.priority < 0:
        raise ValueError("Job Priority must not be negative.")

    writes = []
    for name in settings.write_names:
        node = nuke_module.toNode(name)
        if node is None or node.Class() != WRITE_CLASS:
            raise ValueError(f"Write node not found: {name}")
        if is_disabled(node):
            raise ValueError(f"Write node is disabled: {name}")
        start, end = block_frame_range(settings, node)
        if start > end:
            raise ValueError(f"Write node range is empty: {name} ({start}-{end})")
        writes.append(node)
    return writes


def build_render_command(settings, script_path, write_name, platform_name=os.name):
    args = [os.path.normpath(settings.nuke_path), "-x"]
    if settings.use_nukex:
        args.append("--nukex")
    args += [
        "-X", write_name,
        "-F", f"@#@-@#@x{settings.frame_step}",
        os.path.normpath(script_path),
    ]
    command = subprocess.list2cmdline(args)
    if platform_name == "nt":
        # Afanasy runs the command through cmd.exe, which strips the first and
        # last quote of the line; without this outer pair a quoted executable
        # path containing spaces would be cut at the first space.
        return f'"{command}"'
    return command


def submit_job(settings, nuke_module, af_module, is_file=os.path.isfile, environ=None):
    writes = validate_settings(settings, nuke_module, is_file=is_file)
    nuke_module.scriptSave()
    script_path = nuke_module.root().name()

    job = af_module.Job(settings.job_name.strip())
    job.setPriority(settings.priority)
    env = farm_environment(environ)

    for node in writes:
        name = node.fullName()
        start, end = block_frame_range(settings, node)
        block = af_module.Block(name, AFANASY_SERVICE)
        block.setCommand(build_render_command(settings, script_path, name))
        block.setNumeric(start, end, settings.frames_per_task, settings.frame_step)
        block.setCapacity(settings.capacity)
        if callable(getattr(block, "setEnv", None)):
            for env_key, env_val in env.items():
                block.setEnv(env_key, env_val)
        job.blocks.append(block)
    return job.send()


def session_defaults(nuke_module):
    root = nuke_module.root()
    script_path = root.name()
    return {
        "job_name": os.path.splitext(os.path.basename(script_path))[0],
        "nuke_path": os.path.normpath(nuke_module.EXE_PATH),
        "use_nukex": bool(nuke_module.env.get("nukex")),
        "write_names": default_write_names(nuke_module),
        "write_range_names": tuple(
            node.fullName() for node in list_write_nodes(nuke_module) if limit_range(node)
        ),
        "frame_start": int(root["first_frame"].value()),
        "frame_end": int(root["last_frame"].value()),
        "frame_step": 1,
        "frames_per_task": 1,
        "capacity": 800,
        "priority": 80,
    }


_dialog_class_cache = {}


def _create_dialog_class(QtWidgets, QtCore, nuke_module):
    cache_key = (id(QtWidgets), id(nuke_module))
    if cache_key in _dialog_class_cache:
        return _dialog_class_cache[cache_key]

    checked = QtCore.Qt.CheckState.Checked
    unchecked = QtCore.Qt.CheckState.Unchecked
    user_checkable = QtCore.Qt.ItemFlag.ItemIsUserCheckable
    enabled_flag = QtCore.Qt.ItemFlag.ItemIsEnabled
    name_role = QtCore.Qt.ItemDataRole.UserRole
    submit_column, range_option_column, range_column = 0, 1, 2

    class AfanasySubmitterDialog(QtWidgets.QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.resize(520, 520)
            self.setWindowTitle("Afanasy Submitter")
            defaults = session_defaults(nuke_module)

            self.job_name_edit = QtWidgets.QLineEdit(defaults["job_name"])
            self.nuke_edit = QtWidgets.QLineEdit(defaults["nuke_path"])
            self.nukex_checkbox = QtWidgets.QCheckBox("NukeX (--nukex)")
            self.nukex_checkbox.setChecked(defaults["use_nukex"])

            self.frame_start_spin = self._spin(-1_000_000, 1_000_000, defaults["frame_start"])
            self.frame_end_spin = self._spin(-1_000_000, 1_000_000, defaults["frame_end"])
            self.frame_step_spin = self._spin(1, 1_000_000, defaults["frame_step"])
            self.frames_per_task_spin = self._spin(1, 1_000_000, defaults["frames_per_task"])
            self.capacity_spin = self._spin(1, 1_000_000, defaults["capacity"])
            self.priority_spin = self._spin(0, 1_000_000, defaults["priority"])

            self._limits = {}
            self.write_table = self._build_write_table(
                set(defaults["write_names"]), set(defaults["write_range_names"]))
            self.write_table.itemChanged.connect(self._refresh_ranges)
            self.frame_start_spin.valueChanged.connect(self._refresh_ranges)
            self.frame_end_spin.valueChanged.connect(self._refresh_ranges)

            nuke_button = QtWidgets.QPushButton("Browse")
            self.submit_button = QtWidgets.QPushButton("Submit")
            nuke_button.clicked.connect(self._browse_nuke)
            self.submit_button.clicked.connect(self._on_submit)

            form = QtWidgets.QFormLayout(self)
            form.addRow("Job Name", self.job_name_edit)
            form.addRow("Nuke", self._path_row(self.nuke_edit, nuke_button))
            form.addRow(self.nukex_checkbox)
            form.addRow("Write Nodes", self.write_table)
            form.addRow("Frame Start", self.frame_start_spin)
            form.addRow("Frame End", self.frame_end_spin)
            form.addRow("Frame Step", self.frame_step_spin)
            form.addRow("Frames per task", self.frames_per_task_spin)
            form.addRow("Capacity", self.capacity_spin)
            form.addRow("Job Priority", self.priority_spin)
            form.addRow(self.submit_button)

        def _build_write_table(self, submit_names, range_names):
            writes = list_write_nodes(nuke_module)
            table = QtWidgets.QTableWidget(len(writes), 3)
            table.setHorizontalHeaderLabels(["Write", "Use Write Range", "Range"])
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setStretchLastSection(True)
            for row, node in enumerate(writes):
                name = node.fullName()
                limit = limit_range(node)
                self._limits[name] = limit

                label = f"{name}  (disabled)" if is_disabled(node) else name
                submit_item = QtWidgets.QTableWidgetItem(label)
                submit_item.setData(name_role, name)
                submit_item.setFlags(user_checkable | enabled_flag)
                submit_item.setCheckState(checked if name in submit_names else unchecked)
                table.setItem(row, submit_column, submit_item)

                # Only a Write with Limit to Range has a range of its own.
                option_item = QtWidgets.QTableWidgetItem()
                if limit:
                    option_item.setFlags(user_checkable | enabled_flag)
                    option_item.setCheckState(checked if name in range_names else unchecked)
                else:
                    option_item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
                    option_item.setToolTip("Limit to Range is off on this Write.")
                table.setItem(row, range_option_column, option_item)

                range_item = QtWidgets.QTableWidgetItem()
                range_item.setFlags(enabled_flag)
                table.setItem(row, range_column, range_item)
            self._fill_ranges(table)
            table.resizeColumnsToContents()
            return table

        def _fill_ranges(self, table):
            job_range = (self.frame_start_spin.value(), self.frame_end_spin.value())
            for row in range(table.rowCount()):
                name = table.item(row, submit_column).data(name_role)
                use_own = table.item(row, range_option_column).checkState() == checked
                start, end = self._limits[name] if use_own else job_range
                table.item(row, range_column).setText(f"{start}-{end}")

        def _refresh_ranges(self, *_):
            self.write_table.blockSignals(True)
            try:
                self._fill_ranges(self.write_table)
            finally:
                self.write_table.blockSignals(False)

        @staticmethod
        def _spin(minimum, maximum, value):
            spin = QtWidgets.QSpinBox()
            spin.setRange(minimum, maximum)
            spin.setValue(value)
            return spin

        @staticmethod
        def _path_row(line_edit, button):
            container = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(line_edit)
            layout.addWidget(button)
            return container

        def _browse_nuke(self):
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select Nuke executable", self.nuke_edit.text()
            )
            if path:
                self.nuke_edit.setText(path)

        def _names_checked_in(self, column):
            return tuple(
                self.write_table.item(row, submit_column).data(name_role)
                for row in range(self.write_table.rowCount())
                if self.write_table.item(row, column).checkState() == checked
            )

        def _checked_write_names(self):
            return self._names_checked_in(submit_column)

        def _write_range_names(self):
            return self._names_checked_in(range_option_column)

        def _settings_from_fields(self):
            return SubmissionSettings(
                job_name=self.job_name_edit.text(),
                nuke_path=self.nuke_edit.text(),
                write_names=self._checked_write_names(),
                frame_start=self.frame_start_spin.value(),
                frame_end=self.frame_end_spin.value(),
                frame_step=self.frame_step_spin.value(),
                frames_per_task=self.frames_per_task_spin.value(),
                capacity=self.capacity_spin.value(),
                priority=self.priority_spin.value(),
                use_nukex=self.nukex_checkbox.isChecked(),
                write_range_names=self._write_range_names(),
            )

        def _on_submit(self):
            self.submit_button.setEnabled(False)
            try:
                import af

                settings = self._settings_from_fields()
                validate_settings(settings, nuke_module)
                if not nuke_module.ask(
                    "Save the current script and submit to Afanasy?\n\n"
                    + nuke_module.root().name()
                ):
                    return
                status, data = submit_job(settings, nuke_module, af)
                if not status:
                    raise RuntimeError(f"Afanasy submission failed: {data}")
                nuke_module.message(f"Afanasy job submitted: {settings.job_name}")
            except Exception as exc:
                nuke_module.message(str(exc))
            finally:
                self.submit_button.setEnabled(True)

        def closeEvent(self, event):
            global _dialog
            _dialog = None
            event.accept()

    _dialog_class_cache[cache_key] = AfanasySubmitterDialog
    return AfanasySubmitterDialog


_dialog = None


def show():
    global _dialog

    import nuke
    from PySide6 import QtCore, QtWidgets

    if _dialog is None:
        dialog_class = _create_dialog_class(QtWidgets, QtCore, nuke)
        _dialog = dialog_class(parent=QtWidgets.QApplication.activeWindow())
        _dialog.setWindowFlags(QtCore.Qt.WindowType.Window)

    _dialog.show()
    _dialog.raise_()
    return _dialog
