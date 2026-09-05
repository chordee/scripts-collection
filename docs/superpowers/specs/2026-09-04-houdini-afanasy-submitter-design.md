# Houdini Afanasy submitter design

## Purpose

Add a small PySide6 panel that runs inside Houdini and submits the current HIP
file to Afanasy through its Python `af` module. Each farm task launches the
configured `hython` executable, loads the saved HIP file, finds the selected
ROP node, and calls `render()` for that task's frame chunk.

The render command must be self-contained. Render hosts are not assumed to
have this repository's `chd_toolkits` package, and submission must not create
or depend on a shared temporary Python script.

## Scope decisions

- Add one Houdini-only module:
  `HOUDINI/scripts/python/chd_toolkits/afanasy_submitter.py`.
- Launch it with:

  ```python
  from chd_toolkits import afanasy_submitter
  afanasy_submitter.show()
  ```

- The submitter imports `af` inside Houdini and constructs one `af.Job` with
  one numeric `af.Block`.
- The block service is `hbatch`, while its executable command is the
  user-configurable `hython` path.
- The task command uses `hython -c`; it does not import `chd_toolkits` on the
  render host.
- The panel asks for confirmation before saving the current HIP and sending
  the job. OK proceeds; Cancel or closing the confirmation aborts submission.
- An unnamed `untitled.hip` is rejected so the tool does not choose a save
  location on the user's behalf.
- No Shelf Tool definition is added in this change.

## Panel

The panel is parented to `hou.qt.mainWindow()`. A module-level reference keeps
the window alive, and `show()` closes any previous instance before showing a
new one.

Fields:

- **Job Name**: defaults to the current HIP filename without its extension.
- **Hython**: defaults to `$HFS/bin/hython.exe` on Windows (`hython` on other
  platforms), remains editable, and has a file browser button.
- **ROP Node**: a read-only path field populated through Houdini's node
  selector, restricted to ROP nodes.
- **Use Selected ROP**: unchecked by default. When checked, Submit resolves
  the current Houdini selection instead of the path field. Exactly one node
  must be selected, and it must satisfy `isinstance(node, hou.RopNode)`;
  otherwise submission stops before the save confirmation. The same type
  check also validates nodes supplied by the browser.
- **Frame Start / End / Step**: start and end default to the current playback
  range; step defaults to `1`.
- **Frames per task**: defaults to `1`.
- **Capacity**: defaults to `800`.
- **Job Priority**: defaults to `80`.
- **Submit** button.

Integer widgets prevent non-numeric values. Frame step, frames per task, and
capacity must be positive. Start must not be greater than end.

## Command construction

The HIP path and ROP path are encoded with UTF-8 and URL-safe Base64 before
being embedded into the inline Python program. The worker decodes them before
use. This avoids shell quoting problems with spaces, non-ASCII characters,
quotes, and Windows path separators. Base64 is transport encoding, not a
security mechanism.

Conceptually, the block command is:

```text
"<hython>" -c "import base64,hou; ...; node.render(frame_range=(@#@,@#@,<step>))"
```

The inline program:

1. Decodes the HIP and ROP paths.
2. Loads the HIP with `hou.hipFile.load()`.
3. Resolves the ROP with `hou.node()`.
4. Raises an error if the node does not exist or has no callable `render`.
5. Calls `render(frame_range=(task_start, task_end, frame_step))`.

Exceptions are not swallowed, so `hython` exits unsuccessfully and Afanasy
can mark the task as errored. The two `@#@` tokens are retained for Afanasy to
replace with each numeric task's start and end frames. The configured frame
step is embedded as the third `frame_range` value so the ROP and numeric block
use the same increment.

## Submission flow

On Submit:

1. Validate the job name, hython executable, selected ROP, frame values,
   capacity, and priority.
2. Reject an unnamed HIP file.
3. Show a Save and Submit dialog with the current HIP path and OK/Cancel
   buttons. Cancel (also the default and close action) stops without saving
   or sending. On OK, save the current scene with `hou.hipFile.save()`.
4. Build the self-contained command.
5. Construct the Afanasy objects:

   ```python
   job = af.Job(job_name)
   job.setPriority(priority)
   block = af.Block(rop_name, "hbatch")
   block.setCommand(command)
   block.setNumeric(start, end, frames_per_task, step)
   block.setCapacity(capacity)
   job.blocks.append(block)
   status, data = job.send()
   ```

6. Show a Houdini message for either successful submission or the returned
   failure details.

The Submit button is disabled for the duration of the synchronous submission
and restored in a `finally` path to prevent accidental duplicate sends.
Validation, save, import, and send exceptions are displayed without sending a
partial second job.

## Testing and verification

- Add focused tests for URL-safe Base64 round-tripping and generated command
  content, including spaces, Unicode, quotes, and Windows separators.
- Test that numeric frame settings, service, capacity, priority, and command
  are passed to fake `af.Job` and `af.Block` objects correctly.
- Test validation failures, HIP save failure, and `job.send()` failure without
  contacting an Afanasy server.
- Run the new targeted tests and the existing Houdini test suite through the
  repository's confirmed `tests/run_hython.py` wrapper.
- Run `git diff --check` on the changed files.

These checks validate Python behavior and Afanasy object construction only.
A real Houdini UI launch, Afanasy server submission, render-host path access,
ROP execution, renderer licensing, and produced frames require a separate
smoke test in the user's Houdini/farm environment.

## Out of scope

- Shipping repository modules or temporary scripts to render hosts.
- Adding a Shelf Tool, output preview pattern, parser, host masks,
  dependencies, maximum concurrent tasks, or renderer-specific services.
- Mapping local paths to different render-host paths.
- Automatically choosing a filename for an unsaved HIP.
