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


if __name__ == "__main__":
    unittest.main()
