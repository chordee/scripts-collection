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
- `--skin` 寫在 relationship 名稱後面，不是寫在 prim 路徑上：relationship target 只能存純路徑，而 LOP 的 prim pattern 會把 `-` 解讀成排除語法。
- 不認得的 flag（例如打錯成 `--skins`）會丟 `ValueError`，避免靜默退回 bind pose。

### `--skin` 的行為

- input 可以指向 mesh、底下有多個 mesh 的 Xform、SkelRoot，或更上層的 prim；會找出涵蓋到的所有 SkelRoot。
- 只保留有骨架綁定的 prim（含 rigid 綁定與從祖先繼承的 `skel:skeleton`）；沒綁骨頭的 prim、SkelRoot 以外的 prim 都會被排除。
- 點位、normal、blendshape、rigid 綁定的 transform 都交給 `UsdSkel.BakeSkinning` 計算。
- 烘焙在一個遮罩過的 stage 副本上進行，該副本的 session layer 再 sublayer 原本的 session layer，**算圖用的 stage 不會被修改**。
- `BakeSkinning` 只在動畫有 time sample 的時間點烘焙，所以會先把 SkelAnimation 在當格的內插值釘成一個 time sample，子幀與一拍二的動畫才不會拿到 rest pose。

### 已知限制

- husk 帶 `--validategeo` 時，`runprocedurals.py` 只接受 SideFX 簽章過的 procedural 檔案，本檔會被拒絕。
- 位於 instance 底下的 skinned prim（instance proxy）無法被 `BakeSkinning` 寫入，未驗證。
- 每個帶 `--skin` 的 input 在每個時間樣本都會開一次遮罩 stage 並烘焙，角色越多成本越高。
- 原版 `overrides` 取 primvar 值時用的是 `hou.frame()` 而非該時間樣本，motion blur 各樣本會拿到相同參數；這是原版行為，此處未更動。
