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
    _get_qt_widgets,
    build_render_command,
    decode_text,
    encode_text,
    is_allowed_env_var,
    session_defaults,
    show,
    submit_job,
    validate_settings,
)


class FakeRop:
    def path(self):
        return "/out/selected_rop"

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
    RopNode = FakeRop

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
        self.env = {}

    def setCommand(self, command):
        self.command = command

    def setNumeric(self, start, end, per_task, step):
        self.numeric = (start, end, per_task, step)

    def setCapacity(self, capacity):
        self.capacity = capacity

    def setEnv(self, name, value):
        self.env[name] = value


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

    def test_is_allowed_env_var(self):
        self.assertTrue(is_allowed_env_var("PATH"))
        self.assertTrue(is_allowed_env_var("PYTHONPATH"))
        self.assertTrue(is_allowed_env_var("SIDEFXLABS"))
        self.assertTrue(is_allowed_env_var("HOUDINI_PATH"))
        self.assertTrue(is_allowed_env_var("HOUDINI_CGRU_PATH"))
        self.assertTrue(is_allowed_env_var("CGRU_LOCATION"))
        self.assertTrue(is_allowed_env_var("RP_PROJECT"))
        self.assertTrue(is_allowed_env_var("PUB_VERSION"))
        self.assertTrue(is_allowed_env_var("JOB_ROOT"))
        self.assertTrue(is_allowed_env_var("AXIOM_PATH"))
        self.assertTrue(is_allowed_env_var("REZ_USED_REQUEST"))
        self.assertFalse(is_allowed_env_var("PASSWORD"))
        self.assertFalse(is_allowed_env_var("SECRET_KEY"))
        self.assertFalse(is_allowed_env_var("FOO_VAR"))
        self.assertFalse(is_allowed_env_var("USER"))

    def test_submit_job_injects_environment_variables(self):
        hou_module = FakeHou()
        hou_module.hipFile = FakeHipFileWithSave()
        test_env = {
            "HOUDINI_PATH": "D:/custom/path",
            "CGRU_PYTHON": "python",
            "RP_SHOT": "sh01",
            "PUB_ASSET": "hero",
            "JOB_NAME": "proj_a",
            "AXIOM_DIR": "C:/axiom",
            "REZ_ENV": "1",
            "UNAPPROVED_SECRET": "should_not_pass",
        }
        with mock.patch.dict(os.environ, test_env, clear=True):
            submit_job(
                make_settings(),
                hou_module,
                FakeAf,
                is_file=lambda _: True,
            )
        block = FakeAf.last_job.blocks[0]
        self.assertEqual(block.env.get("HOUDINI_PATH"), "D:/custom/path")
        self.assertEqual(block.env.get("CGRU_PYTHON"), "python")
        self.assertEqual(block.env.get("RP_SHOT"), "sh01")
        self.assertEqual(block.env.get("PUB_ASSET"), "hero")
        self.assertEqual(block.env.get("JOB_NAME"), "proj_a")
        self.assertEqual(block.env.get("AXIOM_DIR"), "C:/axiom")
        self.assertEqual(block.env.get("REZ_ENV"), "1")
        self.assertNotIn("UNAPPROVED_SECRET", block.env)

    def test_submit_job_graceful_when_block_lacks_setenv(self):
        class BlockWithoutSetEnv:
            def __init__(self, name, service):
                self.name = name
                self.service = service

            def setCommand(self, command):
                self.command = command

            def setNumeric(self, start, end, per_task, step):
                self.numeric = (start, end, per_task, step)

            def setCapacity(self, capacity):
                self.capacity = capacity

        class AfWithoutSetEnv(FakeAf):
            Block = BlockWithoutSetEnv

        hou_module = FakeHou()
        hou_module.hipFile = FakeHipFileWithSave()
        status, _ = submit_job(
            make_settings(),
            hou_module,
            AfWithoutSetEnv,
            is_file=lambda _: True,
        )
        self.assertTrue(status)

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

    def setProperty(self, name, value):
        setattr(self, f"prop_{name}", value)

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

    def resize(self, width, height):
        self.size = (width, height)


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


class FakeCheckBox:
    def __init__(self, text):
        self.checked = False

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = checked


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
    QCheckBox = FakeCheckBox
    QDialog = FakeDialog
    QLineEdit = FakeLineEdit
    QSpinBox = FakeSpinBox
    QPushButton = FakePushButton
    QWidget = FakeDialog
    QHBoxLayout = FakeLayout
    QFormLayout = FakeLayout
    QFileDialog = FakeFileDialog


class FakeUi:
    def __init__(self):
        self.selected_node = "/out/farm_rop"
        self.messages = []
        self.confirmation_result = 0
        self.confirmations = []

    def selectNode(self, **kwargs):
        self.select_node_kwargs = kwargs
        return self.selected_node

    def displayMessage(self, message, severity=None, **kwargs):
        self.messages.append((message, severity))
        if "buttons" in kwargs:
            self.confirmations.append((message, kwargs))
            return self.confirmation_result


class SubmitterDialogTests(unittest.TestCase):
    def test_selected_rop_is_resolved_at_submission(self):
        dialog = _create_dialog_class(FakeQtWidgets, self.hou_module)()
        self.assertFalse(dialog.use_selected_rop.isChecked())
        dialog.use_selected_rop.setChecked(True)
        dialog.hython_edit.setText(sys.executable)
        dialog.rop_edit.setText("/out/old_rop")
        selected = FakeRop()
        self.hou_module.selectedNodes = lambda: (selected,)
        FakeAf.send_result = (True, {"id": 42})
        with mock.patch.dict(sys.modules, {"af": FakeAf}):
            dialog._on_submit()
        self.assertTrue(self.hou_module.hipFile.saved)
        self.assertIn(encode_text(selected.path()), FakeAf.last_job.blocks[0].command)

    def test_invalid_selection_aborts_before_confirmation(self):
        impostor = types.SimpleNamespace(render=lambda **kwargs: None)
        for selection in ((), (FakeRop(), FakeRop()), (impostor,)):
            with self.subTest(selection=selection):
                dialog = _create_dialog_class(FakeQtWidgets, self.hou_module)()
                dialog.use_selected_rop.setChecked(True)
                dialog.hython_edit.setText(sys.executable)
                self.hou_module.selectedNodes = lambda: selection
                with mock.patch.dict(sys.modules, {"af": FakeAf}), mock.patch.object(
                    FakeAf, "Job"
                ) as create_job:
                    dialog._on_submit()
                create_job.assert_not_called()
                self.assertFalse(self.hou_module.hipFile.saved)
                self.assertFalse(self.hou_module.ui.confirmations)
                self.assertEqual(self.hou_module.ui.messages[-1][1], "error")
                self.assertTrue(dialog.submit_button.enabled)

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
            "Qt", (), {"mainWindow": staticmethod(lambda: FakeQtWidgets.QWidget())}
        )()

    def test_dialog_defaults_and_rop_selector(self):
        parent_widget = FakeQtWidgets.QWidget()
        dialog_class = _create_dialog_class(FakeQtWidgets, self.hou_module)
        dialog = dialog_class(parent=parent_widget)
        self.assertTrue(getattr(dialog, "prop_houdiniStyle", False))
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
        self.assertEqual(len(self.hou_module.ui.confirmations), 1)
        self.assertEqual(
            self.hou_module.ui.messages[-1],
            ("Afanasy job submitted: 場景 test", None),
        )

    def test_cancel_aborts_before_save_and_job_creation(self):
        dialog = _create_dialog_class(FakeQtWidgets, self.hou_module)()
        dialog.hython_edit.setText(sys.executable)
        dialog.rop_edit.setText("/out/farm_rop")
        self.hou_module.ui.confirmation_result = 1
        with mock.patch.dict(sys.modules, {"af": FakeAf}), mock.patch.object(
            FakeAf, "Job"
        ) as create_job:
            dialog._on_submit()
        self.assertFalse(self.hou_module.hipFile.saved)
        create_job.assert_not_called()
        self.assertTrue(dialog.submit_button.enabled)
        message, options = self.hou_module.ui.confirmations[0]
        self.assertIn(self.hou_module.hipFile.path(), message)
        self.assertEqual(options["buttons"], ("OK", "Cancel"))
        self.assertEqual(options["close_choice"], 1)

    def test_show_raises_existing_dialog(self):
        self.hou_module.hipFile = FakeHipFile(path="D:/show/shot010.hip")
        pyside = types.ModuleType("PySide6")
        pyside.QtWidgets = FakeQtWidgets

        import chd_toolkits.afanasy_submitter as submitter

        submitter._dialog = None
        with mock.patch.dict(
            sys.modules,
            {
                "hou": self.hou_module,
                "hutil": None,
                "hutil.Qt": None,
                "PySide2": None,
                "PySide6": pyside,
            },
        ):
            first = show()
            second = show()

        self.assertIs(first, second)
        self.assertIs(second, submitter._dialog)
        self.assertIsNone(second.parent)
        self.assertTrue(second.visible)
        self.assertTrue(second.raised)

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


class QtResolutionTests(unittest.TestCase):
    def test_prefers_hutil_qt(self):
        hutil_mod = types.ModuleType("hutil")
        qt_mod = types.ModuleType("hutil.Qt")
        qt_mod.QtWidgets = "hutil-widgets"
        hutil_mod.Qt = qt_mod

        pyside2 = types.ModuleType("PySide2")
        pyside2.QtWidgets = "pyside2-widgets"
        pyside6 = types.ModuleType("PySide6")
        pyside6.QtWidgets = "pyside6-widgets"

        with mock.patch.dict(
            sys.modules,
            {
                "hutil": hutil_mod,
                "hutil.Qt": qt_mod,
                "PySide2": pyside2,
                "PySide6": pyside6,
            },
        ):
            self.assertEqual(_get_qt_widgets(), "hutil-widgets")

    def test_falls_back_to_pyside2(self):
        pyside2 = types.ModuleType("PySide2")
        pyside2.QtWidgets = "pyside2-widgets"
        pyside6 = types.ModuleType("PySide6")
        pyside6.QtWidgets = "pyside6-widgets"

        with mock.patch.dict(
            sys.modules,
            {
                "hutil": None,
                "hutil.Qt": None,
                "PySide2": pyside2,
                "PySide6": pyside6,
            },
        ):
            self.assertEqual(_get_qt_widgets(), "pyside2-widgets")

    def test_falls_back_to_pyside6(self):
        pyside6 = types.ModuleType("PySide6")
        pyside6.QtWidgets = "pyside6-widgets"

        with mock.patch.dict(
            sys.modules,
            {
                "hutil": None,
                "hutil.Qt": None,
                "PySide2": None,
                "PySide6": pyside6,
            },
        ):
            self.assertEqual(_get_qt_widgets(), "pyside6-widgets")

    def test_raises_import_error_when_all_missing(self):
        with mock.patch.dict(
            sys.modules,
            {
                "hutil": None,
                "hutil.Qt": None,
                "PySide2": None,
                "PySide6": None,
            },
        ):
            with self.assertRaises(ImportError):
                _get_qt_widgets()


if __name__ == "__main__":
    unittest.main()
