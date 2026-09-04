"""Tests for the Houdini Afanasy submitter."""

import os
import sys
import unittest


PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, PACKAGE_PARENT)

from chd_toolkits.afanasy_submitter import (  # noqa: E402
    SubmissionSettings,
    build_render_command,
    decode_text,
    encode_text,
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


class SubmitterPureTests(unittest.TestCase):
    def make_settings(self, **changes):
        values = dict(
            job_name="render",
            hython_path="C:/Program Files/SideFX/Houdini/bin/hython.exe",
            rop_path="/out/輸出",
            frame_start=1,
            frame_end=12,
        )
        values.update(changes)
        return SubmissionSettings(**values)

    def test_defaults(self):
        settings = self.make_settings()
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
                self.make_settings(), FakeHou(is_new=True), is_file=lambda _: True
            )

    def test_validate_rejects_missing_rop(self):
        with self.assertRaisesRegex(ValueError, "ROP"):
            validate_settings(
                self.make_settings(), FakeHou(node=False), is_file=lambda _: True
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
                    self.make_settings(**changes), FakeHou(), is_file=lambda _: True
                )

    def test_command_is_self_contained_and_has_two_frame_tokens(self):
        settings = self.make_settings()
        command = build_render_command(settings, "D:/show/場景 test.hip")
        self.assertTrue(
            command.startswith(
                '"C:/Program Files/SideFX/Houdini/bin/hython.exe" -c '
            )
        )
        self.assertEqual(command.count("@#@"), 2)
        self.assertIn("urlsafe_b64decode", command)
        self.assertIn("hou.hipFile.load", command)
        self.assertIn("node.render(frame_range=(@#@,@#@))", command)
        self.assertNotIn("chd_toolkits", command)
        self.assertNotIn("場景", command)


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


class SubmitterJobTests(SubmitterPureTests):
    def test_submit_job_saves_and_sends_expected_objects(self):
        hou_module = FakeHou()
        hou_module.hipFile = FakeHipFileWithSave()
        FakeAf.send_result = (True, {"id": 42})
        status, data = submit_job(
            self.make_settings(frames_per_task=4),
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
                self.make_settings(frame_step=0),
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
            self.make_settings(), hou_module, FakeAf, is_file=lambda _: True
        )
        self.assertEqual(result, FakeAf.send_result)


if __name__ == "__main__":
    unittest.main()
