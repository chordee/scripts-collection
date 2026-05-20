# Houdini Python Toolkit (`chd_toolkits`)

`HOUDINI/scripts/python/` 目錄是 Houdini Python module 搜尋路徑之一，本目錄只放 `chd_toolkits.py` — 一個整合的 Houdini-only 工具集，涵蓋 Houdini geometry 與 numpy 的橋接、影像卷積、以及 USD prim / material / clip / layer 查詢。

## 安裝

`HOUDINI/scripts/python/` 在 `HOUDINI_PATH` 上時，會自動被 Houdini 的 `PYTHONPATH` 加入。設定方式：

```
HOUDINI_PATH = D:/dev/scripts-collection/HOUDINI;&
```

或在 package JSON 中：

```json
{
    "env": [
        { "HOUDINI_PATH": "D:/dev/scripts-collection/HOUDINI" }
    ]
}
```

之後在 Houdini 的 Python shell、Python SOP、HDA event handler 等處：

```python
import chd_toolkits as ct
```

## 相依

- `hou`（Houdini 環境內建）
- `numpy`
- `pxr.Usd`、`pxr.UsdGeom`、`pxr.UsdShade`、`pxr.Sdf`、`pxr.Gf`（Houdini 內建）
- `scipy`（**可選**；若存在則自動暴露 `scipy_convolve2d`）

## API 一覽

### Houdini geometry / numpy 橋接

| 函式 | 用途 |
|---|---|
| `matrix_manipulate(matrix, data)` | 用 `hou.Matrix3` 或 `hou.Matrix4` 變換 Nx3 numpy row vector array。內部以 homogeneous coord + 4x4 矩陣處理。 |
| `point_attrib_to_numpy(geo, attr='P')` | 把 `hou.Geometry` 上的 int / float 點屬性轉成正確 dtype 的 numpy array，shape 為 `(npoints, size)`。 |

### 2D 卷積

| 函式 | 用途 |
|---|---|
| `convolve2d(image, kernel, padding=0, strides=1, pad_mode=None)` | 純 numpy 實作的 2D cross-correlation。簡單但慢，用於驗證或教學。 |
| `scipy_convolve2d(image, kernel, mode='same', boundary='symm')` | `scipy.signal.convolve2d` 的薄封裝；scipy 不存在時函式不會被定義。 |

### USD prim transforms

| 函式 | 用途 |
|---|---|
| `compute_prim_scale(prim, time=Usd.TimeCode.Default())` | 取 prim world-space scale vector。內部用 `Gf.Matrix4d.Factor()` 做完整分解（不是 row length，能正確處理 shear/mirror），鏡像 transform 會在 x 軸帶出負號。 |
| `primitive_xform(prim, time=Usd.TimeCode.Default())` | 取 prim 的 world-space transform，轉成 `hou.Matrix4`。 |

### USD material / asset / clip 查詢

| 函式 | 用途 |
|---|---|
| `get_material_from_prim(prim)` | 透過 `MaterialBindingAPI.GetDirectBinding` 取得直接綁定的 `UsdShade.Material`；無 binding 時回 None。 |
| `get_all_asset_paths_from_prim(prim)` | 收集 prim 上所有 `Asset` / `AssetArray` 型屬性的已解析路徑（含 timesample），去重。 |
| `get_clip_names(prim)` | 列出 prim 的 `clips` metadata 中所有 clipSet 名稱。 |
| `get_clip_sequences_from_prim(prim, clip='default')` | 取指定 clipSet 的 `assetPaths` 已解析路徑。注意：template 形式的 clip（用 `templateAssetPath`）沒有 `assetPaths`，會回 None。 |
| `get_all_clip_sequences_from_prim(prim)` | 對 prim 上所有 clipSet 做 union。 |
| `get_all_asset_paths_from_stage(stage, prim_path='/')` | 從 prim_path 開始 traverse stage，回所有 asset path（含子 prim）。 |
| `get_all_clip_sequences_from_stage(stage, prim_path='/')` | 從 prim_path 開始 traverse stage，回所有 clip sequence path。 |

### USD layer 走訪

| 函式 | 用途 |
|---|---|
| `get_all_layers_in_layer(usd_layer)` | 走訪 layer 的所有 composition asset dependencies（sublayer / reference / payload，使用 `Sdf.Layer.GetCompositionAssetDependencies`）並遞迴展開，自動偵測 cycle。回傳絕對路徑 list。 |

## 設計筆記

- **命名**：全部 snake_case，與 Python 慣例一致。
- **回傳型別**：`Optional[List[...]]` 用於「資源不存在」回 None 的查詢；恆定回 list 的函式直接標 `List[...]`。
- **時間參數**：接受 `int`、`float` 或 `Usd.TimeCode`；非 TimeCode 會自動包成 `Usd.TimeCode(time)`。
- **mirror 偵測**：`compute_prim_scale` 用 rotation determinant < 0 判定鏡像，慣例上在 x 軸帶出負號。
- **cycle detection**：`get_all_layers_in_layer` 用 visited set 追蹤 layer identifier 與絕對路徑，避免 sublayer 互相 reference 造成無窮遞迴。
- **scipy 是 optional**：透過 `importlib.util.find_spec` 偵測；不存在時 `scipy_convolve2d` 不會被定義（不是 stub），呼叫端會看到 `AttributeError` 而非靜默走錯路徑。

## 參考文件

- HOM Geometry：<https://www.sidefx.com/docs/houdini/hom/hou/Geometry.html>
- HOM Matrix4：<https://www.sidefx.com/docs/houdini/hom/hou/Matrix4.html>
- Gf.Matrix4d：<https://openusd.org/release/api/class_gf_matrix4d.html>
- UsdGeomXformable：<https://openusd.org/release/api/class_usd_geom_xformable.html>
- UsdShade MaterialBindingAPI：<https://openusd.org/release/api/class_usd_shade_material_binding_a_p_i.html>
- USD Value Clips：<https://openusd.org/release/api/_usd__page__value_clips.html>
- Sdf.Layer：<https://openusd.org/release/api/class_sdf_layer.html>
