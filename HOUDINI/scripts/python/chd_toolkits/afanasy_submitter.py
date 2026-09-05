"""Submit the current Houdini scene to Afanasy."""

import base64
import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SubmissionSettings:
    job_name: str
    hython_path: str
    rop_path: str
    frame_start: int
    frame_end: int
    frame_step: int = 1
    frames_per_task: int = 1
    capacity: int = 800
    priority: int = 80


def encode_text(value):
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


def decode_text(value):
    return base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")


def validate_settings(settings, hou_module, is_file=os.path.isfile):
    if not settings.job_name.strip():
        raise ValueError("Job Name is required.")
    if not is_file(settings.hython_path):
        raise ValueError("Hython executable does not exist.")
    if hou_module.hipFile.isNewFile():
        raise ValueError("Use Save As before submitting an untitled HIP file.")
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

    node = hou_module.node(settings.rop_path)
    if not isinstance(node, hou_module.RopNode):
        raise ValueError("Select a valid ROP node (hou.RopNode).")
    return node


def build_render_command(settings, hip_path):
    hip = encode_text(hip_path)
    rop = encode_text(settings.rop_path)
    code = (
        "import base64,hou;"
        "decode=lambda value:base64.urlsafe_b64decode(value).decode('utf-8');"
        f"hip=decode(b'{hip}');rop=decode(b'{rop}');"
        "hou.hipFile.load(hip,suppress_save_prompt=True);"
        "node=hou.node(rop);"
        "assert node is not None,'ROP node not found: '+rop;"
        "assert callable(getattr(node,'render',None)),'Node has no render(): '+rop;"
        f"node.render(frame_range=(@#@,@#@,{settings.frame_step}))"
    )
    executable = subprocess.list2cmdline([settings.hython_path])
    return f'{executable} -c "{code}"'


def submit_job(settings, hou_module, af_module, is_file=os.path.isfile):
    rop = validate_settings(settings, hou_module, is_file=is_file)
    hou_module.hipFile.save()
    hip_path = hou_module.hipFile.path()

    job = af_module.Job(settings.job_name.strip())
    job.setPriority(settings.priority)

    block = af_module.Block(rop.name(), "hbatch")
    block.setCommand(build_render_command(settings, hip_path))
    block.setNumeric(
        settings.frame_start,
        settings.frame_end,
        settings.frames_per_task,
        settings.frame_step,
    )
    block.setCapacity(settings.capacity)
    job.blocks.append(block)
    return job.send()


def session_defaults(hou_module, platform_name=os.name):
    hip_path = hou_module.hipFile.path()
    frame_start, frame_end = hou_module.playbar.playbackRange()
    executable = "hython.exe" if platform_name == "nt" else "hython"
    return {
        "job_name": os.path.splitext(os.path.basename(hip_path))[0],
        "hython_path": os.path.join(
            hou_module.getenv("HFS") or "", "bin", executable
        ),
        "frame_start": int(frame_start),
        "frame_end": int(frame_end),
        "frame_step": 1,
        "frames_per_task": 1,
        "capacity": 800,
        "priority": 80,
    }


_dialog_class_cache = {}


def _create_dialog_class(QtWidgets, hou_module, QtCore=None):
    if QtCore is None:
        try:
            from hutil.Qt import QtCore
        except ImportError:
            try:
                from PySide2 import QtCore
            except ImportError:
                try:
                    from PySide6 import QtCore
                except ImportError:
                    QtCore = None

    cache_key = (id(QtWidgets), id(hou_module))
    if cache_key in _dialog_class_cache:
        return _dialog_class_cache[cache_key]

    class AfanasySubmitterDialog(QtWidgets.QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            if hasattr(self, "setProperty"):
                self.setProperty("houdiniStyle", True)
            self.resize(360, 280)
            defaults = session_defaults(hou_module)
            self.setWindowTitle("Afanasy Submitter")

            self.job_name_edit = QtWidgets.QLineEdit(defaults["job_name"])
            self.hython_edit = QtWidgets.QLineEdit(defaults["hython_path"])
            self.rop_edit = QtWidgets.QLineEdit()
            self.rop_edit.setReadOnly(True)
            self.use_selected_rop = QtWidgets.QCheckBox("Use Selected ROP")

            self.frame_start_spin = self._spin(
                -1_000_000, 1_000_000, defaults["frame_start"]
            )
            self.frame_end_spin = self._spin(
                -1_000_000, 1_000_000, defaults["frame_end"]
            )
            self.frame_step_spin = self._spin(
                1, 1_000_000, defaults["frame_step"]
            )
            self.frames_per_task_spin = self._spin(
                1, 1_000_000, defaults["frames_per_task"]
            )
            self.capacity_spin = self._spin(
                1, 1_000_000, defaults["capacity"]
            )
            self.priority_spin = self._spin(
                0, 1_000_000, defaults["priority"]
            )

            hython_button = QtWidgets.QPushButton("Browse")
            rop_button = QtWidgets.QPushButton("Browse")
            self.submit_button = QtWidgets.QPushButton("Submit")
            hython_button.clicked.connect(self._browse_hython)
            rop_button.clicked.connect(self._browse_rop)
            self.submit_button.clicked.connect(self._on_submit)

            form = QtWidgets.QFormLayout(self)
            form.addRow("Job Name", self.job_name_edit)
            form.addRow("Hython", self._path_row(self.hython_edit, hython_button))
            form.addRow("ROP Node", self._path_row(self.rop_edit, rop_button))
            form.addRow(self.use_selected_rop)
            form.addRow("Frame Start", self.frame_start_spin)
            form.addRow("Frame End", self.frame_end_spin)
            form.addRow("Frame Step", self.frame_step_spin)
            form.addRow("Frames per task", self.frames_per_task_spin)
            form.addRow("Capacity", self.capacity_spin)
            form.addRow("Job Priority", self.priority_spin)
            form.addRow(self.submit_button)

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

        def _browse_hython(self):
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select hython", self.hython_edit.text()
            )
            if path:
                self.hython_edit.setText(path)

        def _browse_rop(self):
            path = hou_module.ui.selectNode(
                title="Select ROP Node",
                node_type_filter=hou_module.nodeTypeFilter.Rop,
            )
            if path:
                self.rop_edit.setText(path)

        def _settings_from_fields(self):
            rop_path = self.rop_edit.text()
            if self.use_selected_rop.isChecked():
                selected = hou_module.selectedNodes()
                if len(selected) != 1:
                    raise ValueError("Select exactly one ROP node in Houdini.")
                if not isinstance(selected[0], hou_module.RopNode):
                    raise ValueError("The selected node must inherit from hou.RopNode.")
                rop_path = selected[0].path()
            return SubmissionSettings(
                job_name=self.job_name_edit.text(),
                hython_path=self.hython_edit.text(),
                rop_path=rop_path,
                frame_start=self.frame_start_spin.value(),
                frame_end=self.frame_end_spin.value(),
                frame_step=self.frame_step_spin.value(),
                frames_per_task=self.frames_per_task_spin.value(),
                capacity=self.capacity_spin.value(),
                priority=self.priority_spin.value(),
            )

        def _on_submit(self):
            self.submit_button.setEnabled(False)
            try:
                import af

                settings = self._settings_from_fields()
                validate_settings(settings, hou_module)
                choice = hou_module.ui.displayMessage(
                    "Save the current HIP file and submit to Afanasy?\n\n"
                    + hou_module.hipFile.path(),
                    buttons=("OK", "Cancel"),
                    default_choice=1,
                    close_choice=1,
                    title="Save and Submit",
                )
                if choice != 0:
                    return
                status, data = submit_job(settings, hou_module, af)
                if not status:
                    raise RuntimeError(f"Afanasy submission failed: {data}")
                hou_module.ui.displayMessage(
                    f"Afanasy job submitted: {settings.job_name}"
                )
            except Exception as exc:
                hou_module.ui.displayMessage(
                    str(exc), severity=hou_module.severityType.Error
                )
            finally:
                self.submit_button.setEnabled(True)

        def closeEvent(self, event):
            global _dialog
            _dialog = None
            try:
                self.setParent(None)
            except Exception:
                pass
            if hasattr(event, "accept"):
                event.accept()

    _dialog_class_cache[cache_key] = AfanasySubmitterDialog
    return AfanasySubmitterDialog


_dialog = None


def _get_qt():
    for mod_name in ("hutil.Qt", "PySide2", "PySide6"):
        try:
            mod = __import__(mod_name, fromlist=["QtWidgets", "QtCore"])
            qt_widgets = getattr(mod, "QtWidgets", None)
            qt_core = getattr(mod, "QtCore", None)
            if qt_widgets is not None:
                return qt_widgets, qt_core
        except ImportError:
            pass
    raise ImportError("Neither hutil.Qt, PySide2, nor PySide6 could be imported.")


def _get_qt_widgets():
    QtWidgets, _ = _get_qt()
    return QtWidgets


def show(parent=None):
    global _dialog

    import hou

    QtWidgets, QtCore = _get_qt()

    if _dialog is None:
        dialog_class = _create_dialog_class(QtWidgets, hou, QtCore)
        _dialog = dialog_class(parent=parent)
        if parent is not None and QtCore is not None:
            flag_ns = getattr(
                getattr(QtCore, "Qt", None), "WindowType", getattr(QtCore, "Qt", None)
            )
            window_flag = getattr(flag_ns, "Window", None)
            if window_flag is not None and hasattr(_dialog, "setWindowFlags"):
                _dialog.setWindowFlags(window_flag)

    _dialog.show()
    _dialog.raise_()
    return _dialog
