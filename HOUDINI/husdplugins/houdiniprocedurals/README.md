# Houdini Procedurals

本目錄存放自訂的 Houdini procedural（`HoudiniProceduralAPI`），在 husk 算圖時（以及 Solaris 的 Preview Procedurals）執行。

## 載入方式

husk 透過 `husd/runprocedurals.py` 找出套用了 `HoudiniProceduralAPI` 的 prim，讀取 `houdini:procedural:path`。值若只是檔名（例如 `invokegraph_skinned.py`），會在 `HOUDINI_HUSDPLUGINS_PATH` 底下的 `houdiniprocedurals/` 目錄搜尋 — 把 `HOUDINI/` 加進 `HOUDINI_PATH` 即可（安裝見 [`HOUDINI/README.md`](../../README.md)）。

模組需提供 `procedural(prim, args)`，`args` 是 `houdini:procedural:args` 字串經 `ast.literal_eval` 轉成的 dict，另外被塞入 `__husk_settings`、`__preview`、`__validateGeo`。

## invokegraph_skinned.py

以 Houdini 22.0.429 原版 `invokegraph.py` 為基底（第一個 commit 是未修改的原檔，方便比對差異），只多一個功能：**input 可以改取骨架驅動後的模型**。

原版把 `inputs` 指到的 prim 匯入成 SOP geometry 時，讀的是 mesh 的 `points`，也就是 UsdSkel 的 bind pose。在 `args['inputs']` 的項目後面加上 `--skin`，該 input 改為取當格（含 motion blur 子幀）經 skinning 與 blendshape 驅動後的結果：

```python
{
    'graph': '...',
    'inputs': ['guideprims:input_0', 'skinprims:input_1 --skin'],
    ...
}
```

- 沒有 `--skin` 的項目行為與原版完全相同，兩種可以混用。
- `--skin` 只加在 `args['inputs']` 這份**字串清單**的項目上；procedural 會先切掉 flag，再用乾淨的名稱 `prim.GetRelationship()`。relationship 本身的名稱與 target 都不能動：名稱帶空白是不合法的屬性名，target 只能存純 prim 路徑（LOP 的 prim pattern 也會把 `-` 解讀成排除語法）。
- 不認得的 flag（例如打錯成 `--skins`）會丟 `ValueError`，避免靜默退回 bind pose。

### 使用方式

procedural prim 上要改兩個屬性：

| 屬性 | 原本 | 改成 |
|---|---|---|
| `houdini:procedural:path` | `invokegraph.py` | `invokegraph_skinned.py` |
| `houdini:procedural:args` 的 `inputs` | `['guideprims:input_0', 'skinprims:input_1']` | 要走骨架驅動的項目加 ` --skin` |

只改 args 不改 path 的話，husk 跑的仍是原版，會把 `'skinprims:input_1 --skin'` 整串當成 relationship 名稱而找不到。

**自己寫的 procedural LOP**：在組 args 的地方加上 flag，relationship 照原名建立：

```python
for i, iname in enumerate(input_parms):
    rel_name = '{}:input_{}'.format(iname, i)
    rel = prim.CreateRelationship(rel_name)          # relationship 名稱維持乾淨
    for path in input_prim_paths[iname]:
        rel.AddTarget(path)
    entry = rel_name
    if node.evalParm('{}_skin'.format(iname)):       # 例：每個 input 一個 toggle
        entry += ' --skin'
    args['inputs'].append(entry)                     # 只有 args 裡的項目帶 flag
```

**SideFX 的 procedural LOP（例如 Houdini Hair Procedural）**：args 由 LOP 自行寫入，在其下游接一個 Python Script LOP 改寫：

```python
import ast
from pxr import Sdf
from husd import UsdHoudini

PROC_PRIM = "/hairproc"        # 套了 procedural 的 prim
SKIN_INPUTS = ["skinprims"]    # 要走骨架驅動的 input（relationship 名稱冒號前那段）

stage = hou.pwd().editableStage()
prim = stage.GetPrimAtPath(PROC_PRIM)
for api in UsdHoudini.HoudiniProceduralAPI.GetAll(prim):
    api.GetHoudiniProceduralPathAttr().Set(Sdf.AssetPath("invokegraph_skinned.py"))
    args_attr = api.GetHoudiniProceduralArgsAttr()
    args = ast.literal_eval(args_attr.Get(hou.frame()))
    args["inputs"] = [
        entry + " --skin"
        if entry.split(":")[0] in SKIN_INPUTS and "--skin" not in entry.split()
        else entry
        for entry in args.get("inputs", [])
    ]
    args_attr.Set(repr(args))
```

relationship 名稱可在 Scene Graph Details 選取 procedural prim 查看。改完後 args 應該像 `'inputs': ['guideprims:input_0', 'skinprims:input_1 --skin']`。算圖機的 `HOUDINI_PATH` 也必須包含本 repo 的 `HOUDINI/`，husk 才找得到 `invokegraph_skinned.py`。

### `--skin` 的行為

- input 可以指向 mesh、底下有多個 mesh 的 Xform、SkelRoot，或更上層的 prim；會找出涵蓋到的所有 SkelRoot。
- 只保留有骨架綁定的 prim（含 rigid 綁定與從祖先繼承的 `skel:skeleton`）；沒綁骨頭的 prim、SkelRoot 以外的 prim 都會被排除。
- 點位、normal、blendshape、rigid 綁定的 transform 都交給 `UsdSkel.BakeSkinning` 計算。
- 烘焙在一個遮罩過的 stage 副本上進行，該副本的 session layer 再 sublayer 原本的 session layer，**算圖用的 stage 不會被修改**。
- `BakeSkinning` 只在動畫有 time sample 的時間點烘焙，所以會先把 SkelAnimation 在當格的內插值釘成一個 time sample，子幀與一拍二的動畫才不會拿到 rest pose。

### husk 設定

husk 預設 `--allowed-procedurals basic`，會以 `--validategeo` 執行 procedural，只接受 SideFX 簽章過的檔案；本檔會以 `RuntimeError: Checksum for procedural ... is not in the approved list.` 被拒絕。算圖時（含 farm 的 husk 指令）必須加上 `--allowed-procedurals all`（依 husk 說明，此模式可能需要 Houdini Engine 授權）。

### Houdini 版本差異

| | Houdini 22 | Houdini 21 |
|---|---|---|
| `procedural()` 回傳 | `[(frame, hou.Geometry), ...]` | 單一 `hou.Geometry` |
| 多樣本 deformation motion blur | 有（procedural prim 套 `MotionAPI` 且 `motion:nonlinearSampleCount` > 1，相機需有 shutter） | 無 |

Houdini 21 的 `runprocedurals.py` 把回傳值直接交給 `hou.lop.addLockedGeometry()`，沒有時間樣本的概念，原版 `invokegraph.py` 在 H21 也沒有 motion blur；本檔依 `hou.applicationVersion()` 切換回傳格式。`--skin` 在兩個版本都會取當格驅動後的模型。

### 已知限制

- 位於 instance 底下的 skinned prim（instance proxy）無法被 `BakeSkinning` 寫入，未驗證。
- 每個帶 `--skin` 的 input 在每個時間樣本都會開一次遮罩 stage 並烘焙，角色越多成本越高。
- 原版 `overrides` 取 primvar 值時用的是 `hou.frame()` 而非該時間樣本，motion blur 各樣本會拿到相同參數；這是原版行為，此處未更動。
