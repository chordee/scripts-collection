"""Tests for the Houdini Afanasy submitter."""

import os
import sys
import types
import unittest
from unittest import mock


PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)

from chd_toolkits.afanasy_submitter import (  # noqa: E402
    SubmissionSettings,
    _create_dialog_class,
    build_render_command,
    decode_text,
    encode_text,
    session_defaults,
    show,
    submit_job,
    validate_settings,
)


class FakeRop:
    def name(self):
        return "輸出"

    def render(self, frame_range):
        pass


class FakeHipFile:
    def __init__(self, path="D:/show/場景 test.hip", is_new=False):
        self._path = path
        self._is_new = is_new

    def path(self):
        return self._path

    def isNewFile(self):
        return self._is_new


class FakeHipFileWithSave(FakeHipFile):
    def __init__(self):
        super().__init__()
        self.saved = False

    def save(self):
        self.saved = True


class FakeHou:
    def __init__(self, node=None, path="D:/show/場景 test.hip", is_new=False):
        self.hipFile = FakeHipFile(path, is_new)
        self._node = node if node is not None else FakeRop()

    def node(self, path):
        return self._node


def make_settings(**changes):
    values = dict(
        job_name="render",
        hython_path="C:/Program Files/SideFX/Houdini/bin/hython.exe",
        rop_path="/out/輸出",
        frame_start=1,
        frame_end=12,
    )
    values.update(changes)
    return SubmissionSettings(**values)


class SubmitterPureTests(unittest.TestCase):
    def test_defaults(self):
        settings = make_settings()
        self.assertEqual(settings.frame_step, 1)
        self.assertEqual(settings.frames_per_task, 1)
        self.assertEqual(settings.capacity, 800)
        self.assertEqual(settings.priority, 80)

    def test_urlsafe_base64_round_trip(self):
        value = "D:/show/O'Brien/場景 \"test\".hip"
        encoded = encode_text(value)
        self.assertEqual(decode_text(encoded), value)
        self.assertNotIn(value, encoded)

    def test_validate_rejects_new_hip(self):
        with self.assertRaisesRegex(ValueError, "Save As"):
            validate_settings(
                make_settings(), FakeHou(is_new=True), is_file=lambda _: True
            )

    def test_validate_rejects_missing_rop(self):
        with self.assertRaisesRegex(ValueError, "ROP"):
            validate_settings(
                make_settings(), FakeHou(node=False), is_file=lambda _: True
            )

    def test_validate_rejects_invalid_numeric_values(self):
        invalid = (
            {"frame_start": 10, "frame_end": 1},
            {"frame_step": 0},
            {"frames_per_task": 0},
            {"capacity": 0},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_settings(
                    make_settings(**changes), FakeHou(), is_file=lambda _: True
                )

    def test_command_is_self_contained_and_has_two_frame_tokens(self):
        settings = make_settings(frame_step=3)
        command = build_render_command(settings, "D:/show/場景 test.hip")
        self.assertTrue(
            command.startswith(
                '"C:/Program Files/SideFX/Houdini/bin/hython.exe" -c '
            )
        )
        self.assertEqual(command.count("@#@"), 2)
        self.assertIn("urlsafe_b64decode", command)
        self.assertIn("hou.hipFile.load", command)
        self.assertIn("node.render(frame_range=(@#@,@#@,3))", command)
        self.assertNotIn("chd_toolkits", command)
        self.assertNotIn("場景", command)

        inline_code = command.split(' -c "', 1)[1][:-1]
        compile(inline_code.replace("@#@", "1"), "<afanasy-command>", "exec")


class FakeJob:
    def __init__(self, name, send_result):
        self.name = name
        self.priority = None
        self.blocks = []
        self._send_result = send_result

    def setPriority(self, priority):
        self.priority = priority

    def send(self):
        return self._send_result


class FakeBlock:
    def __init__(self, name, service):
        self.name = name
        self.service = service

    def setCommand(self, command):
        self.command = command

    def setNumeric(self, start, end, per_task, step):
        self.numeric = (start, end, per_task, step)

    def setCapacity(self, capacity):
        self.capacity = capacity


class FakeAf:
    last_job = None
    send_result = (True, {"id": 42})
    Block = FakeBlock

    @classmethod
    def Job(cls, name):
        cls.last_job = FakeJob(name, cls.send_result)
        return cls.last_job


class SubmitterJobTests(unittest.TestCase):
    def test_submit_job_saves_and_sends_expected_objects(self):
        hou_module = FakeHou()
        hou_module.hipFile = FakeHipFileWithSave()
        FakeAf.send_result = (True, {"id": 42})
        status, data = submit_job(
            make_settings(frames_per_task=4),
            hou_module,
            FakeAf,
            is_file=lambda _: True,
        )
        self.assertTrue(hou_module.hipFile.saved)
        self.assertTrue(status)
        self.assertEqual(data, {"id": 42})
        job = FakeAf.last_job
        self.assertEqual(job.priority, 80)
        self.assertEqual(len(job.blocks), 1)
        block = job.blocks[0]
        self.assertEqual(block.name, "輸出")
        self.assertEqual(block.service, "hbatch")
        self.assertEqual(block.numeric, (1, 12, 4, 1))
        self.assertEqual(block.capacity, 800)

    def test_submit_job_does_not_save_when_validation_fails(self):
        hou_module = FakeHou()
        hou_module.hipFile = FakeHipFileWithSave()
        with self.assertRaises(ValueError):
            submit_job(
                make_settings(frame_step=0),
                hou_module,
                FakeAf,
                is_file=lambda _: True,
            )
        self.assertFalse(hou_module.hipFile.saved)

    def test_submit_job_returns_send_failure_unchanged(self):
        hou_module = FakeHou()
        hou_module.hipFile = FakeHipFileWithSave()
        FakeAf.send_result = (False, {"error": "server unavailable"})
        result = submit_job(
            make_settings(), hou_module, FakeAf, is_file=lambda _: True
        )
        self.assertEqual(result, FakeAf.send_result)


class SubmitterDefaultsTests(unittest.TestCase):
    def test_default_values_use_current_houdini_session(self):
        hou_module = FakeHou(path="D:/show/shot010.hip")
        hou_module.getenv = lambda name: "C:/Program Files/SideFX/Houdini"
        hou_module.playbar = type(
            "Playbar",
            (),
            {"playbackRange": staticmethod(lambda: (1001.0, 1100.0))},
        )()
        defaults = session_defaults(hou_module, platform_name="nt")
        self.assertEqual(defaults["job_name"], "shot010")
        self.assertEqual(
            defaults["hython_path"],
            os.path.join(
                "C:/Program Files/SideFX/Houdini", "bin", "hython.exe"
            ),
        )
        self.assertEqual(defaults["frame_start"], 1001)
        self.assertEqual(defaults["frame_end"], 1100)
        self.assertEqual(defaults["priority"], 80)
        self.assertEqual(defaults["capacity"], 800)


class FakeSignal:
    def connect(self, callback):
        self.callback = callback


class FakeDialog:
    def __init__(self, parent=None):
        self.parent = parent
        self.closed = False
        self.deleted = False
        self.visible = False

    def setWindowTitle(self, title):
        self.window_title = title

    def close(self):
        self.closed = True

    def deleteLater(self):
        self.deleted = True

    def show(self):
        self.visible = True

    def raise_(self):
        self.raised = True

    def activateWindow(self):
        self.activated = True


class FakeLineEdit:
    def __init__(self, text=""):
        self._text = text
        self.read_only = False

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def setReadOnly(self, value):
        self.read_only = value


class FakeSpinBox:
    def setRange(self, minimum, maximum):
        self.value_range = (minimum, maximum)

    def setValue(self, value):
        self._value = value

    def value(self):
        return self._value


class FakePushButton:
    def __init__(self, text):
        self.text = text
        self.clicked = FakeSignal()
        self.enabled = True

    def setEnabled(self, value):
        self.enabled = value


class FakeWidget:
    pass


class FakeLayout:
    def __init__(self, parent=None):
        self.parent = parent
        self.rows = []

    def setContentsMargins(self, *margins):
        self.margins = margins

    def addWidget(self, widget):
        self.rows.append(widget)

    def addRow(self, *items):
        self.rows.append(items)


class FakeFileDialog:
    selected_path = ""

    @classmethod
    def getOpenFileName(cls, parent, title, path):
        return cls.selected_path, ""


class FakeQtWidgets:
    QDialog = FakeDialog
    QLineEdit = FakeLineEdit
    QSpinBox = FakeSpinBox
    QPushButton = FakePushButton
    QWidget = FakeWidget
    QHBoxLayout = FakeLayout
    QFormLayout = FakeLayout
    QFileDialog = FakeFileDialog


class FakeUi:
    def __init__(self):
        self.selected_node = "/out/farm_rop"
        self.messages = []

    def selectNode(self, **kwargs):
        self.select_node_kwargs = kwargs
        return self.selected_node

    def displayMessage(self, message, severity=None):
        self.messages.append((message, severity))


class SubmitterDialogTests(unittest.TestCase):
    def setUp(self):
        self.hou_module = FakeHou(path="D:/show/shot010.hip")
        self.hou_module.hipFile = FakeHipFileWithSave()
        self.hou_module.getenv = lambda name: "C:/Program Files/SideFX/Houdini"
        self.hou_module.playbar = type(
            "Playbar",
            (),
            {"playbackRange": staticmethod(lambda: (1001.0, 1100.0))},
        )()
        self.hou_module.ui = FakeUi()
        self.hou_module.nodeTypeFilter = type("NodeTypeFilter", (), {"Rop": "rop"})
        self.hou_module.severityType = type("SeverityType", (), {"Error": "error"})
        self.hou_module.qt = type(
            "Qt", (), {"mainWindow": staticmethod(lambda: "main-window")}
        )()

    def test_dialog_defaults_and_rop_selector(self):
        dialog_class = _create_dialog_class(FakeQtWidgets, self.hou_module)
        dialog = dialog_class(parent="main-window")
        self.assertEqual(dialog.window_title, "Afanasy Submitter")
        self.assertEqual(dialog.job_name_edit.text(), "場景 test")
        self.assertTrue(dialog.rop_edit.read_only)
        self.assertEqual(dialog.frames_per_task_spin.value(), 1)
        self.assertEqual(dialog.capacity_spin.value(), 800)
        self.assertEqual(dialog.priority_spin.value(), 80)

        dialog._browse_rop()
        self.assertEqual(dialog.rop_edit.text(), "/out/farm_rop")
        self.assertEqual(
            self.hou_module.ui.select_node_kwargs["node_type_filter"], "rop"
        )

        FakeFileDialog.selected_path = "D:/custom/hython.exe"
        dialog._browse_hython()
        self.assertEqual(dialog.hython_edit.text(), "D:/custom/hython.exe")

    def test_submit_button_saves_and_reports_success(self):
        dialog_class = _create_dialog_class(FakeQtWidgets, self.hou_module)
        dialog = dialog_class()
        dialog.hython_edit.setText(sys.executable)
        dialog.rop_edit.setText("/out/farm_rop")
        FakeAf.send_result = (True, {"id": 42})

        with mock.patch.dict(sys.modules, {"af": FakeAf}):
            dialog._on_submit()

        self.assertTrue(self.hou_module.hipFile.saved)
        self.assertTrue(dialog.submit_button.enabled)
        self.assertEqual(
            self.hou_module.ui.messages[-1],
            ("Afanasy job submitted: 場景 test", None),
        )

    def test_show_replaces_previous_dialog(self):
        self.hou_module.hipFile = FakeHipFile(path="D:/show/shot010.hip")
        pyside = types.ModuleType("PySide6")
        pyside.QtWidgets = FakeQtWidgets

        import chd_toolkits.afanasy_submitter as submitter

        submitter._dialog = None
        with mock.patch.dict(
            sys.modules, {"hou": self.hou_module, "PySide6": pyside}
        ):
            first = show()
            second = show()

        self.assertTrue(first.closed)
        self.assertTrue(first.deleted)
        self.assertIs(second, submitter._dialog)
        self.assertEqual(second.parent, "main-window")
        self.assertTrue(second.visible)
        self.assertTrue(second.raised)
        self.assertTrue(second.activated)

    def test_submit_error_is_displayed_and_button_is_reenabled(self):
        dialog_class = _create_dialog_class(FakeQtWidgets, self.hou_module)
        dialog = dialog_class()
        dialog.job_name_edit.setText("")

        with mock.patch.dict(sys.modules, {"af": FakeAf}):
            dialog._on_submit()

        self.assertEqual(
            self.hou_module.ui.messages[-1], ("Job Name is required.", "error")
        )
        self.assertTrue(dialog.submit_button.enabled)


if __name__ == "__main__":
    unittest.main()
