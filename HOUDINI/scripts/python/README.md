# Houdini Python Toolkit (`chd_toolkits`)

`HOUDINI/scripts/python/` 目錄是 Houdini Python module 搜尋路徑之一，包含 `chd_toolkits.py`（Houdini-only 工具集，涵蓋 Houdini geometry 與 numpy 的橋接、影像卷積、以及 USD prim / material / clip / layer 查詢）與本 README 文件。

## 安裝

`HOUDINI/scripts/python/` 在 `HOUDINI_PATH` 上時，會自動被 Houdini 的 `PYTHONPATH` 加入。設定方式：

```ini
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

## API

### Houdini geometry / numpy 橋接

#### `matrix_manipulate`

```python
matrix_manipulate(
    matrix: Union[hou.Matrix3, hou.Matrix4],
    data: np.ndarray,
) -> Optional[np.ndarray]
```

用 Houdini 矩陣變換一組 row vector。內部把 `hou.Matrix3` 升為 `hou.Matrix4`，再以 homogeneous coordinate 做乘法。

- `matrix`：`hou.Matrix3` 或 `hou.Matrix4`。
- `data`：`np.ndarray`，shape 必須為 `(N, 3)`；不符合則回 `None`。
- 回傳：`np.ndarray`（`float32`，shape `(N, 3)`）；輸入 shape 不對時回 `None`。

#### `point_attrib_to_numpy`

```python
point_attrib_to_numpy(
    geo: hou.Geometry,
    attr: str = "P",
) -> Optional[np.ndarray]
```

把點屬性原始 buffer 直接 reinterpret 成 numpy array，不複製。

- `geo`：`hou.Geometry`。
- `attr`：`str`，點屬性名稱，預設 `"P"`。
- 回傳：`np.ndarray`，shape `(npoints, attr_size)`；int 屬性 dtype 為 `int32`、float 屬性為 `float32`。屬性不存在或非數值型別回 `None`。

---

### 2D 卷積

#### `convolve2d`

```python
convolve2d(
    image: np.ndarray,
    kernel: np.ndarray,
    padding: int = 0,
    strides: int = 1,
    pad_mode: Optional[str] = None,
) -> np.ndarray
```

純 numpy 實作的 2D 卷積（會 flip kernel，行為與 `scipy_convolve2d` 一致）。簡單但慢，用於驗證或教學。

- `image`：2D `np.ndarray`；非 2D 丟 `ValueError`。
- `kernel`：2D `np.ndarray`；非 2D 丟 `ValueError`。
- `padding`：`int ≥ 0`，padding 量；負數或非整數丟 `ValueError`。
- `strides`：`int ≥ 1`，步長；小於 1 或非整數丟 `ValueError`。
- `pad_mode`：`Optional[str]`，傳給 `np.pad` 的 mode，預設 `None`（內部當 `"constant"`）。
- 回傳：`np.ndarray`，dtype 用 `np.result_type(image.dtype, kernel.dtype, np.float64)` 升格，shape `((H+2P-Kh)//strides + 1, (W+2P-Kw)//strides + 1)`。kernel 大於 padded image 時丟 `ValueError`。

#### `scipy_convolve2d`

```python
scipy_convolve2d(
    image: np.ndarray,
    kernel: np.ndarray,
    mode: str = "same",
    boundary: str = "symm",
) -> np.ndarray
```

`scipy.signal.convolve2d` 的薄封裝。**只有在 scipy 可 import 時這個函式才會被定義**（透過 `importlib.util.find_spec` 偵測），否則不會出現在 module 命名空間。

- `image`、`kernel`：2D `np.ndarray`。
- `mode`：`str`，`"full"` / `"valid"` / `"same"`，預設 `"same"`。
- `boundary`：`str`，`"fill"` / `"wrap"` / `"symm"`，預設 `"symm"`。
- 回傳：`np.ndarray`，shape 視 `mode` 而定。

---

### USD prim transforms

#### `compute_prim_scale`

```python
compute_prim_scale(
    prim: Usd.Prim,
    time: Union[int, float, Usd.TimeCode] = Usd.TimeCode.Default(),
) -> Optional[List[float]]
```

世界空間 scale vector，內部用 `Gf.Matrix4d.Factor()` 做完整分解（不是 row length），能正確處理 shear 與非均勻 scale；mirror（rotation determinant < 0）會在 x 軸帶出負號。

- `prim`：`Usd.Prim`；非 `Xformable` 回 `None`。
- `time`：`int` / `float` / `Usd.TimeCode`；非 `TimeCode` 會自動包成 `Usd.TimeCode(time)`。預設 `Usd.TimeCode.Default()`。
- 回傳：`List[float]`，三元素 `[sx, sy, sz]`；Factor 失敗或非 Xformable 回 `None`。

#### `primitive_xform`

```python
primitive_xform(
    prim: Usd.Prim,
    time: Union[int, float, Usd.TimeCode] = Usd.TimeCode.Default(),
) -> Optional[hou.Matrix4]
```

世界空間 transform 轉 `hou.Matrix4`。

- `prim`：`Usd.Prim`；非 `Xformable` 回 `None`。
- `time`：`int` / `float` / `Usd.TimeCode`，預設 `Usd.TimeCode.Default()`。
- 回傳：`hou.Matrix4`，由 `Gf.Matrix4d` 的四個 row 顯式構造；非 Xformable 回 `None`。

---

### USD material / asset / clip 查詢

#### `get_material_from_prim`

```python
get_material_from_prim(prim: Usd.Prim) -> Optional[UsdShade.Material]
```

透過 `UsdShade.MaterialBindingAPI.GetDirectBinding` 取得直接綁定的 material。

- `prim`：`Usd.Prim`。
- 回傳：`UsdShade.Material`；無 direct binding（`GetMaterialPath().IsEmpty()`）或 material prim invalid 時回 `None`。

#### `get_all_asset_paths_from_prim`

```python
get_all_asset_paths_from_prim(prim: Usd.Prim) -> List[str]
```

收集 prim 上所有 `Sdf.ValueTypeNames.Asset` / `AssetArray` 型屬性的已解析路徑，含 timesamples，去重。空字串路徑（resolve 失敗）會被略過。

- `prim`：`Usd.Prim`。
- 回傳：`List[str]`，每個元素為 `Sdf.AssetPath.resolvedPath`。無 asset 屬性時回空 list。

#### `get_clip_names`

```python
get_clip_names(prim: Usd.Prim) -> Optional[List[str]]
```

列出 prim 上 `clips` metadata 內所有 clipSet 名稱。

- `prim`：`Usd.Prim`。
- 回傳：`List[str]`；無 `clips` metadata 時回 `None`。

#### `get_clip_sequences_from_prim`

```python
get_clip_sequences_from_prim(
    prim: Usd.Prim,
    clip: str = 'default',
) -> Optional[List[str]]
```

取指定 clipSet 的 `assetPaths` 已解析路徑。**template 形式的 clip（用 `templateAssetPath` 而非 `assetPaths`）會回 `None`**。

- `prim`：`Usd.Prim`。
- `clip`：`str`，clipSet 名稱，預設 `'default'`。
- 回傳：`List[str]`，去重；無 `clips` metadata、找不到該 clipSet、或該 clipSet 沒有 `assetPaths` 時回 `None`。

#### `get_all_clip_sequences_from_prim`

```python
get_all_clip_sequences_from_prim(prim: Usd.Prim) -> Optional[List[str]]
```

對 prim 上**所有** clipSet 做 `assetPaths` union。

- `prim`：`Usd.Prim`。
- 回傳：`List[str]`，去重；無 `clips` metadata 回 `None`。

#### `get_all_asset_paths_from_stage`

```python
get_all_asset_paths_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
) -> List[str]
```

從 `prim_path` 開始用 `Usd.PrimRange` traverse，對每個 prim 呼叫 `get_all_asset_paths_from_prim` 並 union。

- `stage`：`Usd.Stage`。
- `prim_path`：`str` 或 `Sdf.Path`，起點 prim 路徑，預設 `'/'`。
- 回傳：`List[str]`，去重；`prim_path` 不存在時 `PrimRange` 為空，回空 list。

#### `get_all_clip_sequences_from_stage`

```python
get_all_clip_sequences_from_stage(
    stage: Usd.Stage,
    prim_path: Union[str, Sdf.Path] = '/',
) -> List[str]
```

從 `prim_path` 開始 traverse stage，對每個有 `clips` metadata 的 prim 呼叫 `get_all_clip_sequences_from_prim` 並 union。

- `stage`：`Usd.Stage`。
- `prim_path`：`str` 或 `Sdf.Path`，預設 `'/'`。
- 回傳：`List[str]`，去重。

---

### USD layer 走訪

#### `get_all_layers_in_layer`

```python
get_all_layers_in_layer(usd_layer: Union[str, Sdf.Layer]) -> List[str]
```

走訪 layer 的所有 composition asset dependencies（sublayer / reference / payload，使用 `Sdf.Layer.GetCompositionAssetDependencies`）並遞迴展開。Cycle detection key 用 `layer.realPath`（fallback `identifier`）統一比對，避免 root 用相對路徑開啟時繞過檢查。

- `usd_layer`：`str`（檔案路徑）或已開啟的 `Sdf.Layer`。
- 回傳：`List[str]`，所有依賴 layer 的絕對路徑；主 layer 開不起來時回空 list。

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
