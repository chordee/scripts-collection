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
    if node is None or not callable(getattr(node, "render", None)):
        raise ValueError("Select a valid ROP node with render().")
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
        "node.render(frame_range=(@#@,@#@))"
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
