"""USD Value Clips stitcher.

Stitches a sequence of per-frame USD caches into a single stage that
references them via the Value Clips composition arc. Auto-generates a
``topology`` sublayer and a ``manifest`` asset alongside the output.

Entry point is :func:`stitch_clips`. Helper utilities (``resolve_filepath``,
``build_clip_frame_lists``, ``validate_files``, ``find_all_animated_prims``,
``generate_topology``, ``generate_manifest``) are also public so other
chd_toolkits modules / shelf scripts can compose them as needed.

Houdini is not required at runtime — only ``pxr`` (bundled with Houdini
or installable via ``pip install usd-core``).
"""

import os
import re

from pxr import Sdf, Usd


# ---------------------------------------------------------------------------
# Path token resolver
# ---------------------------------------------------------------------------
def resolve_filepath(template: str, frame: int) -> str:
    """
    Supports two frame token formats:
      - Python format:  /cache/sim.{frame:04d}.usd
      - Houdini $F/$F4: /cache/sim.$F4.usd  or  /cache/sim.$F.usd
    """
    # Houdini $F4 style → resolved integer string
    houdini_pattern = re.compile(r'\$F(\d*)')
    def replace_houdini(m):
        padding = int(m.group(1)) if m.group(1) else 1
        return f"{frame:0{padding}d}"
    resolved = houdini_pattern.sub(replace_houdini, template)

    # Python {frame:04d} style
    try:
        resolved = resolved.format(frame=frame)
    except KeyError:
        pass  # No {frame} token — skip

    return resolved


# ---------------------------------------------------------------------------
# Core stitcher
# ---------------------------------------------------------------------------
def build_clip_frame_lists(
    frame_range: tuple[int, int],
    scene_range: tuple[int, int],
    loop: bool,
) -> tuple[list[int], list[int]]:
    """
    Returns (scene_frame_list, file_frame_list) with equal length.
    When loop=True, the file list is repeated to cover the full scene range.
    """
    if frame_range[1] < frame_range[0]:
        raise ValueError(
            f"frame_range end ({frame_range[1]}) must be >= start ({frame_range[0]})"
        )
    if scene_range[1] < scene_range[0]:
        raise ValueError(
            f"scene_range end ({scene_range[1]}) must be >= start ({scene_range[0]})"
        )

    file_frames = list(range(frame_range[0], frame_range[1] + 1))
    scene_frames = list(range(scene_range[0], scene_range[1] + 1))

    if loop and len(file_frames) < len(scene_frames):
        mul = len(scene_frames) // len(file_frames) + 1
        file_frames = (file_frames * mul)

    # zip truncates to the shorter of the two lists
    paired = list(zip(scene_frames, file_frames))
    scene_out = [p[0] for p in paired]
    file_out  = [p[1] for p in paired]
    return scene_out, file_out


def validate_files(filepaths: list[str], strict: bool = False) -> list[str]:
    """Check whether each path exists.

    With ``strict=True`` raises :class:`FileNotFoundError` when any file is
    missing; otherwise prints a warning and returns the list of missing paths.
    """
    missing = [p for p in filepaths if not os.path.exists(p)]
    if missing:
        msg = f"[WARNING] The following {len(missing)} file(s) do not exist:\n"
        for p in missing[:10]:
            msg += f"    {p}\n"
        if len(missing) > 10:
            msg += f"    ... and {len(missing)-10} more\n"
        if strict:
            raise FileNotFoundError("Strict mode: aborting.\n" + msg)
        print(msg)
    return missing


# ---------------------------------------------------------------------------
# Auto-detect animated prims
# ---------------------------------------------------------------------------
def find_all_animated_prims(probe_frame_path: str, root_primpath: str) -> list[str]:
    """
    Starting from root_primpath in the probe frame, recursively traverses all
    child prims and collects paths of prims that have time-sampled attributes.

    Note: child prims are checked independently even when a parent already has
    animated attributes. Returns all animated prim paths found, or
    [root_primpath] if none are found.
    """
    src_stage = Usd.Stage.Open(probe_frame_path)
    root = src_stage.GetPrimAtPath(root_primpath)
    if not root.IsValid():
        print(f"[WARNING] auto-detect: root prim {root_primpath} not found — using original path.")
        return [root_primpath]

    animated_prims = []

    def walk(prim):
        animated_attrs = [a for a in prim.GetAttributes() if a.GetNumTimeSamples() > 0]
        if animated_attrs:
            path = str(prim.GetPath())
            animated_prims.append(path)
            print(f"[INFO] Animated prim detected: {path}  "
                  f"attrs: {[a.GetName() for a in animated_attrs[:5]]}"
                  f"{'...' if len(animated_attrs) > 5 else ''}")
        for child in prim.GetChildren():
            walk(child)

    walk(root)

    if not animated_prims:
        print(f"[WARNING] auto-detect: no animated attributes found under {root_primpath} — using original path.")
        return [root_primpath]

    print(f"[INFO] {len(animated_prims)} animated prim(s) detected.")
    return animated_prims


# ---------------------------------------------------------------------------
# Topology generator
# ---------------------------------------------------------------------------
def generate_topology(
    probe_frame_path: str,
    clip_primpath: str,
    topology_path: str,
) -> None:
    """
    Copies the prim hierarchy and attribute definitions from the specified
    frame's USD file, stripping all time samples to retain only static structure.
    """
    src_stage = Usd.Stage.Open(probe_frame_path)
    topo_stage = Usd.Stage.CreateNew(topology_path)

    src_root = src_stage.GetPrimAtPath(clip_primpath)
    if not src_root.IsValid():
        print(f"[WARNING] Topology: prim {clip_primpath} not found — skipping topology generation.")
        return

    # Recursively copy prim structure
    def copy_prim(src_prim, dst_stage, dst_parent_path):
        dst_path = dst_parent_path.AppendChild(src_prim.GetName())
        dst_prim = dst_stage.DefinePrim(dst_path, src_prim.GetTypeName())

        # Copy attribute definitions (no time samples)
        for attr in src_prim.GetAttributes():
            dst_attr = dst_prim.CreateAttribute(
                attr.GetName(),
                attr.GetTypeName(),
                custom=attr.IsCustom(),
            )
            # Copy only the default value (not time samples)
            default_val = attr.Get()
            if default_val is not None:
                dst_attr.Set(default_val)

        # Copy relationships
        for rel in src_prim.GetRelationships():
            dst_rel = dst_prim.CreateRelationship(rel.GetName(), custom=rel.IsCustom())
            targets = rel.GetTargets()
            if targets:
                dst_rel.SetTargets(targets)

        # Recurse into children
        for child in src_prim.GetChildren():
            copy_prim(child, dst_stage, dst_path)

    # Start at clip_primpath's parent so the copy lands at the same absolute
    # path as the source (e.g. /World/Sim), not collapsed to its leaf name
    # (/Sim) under the topology stage's root — the topology layer is
    # sublayered into the output stage, so path mismatches mean it silently
    # defines an unrelated orphan prim instead of the real clip-attached one.
    copy_prim(src_root, topo_stage, Sdf.Path(clip_primpath).GetParentPath())

    # Set defaultPrim so future references do not produce warnings
    topo_stage.SetDefaultPrim(topo_stage.GetPrimAtPath(src_root.GetPath()))
    topo_stage.GetRootLayer().Save()
    print(f"[INFO] Topology written → {topology_path}")


# ---------------------------------------------------------------------------
# Manifest generator
# ---------------------------------------------------------------------------
def generate_manifest(
    probe_frame_path: str,
    clip_primpath: str,
    manifest_path: str,
) -> None:
    """
    Scans the specified frame for attributes that have time samples and
    generates a lightweight manifest USD containing only those attribute paths.
    """
    src_stage = Usd.Stage.Open(probe_frame_path)
    mfst_stage = Usd.Stage.CreateNew(manifest_path)

    src_root = src_stage.GetPrimAtPath(clip_primpath)
    if not src_root.IsValid():
        print(f"[WARNING] Manifest: prim {clip_primpath} not found — skipping manifest generation.")
        return

    animated_count = 0

    def scan_prim(src_prim, dst_stage, dst_parent_path):
        nonlocal animated_count
        dst_path = dst_parent_path.AppendChild(src_prim.GetName())
        dst_prim = dst_stage.DefinePrim(dst_path, src_prim.GetTypeName())

        for attr in src_prim.GetAttributes():
            if attr.GetNumTimeSamples() > 0:
                # Only declare the attribute — no value needed in a manifest
                dst_prim.CreateAttribute(
                    attr.GetName(),
                    attr.GetTypeName(),
                    custom=attr.IsCustom(),
                )
                animated_count += 1

        for child in src_prim.GetChildren():
            scan_prim(child, dst_stage, dst_path)

    # Same reasoning as generate_topology: preserve the source's absolute
    # path so the manifest lands on the same prim the output stage attaches
    # clips to, instead of collapsing to a leaf-name orphan.
    scan_prim(src_root, mfst_stage, Sdf.Path(clip_primpath).GetParentPath())

    mfst_stage.GetRootLayer().Save()
    print(f"[INFO] Manifest written → {manifest_path}  ({animated_count} animated attribute(s))")


def stitch_clips(
    filepath_template: str,
    primpath: str,
    output_path: str,
    frame_range: tuple[int, int],
    scene_range: tuple[int, int] | None = None,
    loop: bool = False,
    clip_set: str = "default",
    clip_primpath: str | None = None,
    strict: bool = False,
    gen_topology: bool = True,
    gen_manifest: bool = True,
    probe_frame: int | None = None,
    auto_detect_prim: bool = True,
    fps: float | None = None,
) -> None:
    """
    Main stitching function.

    Parameters
    ----------
    filepath_template : str
        Per-frame path template; supports {frame:04d} or $F4 format.
    primpath : str
        Prim path on the stage where clips will be attached.
    output_path : str
        Output .usd / .usda / .usdc path.
    frame_range : (start, end)
        Frame range of the source files (inclusive).
    scene_range : (start, end) or None
        Frame range on the scene timeline; None means same as frame_range.
    loop : bool
        Whether to loop file frames to fill the scene_range.
    clip_set : str
        USD Clip Set name; defaults to "default".
    clip_primpath : str or None
        Prim path inside the clip files; None means same as primpath.
    strict : bool
        True → abort if any source file is missing.
    gen_topology : bool
        True → auto-generate topology.usd.
    gen_manifest : bool
        True → auto-generate manifest.usd.
    probe_frame : int or None
        Frame number used to generate topology / manifest.
        None means use the first frame of frame_range.
        Must be within frame_range.
    auto_detect_prim : bool
        True → recursively walk all child prims in the probe frame and attach
        independent clip metadata to each prim that has animated data.
        False → attach a single clip to --primpath / --clip-primpath only.
    fps : float or None
        framesPerSecond / timeCodesPerSecond for the output stage.
        None → auto-detected from the probe frame.
    """
    if scene_range is None:
        scene_range = frame_range

    if clip_primpath is None:
        clip_primpath = primpath

    # --- 1. Build frame lists ---
    scene_frames, file_frames = build_clip_frame_lists(frame_range, scene_range, loop)
    print(f"[INFO] Scene frames : {scene_frames[0]} – {scene_frames[-1]}  ({len(scene_frames)} frames)")
    print(f"[INFO] File frames  : {file_frames[0]} – {file_frames[-1]}  (loop={loop})")

    # --- 2. Expand per-frame paths ---
    filepaths = [resolve_filepath(filepath_template, f) for f in range(frame_range[0], frame_range[1] + 1)]
    validate_files(filepaths, strict=strict)

    # --- 3. Determine probe frame path ---
    if probe_frame is not None:
        if not (frame_range[0] <= probe_frame <= frame_range[1]):
            raise ValueError(
                f"probe_frame {probe_frame} is outside frame_range "
                f"{frame_range[0]}-{frame_range[1]}."
            )
        probe_path = resolve_filepath(filepath_template, probe_frame)
        if not os.path.exists(probe_path):
            raise FileNotFoundError(
                f"Probe frame file does not exist: {probe_path}"
            )
        print(f"[INFO] Probe frame  : {probe_frame}  ({probe_path})")
    else:
        probe_frame = frame_range[0]
        probe_path = filepaths[0]
        if not os.path.exists(probe_path):
            raise FileNotFoundError(
                f"Default probe frame file does not exist: {probe_path}. "
                "Pass an explicit probe_frame pointing to an available file."
            )
        print(f"[INFO] Probe frame  : {probe_frame} (default — first frame)")

    # --- 4. Auto-detect animated child prims ---
    if auto_detect_prim:
        target_primpaths = find_all_animated_prims(probe_path, clip_primpath)
    else:
        target_primpaths = [clip_primpath]

    # --- 5. Determine topology / manifest paths (same directory as output) ---
    out_dir  = os.path.dirname(os.path.abspath(output_path))
    out_stem = os.path.splitext(os.path.basename(output_path))[0]
    out_ext  = os.path.splitext(output_path)[1] or ".usd"
    topology_path = os.path.join(out_dir, f"{out_stem}.topology{out_ext}")
    manifest_path = os.path.join(out_dir, f"{out_stem}.manifest{out_ext}")

    # --- 6. Generate topology (reads clip_primpath in the source clip files) ---
    if gen_topology:
        generate_topology(probe_path, clip_primpath, topology_path)

    # --- 7. Generate manifest (reads clip_primpath in the source clip files) ---
    if gen_manifest:
        generate_manifest(probe_path, clip_primpath, manifest_path)

    # --- 8. Create output stage ---
    os.makedirs(out_dir, exist_ok=True)
    stage = Usd.Stage.CreateNew(output_path)
    stage.SetStartTimeCode(scene_frames[0])
    stage.SetEndTimeCode(scene_frames[-1])

    # FPS: use provided value, otherwise auto-detect from probe frame
    if fps is None:
        src = Usd.Stage.Open(probe_path)
        fps = src.GetTimeCodesPerSecond()
        print(f"[INFO] FPS auto-detected : {fps} (from probe frame)")
    else:
        print(f"[INFO] FPS (manual)      : {fps}")
    stage.SetTimeCodesPerSecond(fps)
    stage.SetFramesPerSecond(fps)

    # --- 9. Ensure root prim exists ---
    root_prim = stage.DefinePrim(primpath)
    if not root_prim.IsValid():
        raise RuntimeError(f"Failed to define prim on stage: {primpath}")

    # defaultPrim must be a top-level prim (/A/B/C → /A)
    top_name = Sdf.Path(primpath).GetPrefixes()[0]  # e.g. /Geometry
    top_prim = stage.GetPrimAtPath(top_name)
    if not top_prim.IsValid():
        top_prim = stage.DefinePrim(top_name)
    stage.SetDefaultPrim(top_prim)
    print(f"[INFO] defaultPrim       : {top_name}")

    # --- 10. Set Clips API (attached at primpath on the output stage; reads
    #         from clip_primpath inside each clip file) ---
    asset_paths = [Sdf.AssetPath(p) for p in filepaths]
    # times: list of (scene_time, file_time) pairs
    # USD selects the asset file based on where scene_time falls in this mapping
    times = [(float(s), float(f)) for s, f in zip(scene_frames, file_frames)]

    clip_api = Usd.ClipsAPI(root_prim)
    clip_api.SetClipAssetPaths(asset_paths, clip_set)
    # clipPrimPath is the path *inside each clip file* USD reads data from;
    # it defaults to primpath (clip_primpath is normalized to primpath above
    # when not explicitly given) but can differ when the source clip files
    # store data at a different path than where clips are attached here.
    clip_api.SetClipPrimPath(clip_primpath, clip_set)
    clip_api.SetClipTimes(times, clip_set)
    # active: (scene_time, assetPaths_index) — explicitly maps each scene frame to a file
    frame_start = frame_range[0]
    active = [(float(s), float(file_frames[i] - frame_start))
              for i, s in enumerate(scene_frames)]
    clip_api.SetClipActive(active, clip_set)
    if gen_manifest:
        clip_api.SetClipManifestAssetPath(Sdf.AssetPath(manifest_path), clip_set)

    # Topology as a sublayer — added once to the root layer
    if gen_topology:
        layer = stage.GetRootLayer()
        topo_rel = os.path.relpath(topology_path, out_dir).replace("\\", "/")
        layer.subLayerPaths.append(topo_rel)

    # --- 11. Save ---
    stage.GetRootLayer().Save()
    print(f"[INFO] Output written → {output_path}")

    # --- 12. Summary ---
    print("\n=== Clip Settings Summary ===")
    print(f"  Clip Set           : {clip_set}")
    print(f"  Root Prim          : {primpath}")
    print(f"  Clip PrimPath      : {clip_primpath} (all child prims covered automatically)")
    print(f"  Animated Prims     : {len(target_primpaths)}")
    for tp in target_primpaths:
        print(f"                       {tp}")
    print(f"  Asset Paths        : {len(asset_paths)} file(s)")
    print(f"  Times              : {[(int(s),int(f)) for s,f in times[:3]]}{'...' if len(times) > 3 else ''}")
    print(f"  FPS                : {fps}")
    print(f"  Auto Detect        : {auto_detect_prim}")
    print(f"  Probe Frame        : {probe_frame}  ({probe_path})")
    print(f"  Topology           : {topology_path if gen_topology else '(skipped)'}")
    print(f"  Manifest           : {manifest_path if gen_manifest else '(skipped)'}")
