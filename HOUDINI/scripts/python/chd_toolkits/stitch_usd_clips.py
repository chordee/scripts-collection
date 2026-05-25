#!/usr/bin/env python3
r"""
stitch_usd_clips.py
-------------------
Standalone USD Value Clips stitcher — no Houdini required.
Requires: pip install usd-core

Auto-generates topology.usd and manifest.usd alongside the output file.

Usage:
    python stitch_usd_clips.py [options]

Examples:
    # Basic: stitch frames 1-50 onto scene frames 1-50
    python stitch_usd_clips.py \
        --filepath "/cache/sim.{frame:04d}.usd" \
        --primpath "/World/Geo/sim" \
        --output "/cache/stitched.usd" \
        --frame-range 1 50

    # Loop: stretch 10-frame cache across 60 scene frames
    python stitch_usd_clips.py \
        --filepath "/cache/sim.{frame:04d}.usd" \
        --primpath "/World/Geo/sim" \
        --output "/cache/stitched.usd" \
        --frame-range 1 10 \
        --scene-range 1 60 \
        --loop

    # Custom clip set name
    python stitch_usd_clips.py \
        --filepath "/cache/sim.{frame:04d}.usd" \
        --primpath "/World/Geo/sim" \
        --output "/cache/stitched.usd" \
        --frame-range 1 50 \
        --clip-set "simCache"

    # Use $F4 style token (Houdini convention)
    python stitch_usd_clips.py \
        --filepath "/cache/sim.\$F4.usd" \
        --primpath "/World/Geo/sim" \
        --output "/cache/stitched.usd" \
        --frame-range 1 50

    # Skip auto-generation of topology / manifest
    python stitch_usd_clips.py \
        --filepath "/cache/sim.{frame:04d}.usd" \
        --primpath "/World/Geo/sim" \
        --output "/cache/stitched.usd" \
        --frame-range 1 50 \
        --no-topology \
        --no-manifest

    # Use frame 25 as probe frame for topology / manifest
    python stitch_usd_clips.py \
        --filepath "/cache/sim.{frame:04d}.usd" \
        --primpath "/World/Geo/sim" \
        --output "/cache/stitched.usd" \
        --frame-range 1 50 \
        --probe-frame 25
"""

import argparse
import os
import re
import sys

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
try:
    from pxr import Usd, UsdGeom, Sdf
except ImportError:
    sys.exit(
        "[ERROR] pxr module not found. Please install it first:\n"
        "    pip install usd-core\n"
        "Or ensure the Python environment from Houdini / another DCC is active."
    )


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
    """
    Checks whether each path exists.
    strict=True  → abort on any missing file.
    strict=False → print a warning and continue.
    """
    missing = [p for p in filepaths if not os.path.exists(p)]
    if missing:
        msg = f"[WARNING] The following {len(missing)} file(s) do not exist:\n"
        for p in missing[:10]:
            msg += f"    {p}\n"
        if len(missing) > 10:
            msg += f"    ... and {len(missing)-10} more\n"
        if strict:
            sys.exit("[ERROR] Strict mode: aborting.\n" + msg)
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

    copy_prim(src_root, topo_stage, Sdf.Path.absoluteRootPath)

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

    scan_prim(src_root, mfst_stage, Sdf.Path.absoluteRootPath)

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
            sys.exit(
                f"[ERROR] --probe-frame {probe_frame} is outside frame-range "
                f"{frame_range[0]}–{frame_range[1]}."
            )
        probe_path = resolve_filepath(filepath_template, probe_frame)
        if not os.path.exists(probe_path):
            sys.exit(f"[ERROR] Probe frame file does not exist: {probe_path}")
        print(f"[INFO] Probe frame  : {probe_frame}  ({probe_path})")
    else:
        probe_frame = frame_range[0]
        probe_path = filepaths[0]
        print(f"[INFO] Probe frame  : {probe_frame} (default — first frame)")

    # --- 4. Auto-detect animated child prims ---
    if auto_detect_prim:
        target_primpaths = find_all_animated_prims(probe_path, primpath)
    else:
        target_primpaths = [clip_primpath]

    # --- 5. Determine topology / manifest paths (same directory as output) ---
    out_dir  = os.path.dirname(os.path.abspath(output_path))
    out_stem = os.path.splitext(os.path.basename(output_path))[0]
    out_ext  = os.path.splitext(output_path)[1] or ".usd"
    topology_path = os.path.join(out_dir, f"{out_stem}.topology{out_ext}")
    manifest_path = os.path.join(out_dir, f"{out_stem}.manifest{out_ext}")

    # --- 6. Generate topology (from root primpath, preserving full prim structure) ---
    if gen_topology:
        generate_topology(probe_path, primpath, topology_path)

    # --- 7. Generate manifest (scanning each animated prim) ---
    if gen_manifest:
        generate_manifest(probe_path, primpath, manifest_path)

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
        sys.exit(f"[ERROR] Failed to define prim on stage: {primpath}")

    # defaultPrim must be a top-level prim (/A/B/C → /A)
    top_name = Sdf.Path(primpath).GetPrefixes()[0]  # e.g. /Geometry
    top_prim = stage.GetPrimAtPath(top_name)
    if not top_prim.IsValid():
        top_prim = stage.DefinePrim(top_name)
    stage.SetDefaultPrim(top_prim)
    print(f"[INFO] defaultPrim       : {top_name}")

    # --- 10. Set Clips API (attached to root prim; SetClipPrimPath uses primpath
    #         so all child prims are covered automatically) ---
    asset_paths = [Sdf.AssetPath(p) for p in filepaths]
    # times: list of (scene_time, file_time) pairs
    # USD selects the asset file based on where scene_time falls in this mapping
    times = [(float(s), float(f)) for s, f in zip(scene_frames, file_frames)]

    clip_api = Usd.ClipsAPI(root_prim)
    clip_api.SetClipAssetPaths(asset_paths, clip_set)
    # primPath = primpath means USD reads from that prim in each clip file,
    # so /Geometry/mesh_0, mesh_1, etc. are all resolved correctly
    clip_api.SetClipPrimPath(primpath, clip_set)
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
    print(f"  Clip PrimPath      : {primpath} (all child prims covered automatically)")
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description="Stitch per-frame USD files into a USD Value Clips stage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--filepath",     required=True,
                   help="Per-frame path template, e.g. /cache/sim.{frame:04d}.usd or /cache/sim.$F4.usd")
    p.add_argument("--primpath",     required=True,
                   help="Target prim path on the stage, e.g. /World/Geo/sim")
    p.add_argument("--output",       required=True,
                   help="Output path, e.g. /cache/stitched.usd")
    p.add_argument("--frame-range",  required=True, nargs=2, type=int, metavar=("START", "END"),
                   help="Frame range of the source files")
    p.add_argument("--scene-range",  nargs=2, type=int, metavar=("START", "END"), default=None,
                   help="Scene timeline frame range (defaults to frame-range if omitted)")
    p.add_argument("--loop",         action="store_true",
                   help="Loop file frames to fill the scene-range")
    p.add_argument("--clip-set",     default="default",
                   help="USD Clip Set name (default: default)")
    p.add_argument("--clip-primpath", default=None,
                   help="Prim path inside the clip files (defaults to --primpath)")
    p.add_argument("--strict",       action="store_true",
                   help="Abort if any source file is missing")
    p.add_argument("--fps", type=float, default=None,
                   help="Output stage FPS (default: auto-detected from probe frame)")
    p.add_argument("--no-auto-detect", action="store_true",
                   help="Disable auto-detection of animated child prims (use --primpath as-is)")
    p.add_argument("--no-topology",  action="store_true",
                   help="Skip auto-generation of topology.usd")
    p.add_argument("--no-manifest",  action="store_true",
                   help="Skip auto-generation of manifest.usd")
    p.add_argument("--probe-frame",  type=int, default=None,
                   help="Frame number used to generate topology / manifest (default: first frame of frame-range)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    stitch_clips(
        filepath_template=args.filepath,
        primpath=args.primpath,
        output_path=args.output,
        frame_range=tuple(args.frame_range),
        scene_range=tuple(args.scene_range) if args.scene_range else None,
        loop=args.loop,
        clip_set=args.clip_set,
        clip_primpath=args.clip_primpath,
        strict=args.strict,
        gen_topology=not args.no_topology,
        gen_manifest=not args.no_manifest,
        probe_frame=args.probe_frame,
        auto_detect_prim=not args.no_auto_detect,
        fps=args.fps,
    )
