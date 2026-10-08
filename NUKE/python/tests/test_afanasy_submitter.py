"""Tests for the Nuke Afanasy submitter.

The submission logic runs against fake ``nuke`` and ``af`` modules, so plain
Python is enough. The dialog tests need PySide6 and a QApplication and are
skipped otherwise; run them inside Nuke with ``Nuke --tg run_tests.py``.
"""

import os
import sys
import unittest
from unittest import mock

PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)

from chd_nuke.afanasy_submitter import (  # noqa: E402
    SubmissionSettings,
    _create_dialog_class,
    build_render_command,
    default_write_names,
    expand_short_paths,
    farm_environment,
    is_allowed_env_var,
    list_write_nodes,
    session_defaults,
    submit_job,
    validate_settings,
    write_frame_range,
)


class FakeKnob:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class FakeNode:
    def __init__(self, full_name, cls="Write", selected=False, disabled=False,
                 limit=None):
        self._full_name = full_name
        self._cls = cls
        self._selected = selected
        self._knobs = {"disable": FakeKnob(disabled)}
        if cls == "Write":
            self._knobs["use_limit"] = FakeKnob(limit is not None)
            first, last = limit or (1, 1)
            self._knobs["first"] = FakeKnob(first)
            self._knobs["last"] = FakeKnob(last)

    def fullName(self):
        return self._full_name

    def Class(self):
        return self._cls

    def isSelected(self):
        return self._selected

    def knobs(self):
        return self._knobs

    def __getitem__(self, name):
        return self._knobs[name]


class FakeRoot:
    def __init__(self, name, first=1, last=100):
        self._name = name
        self._knobs = {"first_frame": FakeKnob(first), "last_frame": FakeKnob(last)}

    def name(self):
        return self._name

    def __getitem__(self, name):
        return self._knobs[name]


class FakeNuke:
    EXE_PATH = "D:/Programs/Nuke17.0v1/Nuke17.0.exe"

    def __init__(self, nodes=(), script="D:/shots/sh010/comp_v001.nk", nukex=False,
                 first=1, last=100):
        self._nodes = list(nodes)
        self._root = FakeRoot(script, first, last)
        self.env = {"nukex": nukex}
        self.saved = 0
        self.ask_answer = True
        self.messages = []

    def allNodes(self, filter=None, recurseGroups=False):
        # Mirrors Nuke 17: a class filter stops recursion into groups.
        if filter is not None:
            return [n for n in self._nodes if n.Class() == filter and "." not in n.fullName()]
        if recurseGroups:
            return list(self._nodes)
        return [n for n in self._nodes if "." not in n.fullName()]

    def toNode(self, name):
        return next((n for n in self._nodes if n.fullName() == name), None)

    def root(self):
        return self._root

    def scriptSave(self):
        self.saved += 1

    def ask(self, _text):
        return self.ask_answer

    def message(self, text):
        self.messages.append(text)


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
    send_result = (True, {"id": 7})
    Block = FakeBlock

    @classmethod
    def Job(cls, name):
        cls.last_job = FakeJob(name, cls.send_result)
        return cls.last_job


def make_settings(**overrides):
    values = dict(
        job_name="comp_v001",
        nuke_path="D:/Programs/Nuke17.0v1/Nuke17.0.exe",
        write_names=("Write1",),
        frame_start=1,
        frame_end=100,
    )
    values.update(overrides)
    return SubmissionSettings(**values)


def make_nuke():
    return FakeNuke([
        FakeNode("Write1", selected=False),
        FakeNode("Write2", disabled=True),
        FakeNode("Group1.WriteFG", limit=(10, 20)),
        FakeNode("Blur1", cls="Blur"),
    ])


class EnvironmentTests(unittest.TestCase):
    def test_allowed_names_and_prefixes(self):
        for name in ("NUKE_PATH", "nuke_path", "PYTHONPATH", "OFX_PLUGIN_PATH", "OCIO",
                     "CGRU_LOCATION", "JOB_ROOT", "REZ_USED"):
            self.assertTrue(is_allowed_env_var(name), name)

    def test_system_path_and_unrelated_vars_are_not_sent(self):
        for name in ("PATH", "Path", "HOME", "TEMP", "HOUDINI_PATH"):
            self.assertFalse(is_allowed_env_var(name), name)

    def test_variables_nuke_adds_to_its_own_process_are_not_sent(self):
        # Observed in a running Nuke 17.0v1 but absent from the shell it started from.
        for name in ("NUKE_R_2026_0218", "NUKE_TEMP_DIR", "FN_ENT_DISABLE_SYSTEM_LOCK"):
            self.assertFalse(is_allowed_env_var(name), name)

    def test_license_servers_are_left_to_the_farm(self):
        for name in ("foundry_LICENSE", "JOB_LICENSE_SERVER", "REZ_LICENSE"):
            self.assertFalse(is_allowed_env_var(name), name)

    def test_sensitive_names_are_never_sent(self):
        for name in ("JOB_API_KEY", "CGRU_TOKEN", "JOB_PASSWORD", "CGRU_SECRET",
                     "REZ_AUTH"):
            self.assertFalse(is_allowed_env_var(name), name)

    def test_path_lists_use_forward_slashes_on_windows(self):
        env = farm_environment(
            {"NUKE_PATH": "D:\\tools\\nuke;D:\\shared", "JOB_NAME": "a\\b"},
            platform_name="nt",
        )
        self.assertEqual(env["NUKE_PATH"], "D:/tools/nuke;D:/shared")
        self.assertEqual(env["JOB_NAME"], "a\\b")

    def test_farm_environment_filters(self):
        env = farm_environment({"PATH": "C:/x", "NUKE_PATH": "D:/t", "HOME": "C:/u"},
                               platform_name="posix")
        self.assertEqual(env, {"NUKE_PATH": "D:/t"})

    def test_expand_short_paths_is_noop_off_windows(self):
        self.assertEqual(expand_short_paths("C:/PROGRA~1", platform_name="posix"),
                         "C:/PROGRA~1")

    def test_expand_short_paths_keeps_missing_entries(self):
        self.assertEqual(
            expand_short_paths("Z:/NOPE~1/x;D:/plain", platform_name="nt"),
            "Z:/NOPE~1/x;D:/plain",
        )

    def test_expand_short_paths_resolves_real_short_path(self):
        if os.name != "nt":
            self.skipTest("8.3 short paths only exist on Windows")
        import ctypes
        long_path = os.path.dirname(os.path.abspath(__file__))
        buffer = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetShortPathNameW(long_path, buffer, 1024)
        if "~" not in buffer.value:
            self.skipTest("no 8.3 alias for this directory")
        self.assertEqual(os.path.normcase(expand_short_paths(buffer.value, "nt")),
                         os.path.normcase(long_path))


class WriteNodeTests(unittest.TestCase):
    def test_list_write_nodes_includes_writes_inside_groups(self):
        names = [n.fullName() for n in list_write_nodes(make_nuke())]
        self.assertEqual(names, ["Write1", "Write2", "Group1.WriteFG"])

    def test_default_is_selected_writes(self):
        nuke = FakeNuke([FakeNode("Write1"), FakeNode("Write2", selected=True)])
        self.assertEqual(default_write_names(nuke), ("Write2",))

    def test_default_without_selection_is_every_enabled_write(self):
        self.assertEqual(default_write_names(make_nuke()), ("Write1", "Group1.WriteFG"))

    def test_write_frame_range_uses_limit_when_enabled(self):
        self.assertEqual(write_frame_range(FakeNode("W", limit=(10, 20)), 1, 100), (10, 20))
        self.assertEqual(write_frame_range(FakeNode("W"), 1, 100), (1, 100))


class ValidationTests(unittest.TestCase):
    def assertInvalid(self, message, settings, nuke=None):
        with self.assertRaises(ValueError) as ctx:
            validate_settings(settings, nuke or make_nuke(), is_file=lambda _: True)
        self.assertIn(message, str(ctx.exception))

    def test_valid_settings_return_the_write_nodes(self):
        writes = validate_settings(make_settings(write_names=("Write1", "Group1.WriteFG")),
                                   make_nuke(), is_file=lambda _: True)
        self.assertEqual([w.fullName() for w in writes], ["Write1", "Group1.WriteFG"])

    def test_errors(self):
        self.assertInvalid("Job Name", make_settings(job_name="  "))
        self.assertInvalid("at least one Write", make_settings(write_names=()))
        self.assertInvalid("Frame Start", make_settings(frame_start=5, frame_end=1))
        self.assertInvalid("Frame Step", make_settings(frame_step=0))
        self.assertInvalid("Frames per task", make_settings(frames_per_task=0))
        self.assertInvalid("Capacity", make_settings(capacity=0))
        self.assertInvalid("Priority", make_settings(priority=-1))
        self.assertInvalid("not found", make_settings(write_names=("Nope",)))
        self.assertInvalid("not found", make_settings(write_names=("Blur1",)))
        self.assertInvalid("disabled", make_settings(write_names=("Write2",)))

    def test_missing_executable(self):
        with self.assertRaises(ValueError) as ctx:
            validate_settings(make_settings(), make_nuke(), is_file=lambda _: False)
        self.assertIn("executable", str(ctx.exception))

    def test_untitled_script(self):
        nuke = make_nuke()
        nuke._root = FakeRoot("Root")
        self.assertInvalid("Save the script", make_settings(), nuke)

    def test_empty_write_limit_range(self):
        nuke = FakeNuke([FakeNode("Write1", limit=(20, 10))])
        self.assertInvalid("range is empty", make_settings(), nuke)


class CommandTests(unittest.TestCase):
    def test_windows_command_is_wrapped_for_cmd_exe(self):
        command = build_render_command(
            make_settings(nuke_path="C:/Program Files/Nuke17.0v1/Nuke17.0.exe", frame_step=2),
            "D:/shots/sh 010/comp.nk", "Group1.WriteFG", platform_name="nt")
        self.assertTrue(command.startswith('""'))
        self.assertTrue(command.endswith('"'))
        inner = command[1:-1]
        exe = os.path.normpath("C:/Program Files/Nuke17.0v1/Nuke17.0.exe")
        script = os.path.normpath("D:/shots/sh 010/comp.nk")
        self.assertEqual(
            inner, f'"{exe}" -x -X Group1.WriteFG -F @#@-@#@x2 "{script}"')

    def test_nukex_flag(self):
        command = build_render_command(make_settings(use_nukex=True), "D:/a.nk", "Write1",
                                       platform_name="posix")
        self.assertIn(" -x --nukex -X Write1 ", command)
        self.assertFalse(command.startswith('"'))


class SubmitTests(unittest.TestCase):
    def setUp(self):
        FakeAf.send_result = (True, {"id": 7})

    def test_submit_builds_one_block_per_write(self):
        nuke = make_nuke()
        settings = make_settings(write_names=("Write1", "Group1.WriteFG"), frame_step=2,
                                 frames_per_task=5, capacity=500, priority=60)
        result = submit_job(settings, nuke, FakeAf, is_file=lambda _: True,
                            environ={"NUKE_PATH": "D:/t", "PATH": "C:/x"})

        self.assertEqual(result, (True, {"id": 7}))
        self.assertEqual(nuke.saved, 1)
        job = FakeAf.last_job
        self.assertEqual(job.name, "comp_v001")
        self.assertEqual(job.priority, 60)
        self.assertEqual([b.name for b in job.blocks], ["Write1", "Group1.WriteFG"])
        self.assertEqual({b.service for b in job.blocks}, {"nuke"})
        self.assertEqual(job.blocks[0].numeric, (1, 100, 5, 2))
        self.assertEqual(job.blocks[1].numeric, (10, 20, 5, 2))   # Write's own range
        self.assertEqual(job.blocks[1].capacity, 500)
        self.assertIn("-X Group1.WriteFG", job.blocks[1].command)
        self.assertEqual(job.blocks[0].env, {"NUKE_PATH": "D:/t"})

    def test_validation_failure_does_not_save(self):
        nuke = make_nuke()
        with self.assertRaises(ValueError):
            submit_job(make_settings(write_names=()), nuke, FakeAf, is_file=lambda _: True)
        self.assertEqual(nuke.saved, 0)

    def test_block_without_setenv(self):
        class NoEnvBlock(FakeBlock):
            setEnv = None

        class NoEnvAf(FakeAf):
            Block = NoEnvBlock

        submit_job(make_settings(), make_nuke(), NoEnvAf, is_file=lambda _: True,
                   environ={"NUKE_PATH": "D:/t"})
        self.assertEqual(NoEnvAf.last_job.blocks[0].env, {})


class SessionDefaultsTests(unittest.TestCase):
    def test_defaults_follow_the_running_nuke(self):
        nuke = FakeNuke([FakeNode("Write1")], nukex=True, first=1001, last=1100)
        defaults = session_defaults(nuke)
        self.assertEqual(defaults["job_name"], "comp_v001")
        self.assertEqual(defaults["nuke_path"], os.path.normpath(FakeNuke.EXE_PATH))
        self.assertTrue(defaults["use_nukex"])
        self.assertEqual(defaults["write_names"], ("Write1",))
        self.assertEqual((defaults["frame_start"], defaults["frame_end"]), (1001, 1100))


def _qt():
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        return None
    if QtWidgets.QApplication.instance() is None:
        return None
    return QtWidgets, QtCore


@unittest.skipIf(_qt() is None, "needs PySide6 and a running QApplication")
class DialogTests(unittest.TestCase):
    def make_dialog(self, nuke):
        QtWidgets, QtCore = _qt()
        return _create_dialog_class(QtWidgets, QtCore, nuke)()

    def test_write_list_checks_the_defaults(self):
        dialog = self.make_dialog(make_nuke())
        items = [dialog.write_list.item(i) for i in range(dialog.write_list.count())]
        self.assertEqual([i.text() for i in items],
                         ["Write1", "Write2  (disabled)", "Group1.WriteFG"])
        self.assertEqual(dialog._checked_write_names(), ("Write1", "Group1.WriteFG"))

    def test_settings_from_fields(self):
        _, QtCore = _qt()
        dialog = self.make_dialog(make_nuke())
        dialog.write_list.item(0).setCheckState(QtCore.Qt.CheckState.Unchecked)
        dialog.nukex_checkbox.setChecked(True)
        dialog.frame_step_spin.setValue(3)
        settings = dialog._settings_from_fields()
        self.assertEqual(settings.write_names, ("Group1.WriteFG",))
        self.assertTrue(settings.use_nukex)
        self.assertEqual(settings.frame_step, 3)

    def test_submit_reports_validation_errors(self):
        nuke = make_nuke()
        dialog = self.make_dialog(nuke)
        dialog.job_name_edit.setText("")
        with mock.patch.dict(sys.modules, {"af": FakeAf}):
            dialog._on_submit()
        self.assertTrue(any("Job Name" in m for m in nuke.messages))
        self.assertTrue(dialog.submit_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
