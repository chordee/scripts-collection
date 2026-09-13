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
    CREATOR_NODE_KEY = "HoudiniCreatorNode"
    SOP_LAYER_KEY = "HoudiniTreatAsSopLayer"
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
        include_session_layers: bool = True,
        resolve_nodes: bool = True,
    ) -> None:
        self.stage = stage
        self.include_refs = include_refs
        self.include_session_layers = include_session_layers
        self.resolve_nodes = resolve_nodes

    # ---------- collect ----------

    def layers(self) -> list:
        """Layers the stage currently consumes, not every layer it could reach.

        With ``include_refs`` the local stack is extended by
        ``GetUsedLayers()``, which reports what composition actually traversed.
        A payload that is declared but not loaded (a stage opened with
        ``Usd.Stage.LoadNone``, or an unloaded prim) therefore does not appear —
        it contributes no opinions and Houdini writes nothing for it. Value
        clips do appear without sampling an attribute first, confirmed against
        Houdini's USD build.
        """
        stack = list(
            self.stage.GetLayerStack(
                includeSessionLayers=self.include_session_layers
            )
        )
        if not self.include_refs:
            return stack
        known = {layer.identifier for layer in stack}
        if not self.include_session_layers:
            # GetUsedLayers() always reports the session layer stack, so the
            # layers GetLayerStack() just omitted have to be excluded again.
            known.update(
                layer.identifier
                for layer in self.stage.GetLayerStack(includeSessionLayers=True)
            )
        extra = [
            layer
            for layer in self.stage.GetUsedLayers(includeClipLayers=True)
            if layer.identifier not in known
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

    def _node_path(self, node_id) -> Optional[str]:
        if node_id is None:
            return None
        found, _ = self._node_paths([node_id])
        return found[0] if found else None

    def unresolved_sublayers(self) -> list:
        """Sublayer paths that a layer declares but can't actually be resolved (usually a missing file).

        Scans the same layers :meth:`layers` reports, so a layer pulled in by a
        reference, payload, or clip is checked too — not just the local stack.
        """
        missing: list = []
        for parent in self.layers():
            for sublayer_path in parent.subLayerPaths:
                if Sdf.Layer.FindRelativeToLayer(parent, sublayer_path) is None:
                    missing.append(
                        {"parent": parent.identifier, "subLayerPath": sublayer_path}
                    )
        return missing

    # ---------- describe ----------

    def describe(self, layer: Sdf.Layer, index: int = -1) -> dict:
        meta = self._houdini_meta(layer)
        save_path = meta.get(self.SAVE_PATH_KEY)
        save_control = meta.get(self.SAVE_CONTROL_KEY)
        editor_nodes, stale_ids = self._node_paths(meta.get(self.EDITOR_NODES_KEY))
        # A layer with no save control is "Implicit" in Houdini's terms: it is
        # folded into its parent's file, carries no save path, and its
        # GetDisplayName() is a bare "LOP". The node that created it is the only
        # thing identifying it — that is what Houdini's own Scene Graph Layers
        # panel labels these rows with.
        creator_node = self._node_path(meta.get(self.CREATOR_NODE_KEY))
        return {
            "index": index,
            "identifier": layer.identifier,
            "displayName": layer.GetDisplayName(),
            "creatorNode": creator_node,
            "isSopLayer": bool(meta.get(self.SOP_LAYER_KEY)),
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
        return [self.describe(layer, i) for i, layer in enumerate(self.layers())]

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
