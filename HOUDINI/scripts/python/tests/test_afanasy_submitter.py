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
    USDRENDER_ROP_DEFAULT_SAVE_DIRECTORY,
    _create_dialog_class,
    _get_qt_widgets,
    build_render_command,
    configure_usdrender_rop_settings,
    decode_text,
    encode_text,
    is_allowed_env_var,
    resolve_rop_node,
    session_defaults,
    show,
    submit_job,
    validate_settings,
    validate_usdrender_rop_settings,
)


class FakeNodeType:
    def __init__(self, name):
        self._name = name

    def name(self):
        return self._name


class FakeParmTemplate:
    def __init__(self, menu_items=()):
        self._menu_items = menu_items

    def menuItems(self):
        return self._menu_items


class FakeParm:
    def __init__(self, value, menu_items=()):
        self._value = value
        self._menu_items = menu_items

    def unexpandedString(self):
        return self._value

    def eval(self):
        return self._value

    def set(self, value):
        self._value = value

    def parmTemplate(self):
        return FakeParmTemplate(self._menu_items)


class FakeRop:
    def path(self):
        return "/out/selected_rop"

    def name(self):
        return "輸出"

    def render(self, frame_range):
        pass

    def type(self):
        return FakeNodeType("geometry")

    def parm(self, name):
        return None


class FakeUsdRenderRop(FakeRop):
    def __init__(
        self,
        save_directory=USDRENDER_ROP_DEFAULT_SAVE_DIRECTORY,
        processor_enabled=True,
    ):
        self._parms = {
            "savetodirectory_directory": FakeParm(save_directory),
            "enableoutputprocessor_savetodirectory": FakeParm(processor_enabled),
            "deletefiles": FakeParm(
                "intempdir", menu_items=("intempdir", "always", "never")
            ),
        }

    def type(self):
        return FakeNodeType("usdrender_rop")

    def parm(self, name):
        return self._parms.get(name)


class FakeFileCache:
    """A non-ROP node (e.g. a File Cache SOP) whose actual writing-to-disk
    work happens via an internal child node literally named "render"
    (confirmed via hython against a real filecache::2.0 node: it has a
    child named "render" of type rop_geometry).
    """

    def __init__(self, rop=None):
        self._rop = rop if rop is not None else FakeRop()

    def path(self):
        return "/obj/geo1/filecache1"

    def node(self, relative_path):
        return self._rop if relative_path == "render" else None


class FakeVellumIO:
    """A non-ROP node (Vellum I/O) that embeds a File Cache internally, so
    its writing-to-disk ROP is nested one level deeper than File Cache's own
    (confirmed via hython against a real vellumio::2.0 node: it has a child
    "filecache" whose own child "render" is the rop_geometry).
    """

    def __init__(self, rop=None):
        self._rop = rop if rop is not None else FakeRop()

    def path(self):
        return "/obj/geo1/vellumio1"

    def node(self, relative_path):
        return self._rop if relative_path == "filecache/render" else None


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
        self.assertFalse(settings.is_simulation)

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

    def test_validate_settings_accepts_filecache_via_render_node(self):
        underlying_rop = FakeRop()
        resolved = validate_settings(
            make_settings(),
            FakeHou(node=FakeFileCache(underlying_rop)),
            is_file=lambda _: True,
        )
        self.assertIs(resolved, underlying_rop)

    def test_validate_settings_accepts_vellumio_via_nested_render_node(self):
        underlying_rop = FakeRop()
        resolved = validate_settings(
            make_settings(),
            FakeHou(node=FakeVellumIO(underlying_rop)),
            is_file=lambda _: True,
        )
        self.assertIs(resolved, underlying_rop)

    def test_validate_usdrender_rop_settings_rejects_default_directory(self):
        with self.assertRaisesRegex(ValueError, "default"):
            validate_usdrender_rop_settings(FakeUsdRenderRop())

    def test_validate_usdrender_rop_settings_rejects_directory_not_under_hip(self):
        with self.assertRaisesRegex(ValueError, r"\$HIP"):
            validate_usdrender_rop_settings(
                FakeUsdRenderRop(save_directory="$HOUDINI_TEMP_DIR/custom_renders")
            )

    def test_validate_usdrender_rop_settings_accepts_directory_under_hip(self):
        validate_usdrender_rop_settings(
            FakeUsdRenderRop(save_directory="$HIP/render/$RENDERID")
        )

    def test_validate_usdrender_rop_settings_skips_check_when_processor_disabled(self):
        validate_usdrender_rop_settings(FakeUsdRenderRop(processor_enabled=False))

    def test_validate_usdrender_rop_settings_ignores_other_rop_types(self):
        validate_usdrender_rop_settings(FakeRop())

    def test_configure_usdrender_rop_settings_sets_always_delete(self):
        rop = FakeUsdRenderRop()
        self.assertEqual(rop.parm("deletefiles").eval(), "intempdir")
        configure_usdrender_rop_settings(rop)
        self.assertEqual(rop.parm("deletefiles").eval(), "always")

    def test_configure_usdrender_rop_settings_ignores_other_rop_types(self):
        rop = FakeRop()
        configure_usdrender_rop_settings(rop)  # must not raise

    def test_validate_settings_rejects_usdrender_rop_at_default_directory(self):
        with self.assertRaisesRegex(ValueError, "default"):
            validate_settings(
                make_settings(),
                FakeHou(node=FakeUsdRenderRop()),
                is_file=lambda _: True,
            )

    def test_resolve_rop_node_returns_rop_as_is(self):
        rop = FakeRop()
        self.assertIs(resolve_rop_node(rop, FakeHou()), rop)

    def test_resolve_rop_node_resolves_filecache_via_render_node(self):
        underlying_rop = FakeRop()
        resolved = resolve_rop_node(FakeFileCache(underlying_rop), FakeHou())
        self.assertIs(resolved, underlying_rop)

    def test_resolve_rop_node_resolves_vellumio_via_nested_render_node(self):
        underlying_rop = FakeRop()
        resolved = resolve_rop_node(FakeVellumIO(underlying_rop), FakeHou())
        self.assertIs(resolved, underlying_rop)

    def test_resolve_rop_node_rejects_node_without_render_node(self):
        impostor = types.SimpleNamespace(render=lambda **kwargs: None)
        with self.assertRaisesRegex(ValueError, "ROP"):
            resolve_rop_node(impostor, FakeHou())

    def test_resolve_rop_node_rejects_render_node_that_is_not_a_rop(self):
        broken_filecache = FakeFileCache(rop=types.SimpleNamespace())
        with self.assertRaisesRegex(ValueError, "ROP"):
            resolve_rop_node(broken_filecache, FakeHou())

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
        command = build_render_command(settings, "D:/show/場景 test.hip", platform_name="posix")
        self.assertTrue(
            command.startswith(
                f'"{os.path.normpath("C:/Program Files/SideFX/Houdini/bin/hython.exe")}" -c '
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

    def test_build_render_command_windows_quoting(self):
        settings = make_settings(
            hython_path=r"C:\Program Files\Side Effects Software\Houdini 20.5.278\bin\hython.exe",
            frame_step=1,
        )
        command_win = build_render_command(settings, "D:/show/test.hip", platform_name="nt")
        self.assertTrue(command_win.startswith('""'))
        self.assertTrue(command_win.endswith('""'))
        inner_cmd = command_win[1:-1]
        self.assertTrue(
            inner_cmd.startswith(
                r'"C:\Program Files\Side Effects Software\Houdini 20.5.278\bin\hython.exe" -c "'
            )
        )

        command_posix = build_render_command(settings, "D:/show/test.hip", platform_name="posix")
        self.assertFalse(command_posix.startswith('""'))
        self.assertTrue(
            command_posix.startswith(
                r'"C:\Program Files\Side Effects Software\Houdini 20.5.278\bin\hython.exe" -c "'
            )
        )


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
        self.assertEqual(job.name, "render - /out/selected_rop")
        self.assertEqual(job.priority, 80)
        self.assertEqual(len(job.blocks), 1)
        block = job.blocks[0]
        self.assertEqual(block.name, "輸出")
        self.assertEqual(block.service, "hbatch")
        self.assertEqual(block.numeric, (1, 12, 4, 1))
        self.assertEqual(block.capacity, 800)

    def test_submit_job_simulation_forces_single_task_over_full_range(self):
        hou_module = FakeHou()
        hou_module.hipFile = FakeHipFileWithSave()
        FakeAf.send_result = (True, {"id": 42})
        submit_job(
            make_settings(frame_start=1, frame_end=100, frames_per_task=4, is_simulation=True),
            hou_module,
            FakeAf,
            is_file=lambda _: True,
        )
        block = FakeAf.last_job.blocks[0]
        # frames_per_task (4th element) covers the whole range in one task,
        # regardless of the frames_per_task the user left configured.
        self.assertEqual(block.numeric, (1, 100, 100, 1))

    def test_submit_job_sets_usdrender_rop_delete_files_before_save(self):
        events = []

        class OrderedParm(FakeParm):
            def set(self, value):
                events.append(("set_deletefiles", value))
                super().set(value)

        rop = FakeUsdRenderRop(save_directory="$HIP/render")
        rop._parms["deletefiles"] = OrderedParm(
            "intempdir", menu_items=("intempdir", "always", "never")
        )

        class OrderedHipFile(FakeHipFileWithSave):
            def save(self):
                events.append(("save",))
                super().save()

        hou_module = FakeHou(node=rop)
        hou_module.hipFile = OrderedHipFile()
        FakeAf.send_result = (True, {"id": 1})

        submit_job(make_settings(), hou_module, FakeAf, is_file=lambda _: True)

        self.assertEqual(events, [("set_deletefiles", "always"), ("save",)])

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
        self.assertFalse(is_allowed_env_var("REZ_AUTH_TOKEN"))
        self.assertFalse(is_allowed_env_var("JOB_PASSWORD"))
        self.assertFalse(is_allowed_env_var("JOB_PWD"))
        self.assertFalse(is_allowed_env_var("REZ_PASS"))
        self.assertFalse(is_allowed_env_var("RP_SECRET_KEY"))
        self.assertFalse(is_allowed_env_var("PUB_CREDENTIALS"))

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
            "REZ_AUTH_TOKEN": "secret_token",
            "JOB_PASSWORD": "secret_pass",
            "JOB_PWD": "secret_pwd",
            "REZ_PASS": "secret_pass2",
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
        self.assertNotIn("REZ_AUTH_TOKEN", block.env)
        self.assertNotIn("JOB_PASSWORD", block.env)
        self.assertNotIn("JOB_PWD", block.env)
        self.assertNotIn("REZ_PASS", block.env)

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
            os.path.normpath(
                os.path.join(
                    "C:/Program Files/SideFX/Houdini", "bin", "hython.exe"
                )
            ),
        )
        self.assertEqual(defaults["frame_start"], 1001)
        self.assertEqual(defaults["frame_end"], 1100)
        self.assertEqual(defaults["priority"], 80)
        self.assertEqual(defaults["capacity"], 800)

    def test_session_defaults_resolves_8_3_short_path(self):
        hou_module = FakeHou(path="D:/show/shot010.hip")
        hou_module.playbar = type(
            "Playbar",
            (),
            {"playbackRange": staticmethod(lambda: (1001.0, 1100.0))},
        )()
        # Test on Windows: C:\PROGRA~1 resolves to C:\Program Files if present
        if os.name == "nt" and os.path.exists("C:/PROGRA~1"):
            hou_module.getenv = lambda name: "C:/PROGRA~1/SideFX/Houdini"
            defaults = session_defaults(hou_module, platform_name="nt")
            self.assertTrue(defaults["hython_path"].startswith("C:\\Program Files"))
            self.assertNotIn("~", defaults["hython_path"])
        else:
            hou_module.getenv = lambda name: "/opt/hfs"
            defaults = session_defaults(hou_module, platform_name="posix")
            self.assertEqual(defaults["hython_path"], "/opt/hfs/bin/hython")


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
        self.enabled = True

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text

    def setReadOnly(self, value):
        self.read_only = value

    def setEnabled(self, value):
        self.enabled = value


class FakeSpinBox:
    def __init__(self):
        self.enabled = True

    def setRange(self, minimum, maximum):
        self.value_range = (minimum, maximum)

    def setValue(self, value):
        self._value = value

    def value(self):
        return self._value

    def setEnabled(self, value):
        self.enabled = value


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
        self.toggled = FakeSignal()

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = checked
        callback = getattr(self.toggled, "callback", None)
        if callback:
            callback(checked)


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

    def test_selected_filecache_resolved_to_its_render_node_at_submission(self):
        underlying_rop = FakeRop()
        dialog = _create_dialog_class(FakeQtWidgets, self.hou_module)()
        dialog.use_selected_rop.setChecked(True)
        dialog.hython_edit.setText(sys.executable)
        self.hou_module.selectedNodes = lambda: (FakeFileCache(underlying_rop),)
        FakeAf.send_result = (True, {"id": 42})
        with mock.patch.dict(sys.modules, {"af": FakeAf}):
            dialog._on_submit()
        self.assertTrue(self.hou_module.hipFile.saved)
        self.assertIn(
            encode_text(underlying_rop.path()), FakeAf.last_job.blocks[0].command
        )
        self.assertEqual(FakeAf.last_job.blocks[0].name, underlying_rop.name())
        self.assertTrue(FakeAf.last_job.name.endswith(f" - {underlying_rop.path()}"))

    def test_selected_vellumio_resolved_to_its_nested_render_node_at_submission(self):
        underlying_rop = FakeRop()
        dialog = _create_dialog_class(FakeQtWidgets, self.hou_module)()
        dialog.use_selected_rop.setChecked(True)
        dialog.hython_edit.setText(sys.executable)
        self.hou_module.selectedNodes = lambda: (FakeVellumIO(underlying_rop),)
        FakeAf.send_result = (True, {"id": 42})
        with mock.patch.dict(sys.modules, {"af": FakeAf}):
            dialog._on_submit()
        self.assertTrue(self.hou_module.hipFile.saved)
        self.assertIn(
            encode_text(underlying_rop.path()), FakeAf.last_job.blocks[0].command
        )
        self.assertEqual(FakeAf.last_job.blocks[0].name, underlying_rop.name())

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

    def test_simulation_toggle_disables_frames_per_task(self):
        dialog = _create_dialog_class(FakeQtWidgets, self.hou_module)()
        self.assertTrue(dialog.frames_per_task_spin.enabled)

        dialog.simulation_checkbox.setChecked(True)
        self.assertFalse(dialog.frames_per_task_spin.enabled)

        dialog.simulation_checkbox.setChecked(False)
        self.assertTrue(dialog.frames_per_task_spin.enabled)

    def test_use_selected_rop_toggle_disables_rop_node_field(self):
        dialog = _create_dialog_class(FakeQtWidgets, self.hou_module)()
        self.assertTrue(dialog.rop_edit.enabled)
        self.assertTrue(dialog.rop_button.enabled)

        dialog.use_selected_rop.setChecked(True)
        self.assertFalse(dialog.rop_edit.enabled)
        self.assertFalse(dialog.rop_button.enabled)

        dialog.use_selected_rop.setChecked(False)
        self.assertTrue(dialog.rop_edit.enabled)
        self.assertTrue(dialog.rop_button.enabled)

    def test_settings_from_fields_carries_simulation_flag(self):
        dialog = _create_dialog_class(FakeQtWidgets, self.hou_module)()
        dialog.rop_edit.setText("/out/farm_rop")
        dialog.simulation_checkbox.setChecked(True)
        settings = dialog._settings_from_fields()
        self.assertTrue(settings.is_simulation)

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
