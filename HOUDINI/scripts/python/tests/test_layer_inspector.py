"""Tests for chd_toolkits.layer_inspector.

Pure pxr module — runs in both hython and plain Python (the latter needs
``pip install usd-core``). No editor-node ids are exercised, so ``hou`` is
never required.
"""

import json
from pathlib import Path

import pytest

# Skip the whole file if pxr is missing (plain Python without usd-core).
pytest.importorskip("pxr")
from pxr import Sdf, Usd

from chd_toolkits.layer_inspector import LayerInspector, layers_to_json


def _stage_with_sublayer(tmp_path):
    sub_path = tmp_path / "sub.usda"
    sub_layer = Sdf.Layer.CreateNew(str(sub_path))
    sub_layer.Save()

    root_path = tmp_path / "root.usda"
    root_layer = Sdf.Layer.CreateNew(str(root_path))
    root_layer.subLayerPaths.append(str(sub_path))
    root_layer.Save()

    return Usd.Stage.Open(str(root_path)), root_layer, sub_layer


# ---------------------------------------------------------------------------
# layers() / report()
# ---------------------------------------------------------------------------


def test_layers_includes_root_and_sublayer(tmp_path):
    stage, root_layer, sub_layer = _stage_with_sublayer(tmp_path)
    inspector = LayerInspector(stage)
    identifiers = {layer.identifier for layer in inspector.layers()}
    assert root_layer.identifier in identifiers
    assert sub_layer.identifier in identifiers


def test_layers_excludes_session_layer_when_asked(tmp_path):
    stage, root_layer, sub_layer = _stage_with_sublayer(tmp_path)
    session_id = stage.GetSessionLayer().identifier

    with_session = {layer.identifier for layer in LayerInspector(stage).layers()}
    without_session = {
        layer.identifier
        for layer in LayerInspector(stage, include_session_layers=False).layers()
    }

    assert session_id in with_session
    assert session_id not in without_session
    # Everything else is still reported
    assert without_session == with_session - {session_id}
    assert root_layer.identifier in without_session
    assert sub_layer.identifier in without_session


def test_report_excludes_session_layer_when_asked(tmp_path):
    stage, _, _ = _stage_with_sublayer(tmp_path)
    report = LayerInspector(stage, include_session_layers=False).report()
    assert not any(d["isSessionLayer"] for d in report)


def _stage_with_payload(tmp_path, load_policy):
    asset_path = tmp_path / "asset.usda"
    asset_layer = Sdf.Layer.CreateNew(str(asset_path))
    Usd.Stage.Open(asset_layer).DefinePrim("/Asset", "Xform")
    asset_layer.Save()

    root_path = tmp_path / "root.usda"
    root_layer = Sdf.Layer.CreateNew(str(root_path))
    root_stage = Usd.Stage.Open(root_layer)
    prim = root_stage.DefinePrim("/World", "Xform")
    prim.GetPayloads().AddPayload(str(asset_path), "/Asset")
    root_layer.Save()

    return Usd.Stage.Open(str(root_path), load_policy), asset_layer


def test_layers_includes_loaded_payload(tmp_path):
    stage, asset_layer = _stage_with_payload(tmp_path, Usd.Stage.LoadAll)
    identifiers = {layer.identifier for layer in LayerInspector(stage).layers()}
    assert asset_layer.identifier in identifiers


def test_layers_omits_unloaded_payload(tmp_path):
    # GetUsedLayers() reports what composition actually traversed, so a payload
    # that was never loaded contributes no layer — and nothing gets written for
    # it on save either.
    stage, asset_layer = _stage_with_payload(tmp_path, Usd.Stage.LoadNone)
    identifiers = {layer.identifier for layer in LayerInspector(stage).layers()}
    assert asset_layer.identifier not in identifiers


def test_layers_includes_clip_layer_without_sampling_first(tmp_path):
    clip_path = tmp_path / "clip.001.usda"
    clip_layer = Sdf.Layer.CreateNew(str(clip_path))
    clip_stage = Usd.Stage.Open(clip_layer)
    clip_prim = clip_stage.DefinePrim("/World/geo", "Xform")
    clip_prim.CreateAttribute("size", Sdf.ValueTypeNames.Float).Set(1.0, 1.0)
    clip_layer.Save()

    root_path = tmp_path / "clip_root.usda"
    root_layer = Sdf.Layer.CreateNew(str(root_path))
    root_stage = Usd.Stage.Open(root_layer)
    clips = Usd.ClipsAPI(root_stage.DefinePrim("/World/geo", "Xform"))
    clips.SetClipAssetPaths([Sdf.AssetPath(str(clip_path))])
    clips.SetClipPrimPath("/World/geo")
    clips.SetClipActive([(1.0, 0)])
    clips.SetClipTimes([(1.0, 1.0)])
    root_layer.Save()

    stage = Usd.Stage.Open(str(root_path))
    names = {Path(layer.identifier).name for layer in LayerInspector(stage).layers()}
    assert "clip.001.usda" in names


def test_report_marks_root_and_session_layer(tmp_path):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    inspector = LayerInspector(stage)
    report = inspector.report()

    root_entry = next(d for d in report if d["identifier"] == root_layer.identifier)
    assert root_entry["isRootLayer"] is True
    assert root_entry["implicit"] is False

    session_entry = next(d for d in report if d["isSessionLayer"])
    assert session_entry["implicit"] is True


# ---------------------------------------------------------------------------
# HoudiniSavePath / HoudiniSaveControl custom layer data
# ---------------------------------------------------------------------------


def test_describe_reads_save_path_and_control(tmp_path):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    root_layer.customLayerData = {
        "HoudiniSavePath": "$HIP/out.usd",
        "HoudiniSaveControl": "Explicit",
    }
    inspector = LayerInspector(stage)
    entry = inspector.describe(root_layer)

    assert entry["savePath"] == "$HIP/out.usd"
    assert entry["saveControl"] == "Explicit"
    assert entry["willWriteFile"] is True


def test_describe_will_write_file_for_file_from_disk_control(tmp_path):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    root_layer.customLayerData = {
        "HoudiniSavePath": "$HIP/out.usd",
        "HoudiniSaveControl": "IsFileFromDisk",
    }
    entry = LayerInspector(stage).describe(root_layer)
    assert entry["willWriteFile"] is True


@pytest.mark.parametrize("control", ["Placeholder", "DoNotSave"])
def test_describe_will_write_file_false_for_non_writing_controls(tmp_path, control):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    root_layer.customLayerData = {
        "HoudiniSavePath": "$HIP/out.usd",
        "HoudiniSaveControl": control,
    }
    entry = LayerInspector(stage).describe(root_layer)
    assert entry["willWriteFile"] is False


def test_describe_reads_metadata_from_houdini_layer_info_prim(tmp_path):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    info = Sdf.PrimSpec(root_layer, "HoudiniLayerInfo", Sdf.SpecifierDef)
    info.customData = {
        "HoudiniSavePath": "$HIP/from_prim.usd",
        "HoudiniSaveControl": "Explicit",
    }
    entry = LayerInspector(stage).describe(root_layer)

    assert entry["savePath"] == "$HIP/from_prim.usd"
    assert entry["willWriteFile"] is True


def test_describe_will_write_file_false_without_save_path(tmp_path):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    inspector = LayerInspector(stage)
    entry = inspector.describe(root_layer)

    assert entry["savePath"] is None
    assert entry["willWriteFile"] is False


# ---------------------------------------------------------------------------
# unresolved_sublayers()
# ---------------------------------------------------------------------------


def test_unresolved_sublayers_reports_missing_file(tmp_path):
    root_path = tmp_path / "root.usda"
    root_layer = Sdf.Layer.CreateNew(str(root_path))
    root_layer.subLayerPaths.append("./missing.usda")
    root_layer.Save()
    stage = Usd.Stage.Open(str(root_path))

    inspector = LayerInspector(stage)
    missing = inspector.unresolved_sublayers()

    assert len(missing) == 1
    assert missing[0]["subLayerPath"] == "./missing.usda"
    assert missing[0]["parent"] == root_layer.identifier


def test_unresolved_sublayers_covers_referenced_layers(tmp_path):
    ref_path = tmp_path / "ref.usda"
    ref_layer = Sdf.Layer.CreateNew(str(ref_path))
    ref_stage = Usd.Stage.Open(ref_layer)
    ref_stage.DefinePrim("/Asset", "Xform")
    ref_layer.subLayerPaths.append("./missing_in_ref.usda")
    ref_layer.Save()

    root_path = tmp_path / "root.usda"
    root_layer = Sdf.Layer.CreateNew(str(root_path))
    root_stage = Usd.Stage.Open(root_layer)
    prim = root_stage.DefinePrim("/World", "Xform")
    prim.GetReferences().AddReference(str(ref_path), "/Asset")
    root_layer.Save()

    stage = Usd.Stage.Open(str(root_path))
    missing = LayerInspector(stage).unresolved_sublayers()

    assert [d["subLayerPath"] for d in missing] == ["./missing_in_ref.usda"]
    assert missing[0]["parent"] == ref_layer.identifier

    # Without reference layers in scope the referenced layer isn't scanned
    assert LayerInspector(stage, include_refs=False).unresolved_sublayers() == []


def test_unresolved_sublayers_empty_when_all_resolve(tmp_path):
    stage, _, _ = _stage_with_sublayer(tmp_path)
    inspector = LayerInspector(stage)
    assert inspector.unresolved_sublayers() == []


# ---------------------------------------------------------------------------
# editor nodes without hou -> resolve_nodes has nothing to resolve
# ---------------------------------------------------------------------------


def test_describe_without_editor_nodes_metadata_returns_empty_lists(tmp_path):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    inspector = LayerInspector(stage)
    entry = inspector.describe(root_layer)

    assert entry["editorNodes"] == []
    assert entry["staleEditorNodeIds"] == []


# ---------------------------------------------------------------------------
# full_report() / to_json() / layers_to_json()
# ---------------------------------------------------------------------------


def test_full_report_summary_counts_and_pending_writes(tmp_path):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    root_layer.customLayerData = {
        "HoudiniSavePath": "$HIP/out.usd",
        "HoudiniSaveControl": "Explicit",
    }
    inspector = LayerInspector(stage)
    full_report = inspector.full_report()

    assert full_report["summary"]["total"] == len(full_report["layers"])
    assert "$HIP/out.usd" in full_report["summary"]["pendingWrites"]
    assert full_report["unresolvedSublayers"] == []


def test_to_json_round_trips_through_json_loads(tmp_path):
    stage, _, _ = _stage_with_sublayer(tmp_path)
    inspector = LayerInspector(stage)
    parsed = json.loads(inspector.to_json())
    assert "layers" in parsed
    assert "summary" in parsed


def test_layers_to_json_module_function_matches_class(tmp_path):
    stage, _, _ = _stage_with_sublayer(tmp_path)
    via_function = json.loads(layers_to_json(stage))
    via_class = json.loads(LayerInspector(stage).to_json())
    assert via_function == via_class


def test_custom_layer_data_jsonifies_asset_path(tmp_path):
    stage, root_layer, _ = _stage_with_sublayer(tmp_path)
    root_layer.customLayerData = {"someAsset": Sdf.AssetPath("./tex.png")}
    inspector = LayerInspector(stage)
    entry = inspector.describe(root_layer)

    assert entry["customLayerData"]["someAsset"]["assetPath"] == "./tex.png"
