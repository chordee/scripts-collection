"""chd_toolkits — Houdini Python toolkit.

Submodules
----------
- ``core``: Houdini geometry / numpy bridge and USD prim / layer helpers.
- ``colmap_points``: COLMAP ``.bin`` points → Houdini geometry.
- ``nerfstudio_cam``: Nerfstudio ``transforms.json`` → Houdini animated camera.
- ``stitch_usd_clips``: USD Value Clips stitcher; also runnable as
  ``python -m chd_toolkits.stitch_usd_clips``.

Importing the package itself does not require ``hou``. The ``hou``-dependent
helpers in ``core`` are re-exported best-effort, so ``stitch_usd_clips`` can be
used as a standalone CLI from plain Python with only ``pxr`` available.
"""

try:
    from .core import (  # noqa: F401
        matrix_manipulate,
        point_attrib_to_numpy,
        convolve2d,
        compute_prim_scale,
        primitive_xform,
        get_material_from_prim,
        get_all_asset_paths_from_prim,
        get_clip_names,
        get_clip_sequences_from_prim,
        get_all_clip_sequences_from_prim,
        get_all_asset_paths_from_stage,
        get_all_clip_sequences_from_stage,
        get_all_layers_in_layer,
        get_all_shader_texture_paths_from_stage,
        get_all_vdb_paths_from_stage,
        dump_json,
    )
except ImportError:
    # core requires hou + pxr; only available inside Houdini.
    pass

try:
    from .core import scipy_convolve2d  # noqa: F401
except ImportError:
    pass
