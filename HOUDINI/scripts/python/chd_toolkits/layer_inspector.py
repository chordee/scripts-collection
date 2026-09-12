"""USD layer inspector.

Surveys every ``Sdf.Layer`` a ``Usd.Stage`` uses and reports each layer's
Houdini save settings (``HoudiniSavePath`` / ``HoudiniSaveControl`` /
``HoudiniEditorNodes`` custom layer data), so it's easy to see which layers
will actually be written to disk and by which LOP nodes.

Entry point is :class:`LayerInspector`. Houdini is only required to resolve
``HoudiniEditorNodes`` session ids back to node paths (``resolve_nodes=True``,
the default) — with ``resolve_nodes=False`` this module needs only ``pxr``.
"""

import json
from pathlib import Path
from typing import Optional, Union

from pxr import Sdf, Usd

try:
    import hou
except ImportError:
    hou = None


def _jsonify(value):
    """Recursively convert Sdf/Vt values to plain JSON-safe Python types."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Sdf.AssetPath):
        return {"assetPath": value.path, "resolvedPath": value.resolvedPath}
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    try:
        return [_jsonify(v) for v in value]
    except TypeError:
        return str(value)


class LayerInspector:
    """Survey every layer a ``Usd.Stage`` uses, along with its Houdini save settings."""

    SAVE_PATH_KEY = "HoudiniSavePath"
    SAVE_CONTROL_KEY = "HoudiniSaveControl"
    EDITOR_NODES_KEY = "HoudiniEditorNodes"
    META_PRIM = "/HoudiniLayerInfo"
    # Save-control tokens Houdini authors on /HoudiniLayerInfo, per its own
    # Scene Graph Layers panel (``scenegraphlayers/model.py``): ``Explicit``
    # writes to HoudiniSavePath and ``IsFileFromDisk`` overwrites the file the
    # layer was loaded from, while ``Placeholder`` and ``DoNotSave`` write
    # nothing. An absent token means "Implicit" — the layer is folded into its
    # parent's file rather than written on its own.
    WRITING_CONTROLS = frozenset({"Explicit", "IsFileFromDisk"})

    def __init__(
        self,
        stage: Usd.Stage,
        include_refs: bool = True,
        resolve_nodes: bool = True,
    ) -> None:
        self.stage = stage
        self.include_refs = include_refs
        self.resolve_nodes = resolve_nodes

    # ---------- collect ----------

    def layers(self) -> list:
        stack = list(self.stage.GetLayerStack(includeSessionLayers=True))
        if not self.include_refs:
            return stack
        known = {l.identifier for l in stack}
        extra = [
            l
            for l in self.stage.GetUsedLayers(includeClipLayers=True)
            if l.identifier not in known
        ]
        return stack + extra

    def _houdini_meta(self, layer: Sdf.Layer) -> dict:
        meta = dict(layer.customLayerData or {})
        spec = layer.GetPrimAtPath(self.META_PRIM)
        if spec is not None:
            meta.update(dict(spec.customData or {}))
        return meta

    def _node_paths(self, ids) -> tuple:
        if not self.resolve_nodes or not ids or hou is None:
            return [], []
        found: list = []
        stale: list = []
        for sid in ids:
            n = hou.nodeBySessionId(int(sid))
            if n:
                found.append(n.path())
            else:
                stale.append(int(sid))
        return found, stale

    def unresolved_sublayers(self) -> list:
        """Sublayer paths that a layer declares but can't actually be resolved (usually a missing file)."""
        missing: list = []
        for parent in self.stage.GetLayerStack(includeSessionLayers=True):
            for p in parent.subLayerPaths:
                if Sdf.Layer.FindRelativeToLayer(parent, p) is None:
                    missing.append({"parent": parent.identifier, "subLayerPath": p})
        return missing

    # ---------- describe ----------

    def describe(self, layer: Sdf.Layer, index: int = -1) -> dict:
        meta = self._houdini_meta(layer)
        save_path = meta.get(self.SAVE_PATH_KEY)
        save_control = meta.get(self.SAVE_CONTROL_KEY)
        editor_nodes, stale_ids = self._node_paths(meta.get(self.EDITOR_NODES_KEY))
        return {
            "index": index,
            "identifier": layer.identifier,
            "displayName": layer.GetDisplayName(),
            "implicit": layer.anonymous,
            "realPath": layer.realPath or "",
            "savePath": save_path,
            "saveControl": save_control,
            "willWriteFile": bool(save_path) and save_control in self.WRITING_CONTROLS,
            "isRootLayer": layer == self.stage.GetRootLayer(),
            "isSessionLayer": layer == self.stage.GetSessionLayer(),
            "dirty": layer.dirty,
            "muted": self.stage.IsLayerMuted(layer.identifier),
            "editorNodes": editor_nodes,
            "staleEditorNodeIds": stale_ids,
            "customLayerData": _jsonify(meta),
        }

    def report(self) -> list:
        return [self.describe(l, i) for i, l in enumerate(self.layers())]

    def full_report(self) -> dict:
        layers = self.report()
        return {
            "layers": layers,
            "unresolvedSublayers": self.unresolved_sublayers(),
            "summary": {
                "total": len(layers),
                "implicit": sum(1 for d in layers if d["implicit"]),
                "explicit": sum(1 for d in layers if not d["implicit"]),
                "pendingWrites": [d["savePath"] for d in layers if d["willWriteFile"]],
            },
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.full_report(), indent=indent, ensure_ascii=False)


def layers_to_json(stage: Usd.Stage, indent: Optional[int] = 2, **kwargs) -> str:
    return LayerInspector(stage, **kwargs).to_json(indent=indent)
